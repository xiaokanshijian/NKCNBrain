import nkcn_public_config as _public_config
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
from django.conf import settings
import pandas as pd
from threading import Thread

from django.core.cache import cache

from PIL import Image, ExifTags
import io

import matplotlib.pyplot as plt
import matplotlib

matplotlib.use('Agg')  # 使用非交互式后端
import numpy as np
from scipy.signal import find_peaks
from io import BytesIO

from anthropic import APITimeoutError
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import render, HttpResponse, redirect
import json
import base64
import asyncio
import os
import math
import random
from datetime import datetime, timedelta, timezone as dt_timezone
import fitz
from openai import AsyncOpenAI, OpenAI
import pytz
from django.utils import timezone
from django.db.models import Q, Max
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

# DMT分析相关导入
from app_chat.dmt_analysis import start_dmt_analysis, get_dmt_analysis_status, get_dmt_analysis_result, \
    stop_dmt_analysis, check_dmt_config

from app_chat.automation import AutomationEngine
from app_chat.bgcGenerate import summarize_group, summarize_scene, summarize_user, summarize_notebook, clean_emoji
from app_chat.dmt_utils import compress_image_if_needed
from app_chat.models import Card, BgCard, AutomationTask, AutomationRecord, AutomationStatus, DMTAnalysisTask
from app_chat.core.model_manager import model_manager
from app_chat.config.config_manager import config_manager
from app_chat.views_generate_permanent_card import generate_permanent_card, delete_permanent_card
from app_chat.views_analyze_cognitive_state import analyze_cognitive_state
from app_chat.views_smart_sort_questions import smart_sort_questions

from app_chat.global_state import GLOBAL_STATE
from app_chat.interrupt_manager import interrupt_manager

from app1.models import UserSceneParams, User
from llm_langchain.normal_qa import get_qa_direct_api, get_single_model_response
from zym.models import UserNotebook, scene

from llm_langchain import parse_input, normal_qa, normal_qa_new, get_suma, get_rel_que, global_var, red_bule_rate, \
    get_topic
from llm_langchain.parse_input import *
from llm_langchain import init
from llm_langchain.red_bule_rate import extract_number_SFT, extract_color_SFT, extract_reason_SFT, extract_number, \
    extract_color, extract_reason
from app_chat import tests as chat_tests, utils
from app_chat import gpt4_api, claude_api, kimi_api, deepseek_api, dsreasoner_api, mutil_agent_loop, mutil_agent_dabate
from app_chat.memory_tier_consolidation import schedule_memory_tier_consolidation, get_memory_tier_context_for_user

from app_chat.utils import read_prompt_from_bytes, prompt_to_ghp, remove_spaces_and_blank_lines, get_time_period, \
    is_rest_time, split_text_by_size, sample_content, get_first_valid_answer, remove_thinking_and_checking_blocks, \
    restore_thinking_checking_blocks, calculate_weighted_score_recursion, extract_card_ids, get_base64_size, \
    add_cardImage, detect_special_markers, calculate_overlap_ratio, count_words, get_total_words_count, \
    count_words_another, limit_content_to_400_chars
from app_chat.tts import generate_wav_response
from collections import OrderedDict
from django.http import FileResponse
from django.http import StreamingHttpResponse
from django.core.files.storage import FileSystemStorage

from app_chat.tts import pcm2wav, convert_pcm_to_webm
from app_chat.volcanotts import generate

from app_chat.baidu_trans_doc import translate, check_for_single, translation_requests

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel, SimpleChatModel
from langchain_experimental.llms import ChatLlamaAPI
from app_chat.utils import is_valid_answer
from .models import DeletedFile

from concurrent.futures import ThreadPoolExecutor, TimeoutError
from requests_futures.sessions import FuturesSession
from llm_langchain.util import image_retry_summary_prompt, image_merge_summary_prompt
from dashscope import MultiModalConversation

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

# 🔥 文档四色DMT属性处理的全局锁和正在处理的文档集合（避免重复分析）
document_processing_lock = threading.Lock()
document_processing_docs = set()  # 存储正在处理的文档键，格式: "username:filename"

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

# HLScore 计算状态管理
hlscore_status = {}  # 格式: {key: {'status': 'processing/completed/failed', 'result': HLScore}}


def get_hlscore_status(key):
    """获取HLScore计算状态"""
    return hlscore_status.get(key, {'status': 'not_started'})


def set_hlscore_status(key, status, result=None):
    """设置HLScore计算状态"""
    hlscore_status[key] = {'status': status, 'result': result}


# 异步计算HLScore的函数
def async_calculate_hlscore(username, realName, filename, imgid, content, base64_image, key):
    """
    异步计算并保存 HLScore 的函数
    """
    try:
        print(f"开始异步计算 HLScore: {username}/{filename}-{imgid}")

        # 设置处理中状态
        set_hlscore_status(key, 'processing')

        # 导入必要的模块（在函数内部导入，避免循环导入）
        from llm_langchain import util
        from zym.models import UserNotebook

        # 计算 HLScore（这是耗时操作）
        HLScore = util.imageSum_2_HLScore(content, base64_image)

        # 保存到数据库
        book_name = username[len(realName) + 1:]  # 去掉 "用户名_" 部分
        notebook = UserNotebook.objects.get(username=realName, bookName=book_name)

        # 读取现有的JSON数据
        try:
            existing_data = json.loads(notebook.MayImgDocHLScore) if notebook.MayImgDocHLScore else {}
        except json.JSONDecodeError:
            existing_data = {}

        # 更新JSON数据
        existing_data[key] = HLScore
        notebook.MayImgDocHLScore = json.dumps(existing_data, ensure_ascii=False)
        notebook.save()

        # 设置完成状态
        set_hlscore_status(key, 'completed', HLScore)

        print(f"HLScore 计算完成并保存: {username}/{filename}-{imgid}, 分数: {HLScore}")

    except Exception as e:
        # 设置失败状态
        set_hlscore_status(key, 'failed', str(e))
        print(f"异步计算 HLScore 失败: {username}/{filename}-{imgid}, 错误: {str(e)}")


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
    "9": "excel",  # Excel .xlsx
    "10": "excel",  # Excel .xls
    "11": "audio",  # 音频文件
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
    "9": "xlsx",  # Excel .xlsx
    "10": "xls",  # Excel .xls
    "11": "mp3",  # 音频文件默认后缀（实际以原文件扩展名为准）
}

QS_QQ_base = "请务必注意：当前的语境口吻为建议引导性回答，即不能直接回答用户的问题，而是通过" \
             "建议、反向发问等方式，引导用户深入思考，帮助用户通过自己的思考解决问题，" \
             "有助熵减式的个人能力提升，熵减程度提升顺序是QA→QS→QQ，即直接回答→建议→反问；" \
             "如果用户的提问本身是需要提出一些相关问题链，则此时你应该" \
             "给出更有引导价值、更有张力、更有深度思考价值的问题。请重视这个要求！"

# OPEN_AI_KEY = "[redacted]"
OPEN_AI_KEY = _public_config.secret('OPENAI_API_KEY')

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
- 控制每次"thinking"尽量不超过400字、每次"checking"不超过200字；如果思考和检查超过2轮就请停下来，承认自己无法解决并告知人类原因
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

# 用于存储带文档对话参数，作为临时存储状态的变量，保存提问后调用LLM前后端准备预备好的状态，由于各窗口回答后主窗口可能做综合，会覆盖chat_with_files_params
# 存下的状态，导致如果在此后再重做某个窗口的回答，会获取不到正确的状态
chat_with_files_params_tmp = {}

# 超时时间（秒）
time_out = 240

RANDOM_USER_NAME = 'gkjbkjbubuobklnb'

# 创建文件上传chat_upload全局线程池（根据CPU核心数动态设置）
# max_workers = min(4, (os.cpu_count() or 1) + 1)
file_processing_executor = ThreadPoolExecutor(max_workers=10)

# 创建物联API后台处理线程池
background_executor = ThreadPoolExecutor(max_workers=2)

# 🔥 修复方案2：限制同时处理的上传任务数量（防止资源耗尽）
from threading import Semaphore
MAX_CONCURRENT_UPLOADS = 5  # 最多5个并发上传
upload_semaphore = Semaphore(MAX_CONCURRENT_UPLOADS)
print(f"[INIT] 上传并发限制已设置: {MAX_CONCURRENT_UPLOADS}个同时上传")

# 会话存储
SESSION_STORE = {}
SESSION_TIMEOUT = 300  # 5分钟

# 重新指向的服务器路由配置文件路径
USER_REDIRECT_CONFIG_FILE = 'redirect_config.json'


def preprocess_data_before_async(data):
    """在异步上下文前预处理所有数据库操作"""
    # 处理FormData列表问题
    processed_data = {}
    for key, value in data.items():
        if isinstance(value, list) and len(value) == 1:
            processed_data[key] = value[0]
        else:
            processed_data[key] = value

    # 如果需要处理摘要，提前处理
    if processed_data.get("isSummaryUsed") == "true":
        message = processed_data["message"]
        username = processed_data["username"]
        realName = processed_data["realName"]

        # 执行 compose_message_with_summary 的逻辑
        from app_chat.models import BgCard
        from app_chat.bgcGenerate import summarize_scene

        sumContent = ""
        try:
            mysql_card = BgCard.objects.get(username=realName, status="3")
            sumContent = mysql_card.content
        except BgCard.DoesNotExist:
            realName = processed_data["realName"]
            userbookName = processed_data["userbookName"]
            sceneName = processed_data["sceneName"]
            bgc = summarize_scene(realName, sceneName)
            current_datetime = timezone.now()
            bg_card = BgCard(
                username=realName,
                name=sceneName + "场景背景摘要",
                detail=sceneName + "场景背景摘要",
                datetime=current_datetime,
                status="2"
            )
            bg_card.save()
            sumContent = bgc

        # 更新消息内容
        processed_data["message"] = "背景知识摘要：\n" + sumContent + "\n用户的请求或提问：\n" + message
        # 标记为已处理，避免重复处理
        processed_data["isSummaryUsed"] = "false"

    return processed_data


def stream_generator_sync(data):
    print("[DEBUG] 从前端获取到的数据:", data)

    # 【新增】在异步上下文之前预处理数据库操作
    data = preprocess_data_before_async(data)

    loop = asyncio.new_event_loop()
    print("[INFO] 创建模型回答事件循环")
    asyncio.set_event_loop(loop)

    # 根据 model_id 获取对应的处理器
    model_id = data["model_id"]

    # 列举一下所有的模型ID
    for model_name in model_manager.get_all_model_names():
        print("[DEBUG] 模型名称:", model_name)
        print("[DEBUG] 模型ID:", config_manager.get_model_id_by_name(model_name))

    cur_handler = model_manager.get_model_handler_by_id(model_id)
    # print("[DEBUG] cur_handler的类型:", type(cur_handler))
    print("[INFO] 当前申请流式输出的模型:", cur_handler.model_name)

    # 【新增】创建会话ID和中断事件
    username = data.get("username", "unknown")
    # 使用时间戳来生成唯一的session_id，避免在同步上下文中调用asyncio.current_task()
    timestamp = int(time.time() * 1000)  # 毫秒级时间戳
    session_id = f"{username}_{model_id}_{timestamp}"
    interrupt_event = interrupt_manager.create_session(session_id)

    # 【新增】发送session_id给前端（在第一个chunk中）
    session_data = {
        "type": "session_init",
        "session_id": session_id,
        "model_id": model_id,
        "content": ""
    }
    yield json.dumps(session_data, ensure_ascii=False)

    try:
        # 先判断是否为reasoner模型
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        generator = cur_handler.stream_generator(data, is_reasoner=is_reasoner)
        # if is_reasoner:
        #     generator = cur_handler.stream_generator_reasoner(data)
        # else:
        #     generator = cur_handler.stream_generator(data)

        chunk_count = 0
        while True:
            try:
                # 【新增】频繁检查中断状态（每个chunk都检查）
                if interrupt_manager.is_interrupted(session_id):
                    print(f"[中断] 响应被中断: {session_id}, 已输出chunk数: {chunk_count}")
                    # 发送中断消息给前端
                    interrupt_data = {
                        "type": "interrupt",
                        "message": "⚠️ 响应已被用户中断",
                        "session_id": session_id,
                        "content": ""
                    }
                    yield json.dumps(interrupt_data, ensure_ascii=False)
                    break

                # 【新增】检查超时（每100个chunk检查一次）
                if chunk_count % 100 == 0 and interrupt_manager.check_session_timeout(session_id, timeout_seconds=300):
                    print(f"[中断] 会话超时: {session_id}")
                    interrupt_manager.interrupt_session(session_id, force=True)
                    timeout_data = {
                        "type": "timeout",
                        "message": "⚠️ 响应超时，已自动中断",
                        "session_id": session_id,
                        "content": ""
                    }
                    yield json.dumps(timeout_data, ensure_ascii=False)
                    break

                chunk_count += 1
                yield loop.run_until_complete(generator.__anext__())  # .__anext__()
            except StopAsyncIteration:
                print(f"[完成] 迭代器结束，共输出 {chunk_count} 个chunk")
                break
    except Exception as e:
        print(f"[错误] 流式生成异常: {e}")
        error_data = {
            "type": "error",
            "message": f"响应生成出错: {str(e)}",
            "session_id": session_id,
            "content": ""
        }
        yield json.dumps(error_data, ensure_ascii=False)
    finally:
        # 【新增】清理会话资源
        print(f"[清理] 清理会话资源: {session_id}")
        interrupt_manager.cleanup_session(session_id)
        loop.close()


def stream_generator_sync_up(data):
    print("[DEBUG] 从前端获取到的数据:", data)

    # 【新增】在异步上下文之前预处理数据库操作
    data = preprocess_data_before_async(data)

    loop = asyncio.new_event_loop()
    print("[INFO] 创建模型回答事件循环")
    asyncio.set_event_loop(loop)

    # 根据 model_id 获取对应的处理器
    model_id = data["model_id"]

    # 列举一下所有的模型ID
    for model_name in model_manager.get_all_model_names():
        print("[DEBUG] 模型名称:", model_name)
        print("[DEBUG] 模型ID:", config_manager.get_model_id_by_name(model_name))

    cur_handler = model_manager.get_model_handler_by_id(model_id)
    # print("[DEBUG] cur_handler的类型:", type(cur_handler))
    print("[INFO] 当前申请流式输出的模型:", cur_handler.model_name)

    try:
        # 先判断是否为reasoner模型
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        generator = cur_handler.stream_generator(data, is_reasoner=is_reasoner)

        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())  # .__anext__()
            except StopAsyncIteration:
                print("[Debug] 迭代器结束")
                break
    finally:
        loop.close()


def stream_generator_sync_down(data):
    print("[DEBUG] 从前端获取到的数据:", data)

    # 【新增】在异步上下文之前预处理数据库操作
    data = preprocess_data_before_async(data)

    loop = asyncio.new_event_loop()
    print("[INFO] 创建模型回答事件循环")
    asyncio.set_event_loop(loop)

    # 根据 model_id 获取对应的处理器
    model_id = data["model_id"]

    # 列举一下所有的模型ID
    for model_name in model_manager.get_all_model_names():
        print("[DEBUG] 模型名称:", model_name)
        print("[DEBUG] 模型ID:", config_manager.get_model_id_by_name(model_name))

    cur_handler = model_manager.get_model_handler_by_id(model_id)
    # print("[DEBUG] cur_handler的类型:", type(cur_handler))
    print("[INFO] 当前申请流式输出的模型:", cur_handler.model_name)

    try:
        # 先判断是否为reasoner模型
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        generator = cur_handler.stream_generator(data, is_reasoner=is_reasoner)

        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())  # .__anext__()
            except StopAsyncIteration:
                print("[Debug] 迭代器结束")
                break
    finally:
        loop.close()


def stream_generator_sync_summa(data):
    print("[DEBUG] 从前端获取到的数据:", data)

    # Admin 场景槽：文档点摘要模型（覆盖前端写死的 model_id）
    try:
        from app_chat.scene_models import resolve_scene_model_id
        admin_mid = resolve_scene_model_id('doc_file_summary')
        if admin_mid:
            if hasattr(data, 'copy'):
                data = data.copy()
                data['model_id'] = admin_mid
            elif isinstance(data, dict):
                data = {**data, 'model_id': admin_mid}
            print(f"[SceneModels] doc_file_summary → model_id={admin_mid}")
    except Exception as e:
        print(f"[SceneModels] doc_file_summary 解析失败，沿用请求 model_id: {e}")

    # 【新增】在异步上下文之前预处理数据库操作
    # data = preprocess_data_before_async(data)

    loop = asyncio.new_event_loop()
    print("[INFO] 创建模型回答事件循环")
    asyncio.set_event_loop(loop)

    # 根据 model_id 获取对应的处理器
    model_id = data["model_id"]

    # 列举一下所有的模型ID
    for model_name in model_manager.get_all_model_names():
        print("[DEBUG] 模型名称:", model_name)
        print("[DEBUG] 模型ID:", config_manager.get_model_id_by_name(model_name))

    cur_handler = model_manager.get_model_handler_by_id(model_id)
    # print("[DEBUG] cur_handler的类型:", type(cur_handler))
    print("[INFO] 当前申请流式输出的模型:", cur_handler.model_name)

    try:
        # 先判断是否为reasoner模型
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        generator = cur_handler.stream_generator_summa(data, is_reasoner=is_reasoner)

        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())  # .__anext__()
            except StopAsyncIteration:
                print("[Debug] 迭代器结束")
                break
    finally:
        loop.close()


def stream_generator_sync_rate(data):
    print("[DEBUG] 从前端获取到的数据:", data)

    # Admin 场景槽：建卡红蓝浅评模型（覆盖前端写死的 model_id）
    try:
        from app_chat.scene_models import resolve_scene_model_id
        admin_mid = resolve_scene_model_id('card_shallow_rate')
        if admin_mid:
            if hasattr(data, 'copy'):
                data = data.copy()
                data['model_id'] = admin_mid
            elif isinstance(data, dict):
                data = {**data, 'model_id': admin_mid}
            print(f"[SceneModels] card_shallow_rate → model_id={admin_mid}")
    except Exception as e:
        print(f"[SceneModels] card_shallow_rate 解析失败，沿用请求 model_id: {e}")

    # 【新增】在异步上下文之前预处理数据库操作
    # data = preprocess_data_before_async(data)

    loop = asyncio.new_event_loop()
    print("[INFO] 创建模型回答事件循环")
    asyncio.set_event_loop(loop)

    # 根据 model_id 获取对应的处理器
    model_id = data["model_id"]

    # 列举一下所有的模型ID
    for model_name in model_manager.get_all_model_names():
        print("[DEBUG] 模型名称:", model_name)
        print("[DEBUG] 模型ID:", config_manager.get_model_id_by_name(model_name))

    cur_handler = model_manager.get_model_handler_by_id(model_id)
    # print("[DEBUG] cur_handler的类型:", type(cur_handler))
    print("[INFO] 当前申请流式输出的模型:", cur_handler.model_name)

    try:
        # 先判断是否为reasoner模型
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        generator = cur_handler.stream_generator_rate(data, is_reasoner=is_reasoner)

        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())  # .__anext__()
            except StopAsyncIteration:
                print("[Debug] 迭代器结束")
                break
    finally:
        loop.close()


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
        - 意境优美而不失亲和，可适当运用一些富有画面感和故事性的意象

        3. 情感共鸣
        - 体察用户当下可能的身心状态
        - 用声音传递理解与关怀
        - 在适当时候给予温暖鼓励
        - 营造轻松愉悦的氛围

        4. 内容建构
        - 巧妙融入用户的研究主题并提供一些扩展延伸或深化的灵感，但不可牵强附会，一定要是自然通达的
        - 循序渐进地展开内容，段落之间的衔接流畅
        - 注重逻辑连贯与层次感
        - 适时留白，给予思考空间；也可适当加入一些趣味性内容
        - 结尾要自然收束，给人回味

        请以这些为目标，结合用户背景，创作一段与当下时间相契合、打动人心、富有温度的播报内容，但注意不可以太浮夸或过度使用比喻等使得文字失去内涵价值。'''

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
    # ------------------------------基本参数设置Start--------------------------------
    data = json.loads(request.body)
    username = data["username"]
    model_id = data["modelID"]
    rounds = int(data["rounds"])
    originRealName = data.get("originRealName", "")
    if originRealName != "":
        name2lock = originRealName
    else:
        name2lock = username
    print("[chat_sendParams]:" + name2lock)

    global params_count, chat_with_files_params, chat_content, last_segments

    global_lock[name2lock].acquire()
    model_names = model_manager.get_all_model_names()

    if name2lock not in chat_content:
        chat_content[name2lock] = {}
        for model in model_names:
            chat_content[name2lock][model] = "此模型您已暂时关闭使用"

    print(f"windowId: {data['windowId']}")
    if data['windowId'] == 'left':
        for key in chat_content[name2lock]:
            chat_content[name2lock][key] = "此模型您已暂时关闭使用"

    if name2lock not in chat_with_files_params:
        chat_with_files_params[name2lock] = {}

    if name2lock not in chat_with_files_params_tmp:
        chat_with_files_params_tmp[name2lock] = {}

    if name2lock not in last_question:
        last_question[name2lock] = ''

    if name2lock not in last_segments:
        last_segments[name2lock] = []

    # ------------------------------基本参数设置End--------------------------------

    # ------------------------------文件列表信息更新Start--------------------------------

    def _parse_int_list(raw_value):
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            out = []
            for item in raw_value:
                try:
                    out.append(int(item))
                except Exception:
                    continue
            return out
        text = str(raw_value).strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                out = []
                for item in parsed:
                    try:
                        out.append(int(item))
                    except Exception:
                        continue
                return out
        except Exception:
            pass
        out = []
        for item in text.split(','):
            item = str(item).strip()
            if not item:
                continue
            try:
                out.append(int(item))
            except Exception:
                continue
        return out

    def _looks_like_complete_filename(name: str) -> bool:
        return bool(re.search(r'\.(pdf|doc|docx|ppt|pptx|xls|xlsx|txt|md|png|jpg|jpeg|webp|bmp|gif|zip|mp3)$',
                              str(name or '').strip(), flags=re.IGNORECASE))

    def _parse_filename_list(raw_value, expected_count: int = 0):
        if raw_value is None:
            return []
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]
        text = str(raw_value).strip()
        if not text:
            return []
        # 优先支持 JSON 数组字符串（前端可逐步切到该格式）
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except Exception:
            pass

        # 兼容历史逗号拼接：尽量把“文件名中逗号”重新拼回去
        tokens = [seg.strip() for seg in text.split(',')]
        tokens = [seg for seg in tokens if seg]
        if not tokens:
            return []
        merged = []
        cur = ''
        for seg in tokens:
            cur = f'{cur},{seg}' if cur else seg
            if _looks_like_complete_filename(cur):
                merged.append(cur)
                cur = ''
        if cur:
            merged.append(cur)
        # 若重组后数量不对，保守回退到原 split，避免误并
        if expected_count and len(merged) != expected_count:
            return tokens
        return merged

    if 'message' in data and 'filenamelist' in data and 'rightSelectList' in data and 'isHistoryUsed' in data:
        message = data["message"]
        last_question[name2lock] = message
        fileNameList = data["filenamelist"]
        rightSelectList = data["rightSelectList"]
        isHistoryUsed = data["isHistoryUsed"]

        # 🔥 获取核心关键词（如果使用了tab增强后的问题）
        core_keyword = data.get("coreKeyword", None)
        if core_keyword:
            print(f"[chat_sendParams] 接收到核心关键词: {core_keyword}")

        cross_notebook_context_on = str(data.get('crossNotebookContext', '')).lower() in ('true', '1', 'yes')
        if cross_notebook_context_on:
            print('[chat_sendParams] 跨本子关联已开启')

        pinned_cross_notebooks = None
        pinned_raw = data.get('pinnedCrossNotebooks') or data.get('pinned_cross_notebooks')
        if pinned_raw:
            try:
                if isinstance(pinned_raw, str) and pinned_raw.strip():
                    pinned_cross_notebooks = json.loads(pinned_raw)
                elif isinstance(pinned_raw, list):
                    pinned_cross_notebooks = pinned_raw
                if pinned_cross_notebooks:
                    print(f'[chat_sendParams] 用户勾选跨本本子: {pinned_cross_notebooks}')
            except Exception as e:
                print(f'[chat_sendParams] 解析 pinnedCrossNotebooks 失败: {e}')
                pinned_cross_notebooks = None

        history = False
        if isHistoryUsed == "true" and chat_history_used != {}:
            history = True
        # file_list = fileNameList.split(',') if fileNameList else []
        # right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []
        right_select_list = _parse_int_list(rightSelectList)
        file_list = _parse_filename_list(fileNameList, expected_count=len(right_select_list))
        print(
            f"[chat_sendParams][debug] docs_count={len(file_list)} "
            f"segment_way_count={len(right_select_list)} "
            f"docs={file_list[:8]} ways={right_select_list[:8]}"
        )

        segments = []
        rag_search_time = 0  # RAG搜索用时（秒）
        cross_notebook_citation_prefix = ''

        # ── 语义反问判定（deepseek-v4-flash）────────────────────────────
        # 按「对话轮次」计：同一轮多窗口共用同一 message，后端去重只计一次。
        # 慢思考 iteration：不重判；若首答为反问，则延续并加深反问。
        # merge：清除反问约束，避免综合合并被改成只反问。
        from concurrent.futures import ThreadPoolExecutor
        from app_chat.socratic_probe import (
            preserve_socratic_for_iteration,
            publish_round_socratic_probe,
            resolve_round_socratic_probe,
            run_socratic_probe,
            store_socratic_probe_on_params,
        )
        from app_chat.skill_router import run_skill_select
        from app_chat.rag_structure_scope import (
            should_locate_structure_scope,
            run_structure_scope_locate,
        )

        req_mode = str(data.get('mode') or 'normal').strip().lower()
        req_window_id = str(data.get('windowId') or data.get('window_id') or 'left').strip() or 'left'
        # 勾选列表：RAG 不含 zip；Skill 候选用完整 file_list（含 zip）
        file_list_all = list(file_list or [])
        file_list = [f for f in file_list_all if not str(f).lower().endswith('.zip')]
        # 杨谦：所选材料若有已完成批改，供 RAG 参考（与 RAG 文档列表一致，不含 zip）
        from app_chat.homework_grading.grading_rag import inspect_selection, cache_matches
        grading_selection = inspect_selection(username, file_list)
        grading_cache_key = grading_selection['cache_key']
        grading_context_status = []
        has_docs = bool(file_list)
        # 前端「是否启用反问」：关闭则不调用 DS 判定
        _socratic_flag = str(
            data.get('isSocraticProbeUsed')
            or data.get('socraticProbeEnabled')
            or 'false'
        ).strip().lower()
        socratic_enabled = _socratic_flag in ('true', '1', 'yes', 'on')
        socratic_future = None
        skill_future = None
        structure_future = None
        structure_scope_result = None
        page_scopes_for_rag = None
        structure_plans_for_rag = None
        structure_map_prompt = ''
        socratic_probe_result = None
        skill_select_result = None
        _socratic_pool = None
        prev_socratic = {}
        try:
            # 迭代时优先取「本轮原问题」已发布的共享判定，保证多窗口一致
            _bound_for_prev = ''
            if req_mode == 'iteration':
                _bound_for_prev = str(
                    data.get('socraticBoundMessage')
                    or data.get('originalQuestion')
                    or ''
                ).strip()
            if _bound_for_prev:
                prev_socratic = resolve_round_socratic_probe(
                    owner_keys=[name2lock, username],
                    bound_message=_bound_for_prev,
                    prefer_mode='normal',
                ) or {}
            if not prev_socratic and isinstance(chat_with_files_params.get(name2lock), dict):
                prev_socratic = dict(chat_with_files_params[name2lock].get('socratic_probe') or {})
            if (not prev_socratic) and isinstance(chat_with_files_params_tmp.get(name2lock), dict):
                prev_socratic = dict(chat_with_files_params_tmp[name2lock].get('socratic_probe') or {})
        except Exception:
            prev_socratic = {}

        if not socratic_enabled:
            socratic_probe_result = {
                'ok': True,
                'should_counter_ask': False,
                'decision': '否',
                'skipped_rejudge': True,
                'skip_reason': 'user_disabled',
                'phase': 'user_disabled',
                'instruction': '',
            }
            print(
                f'[chat_sendParams] 用户关闭反问判定 window={req_window_id} mode={req_mode}：跳过 DS',
                flush=True,
            )
            if has_docs:
                _probe_message = str(data.get('socraticBoundMessage') or message or '').strip() or message
                _need_scope = should_locate_structure_scope(_probe_message, file_list)
                _socratic_pool = ThreadPoolExecutor(max_workers=2 if _need_scope else 1)
                skill_future = _socratic_pool.submit(
                    run_skill_select,
                    username,
                    _probe_message,
                    file_list_all,
                    mode=req_mode,
                )
                if _need_scope:
                    structure_future = _socratic_pool.submit(
                        run_structure_scope_locate,
                        username,
                        _probe_message,
                        file_list,
                    )
            else:
                _probe_message = str(data.get('socraticBoundMessage') or message or '').strip() or message
                try:
                    skill_select_result = run_skill_select(
                        username, _probe_message, file_list_all, mode=req_mode,
                    )
                except Exception as _sk_e:
                    print(f'[chat_sendParams] skill_select 失败: {_sk_e}', flush=True)
                    skill_select_result = {'ok': False, 'selected_skills': [], 'injection_block': ''}
        elif req_mode == 'iteration':
            # 慢思考二次迭代：不重判；首答为反问则延续并加深反问
            socratic_probe_result = preserve_socratic_for_iteration(prev_socratic, mode=req_mode)
            print(
                f'[chat_sendParams] mode=iteration window={req_window_id}：不重判，'
                f'should_counter_ask={socratic_probe_result.get("should_counter_ask")} '
                f'phase={socratic_probe_result.get("phase")}',
                flush=True,
            )
            # 迭代仍可能问「第x章」：与选 Skill 无关，单独并发定位
            if has_docs:
                _probe_message = str(data.get('socraticBoundMessage') or message or '').strip() or message
                if should_locate_structure_scope(_probe_message, file_list):
                    _socratic_pool = ThreadPoolExecutor(max_workers=1)
                    structure_future = _socratic_pool.submit(
                        run_structure_scope_locate,
                        username,
                        _probe_message,
                        file_list,
                    )
        elif req_mode == 'merge':
            # 综合合并不应继承「只反问」约束，避免把合并答案强行改成反问
            socratic_probe_result = {
                'ok': True,
                'should_counter_ask': False,
                'decision': '否',
                'skipped_rejudge': True,
                'skip_reason': 'merge',
                'phase': 'merge_clear',
                'instruction': '',
            }
            print('[chat_sendParams] mode=merge：清除语义反问约束', flush=True)
            # merge 仍可能做 RAG：章/节问题照样定位收窄
            if has_docs:
                _probe_message = str(data.get('socraticBoundMessage') or message or '').strip() or message
                if should_locate_structure_scope(_probe_message, file_list):
                    _socratic_pool = ThreadPoolExecutor(max_workers=1)
                    structure_future = _socratic_pool.submit(
                        run_structure_scope_locate,
                        username,
                        _probe_message,
                        file_list,
                    )
        elif has_docs:
            _probe_message = str(data.get('socraticBoundMessage') or message or '').strip() or message
            _need_scope = should_locate_structure_scope(_probe_message, file_list)
            _socratic_pool = ThreadPoolExecutor(max_workers=3 if _need_scope else 2)
            socratic_future = _socratic_pool.submit(
                run_socratic_probe,
                username=username,
                message=_probe_message,
                name2lock=name2lock,
                file_list=file_list,
                prev_question=str(data.get('socraticPrevQuestion') or ''),
                prev_answer=str(data.get('socraticPrevAnswer') or ''),
            )
            skill_future = _socratic_pool.submit(
                run_skill_select,
                username,
                _probe_message,
                file_list_all,
                mode=req_mode,
            )
            if _need_scope:
                structure_future = _socratic_pool.submit(
                    run_structure_scope_locate,
                    username,
                    _probe_message,
                    file_list,
                )
        else:
            print('[chat_sendParams] 无勾选文档：先执行语义反问判定', flush=True)
            _probe_message = str(data.get('socraticBoundMessage') or message or '').strip() or message
            socratic_probe_result = run_socratic_probe(
                username=username,
                message=_probe_message,
                name2lock=name2lock,
                file_list=[],
                prev_question=str(data.get('socraticPrevQuestion') or ''),
                prev_answer=str(data.get('socraticPrevAnswer') or ''),
            )
            # 无 PDF 但可能勾了 Skill zip
            try:
                skill_select_result = run_skill_select(
                    username, _probe_message, file_list_all, mode=req_mode,
                )
            except Exception as _sk_e:
                print(f'[chat_sendParams] skill_select 失败: {_sk_e}', flush=True)
                skill_select_result = {'ok': False, 'selected_skills': [], 'injection_block': ''}

        try:
            if not has_docs:
                # 无勾选文档：不做 RAG；避免空 file_list 仍走进 get_docs_all_split 打出误导日志
                segments = []
                rag_search_time = 0
                cross_notebook_citation_prefix = ''
                last_segments[name2lock] = segments
                print('[chat_sendParams] 无勾选文档：跳过文档分割/RAG', flush=True)
            else:
                # 章/节定位：必须在 RAG 前拿到（与 skill_select 并发，不挡选 Skill）
                if structure_future is not None:
                    try:
                        structure_scope_result = structure_future.result(timeout=25)
                        page_scopes_for_rag = (structure_scope_result or {}).get('page_scopes')
                        structure_plans_for_rag = (structure_scope_result or {}).get('plans') or None
                        structure_map_prompt = (structure_scope_result or {}).get('map_prompt') or ''
                        print(
                            f'[chat_sendParams] RAG 页码收窄: '
                            f'triggered={(structure_scope_result or {}).get("triggered")} '
                            f'scopes={page_scopes_for_rag} '
                            f'plans={len(structure_plans_for_rag or [])}',
                            flush=True,
                        )
                    except Exception as _sc_e:
                        print(f'[chat_sendParams] structure_scope 失败，RAG 不收窄: {_sc_e}', flush=True)
                        structure_scope_result = {'ok': False, 'note': str(_sc_e)}
                        page_scopes_for_rag = None
                        structure_plans_for_rag = None
                        structure_map_prompt = ''

                # 🔥 缓存key需要包含core_keyword，确保关键词变化时重新搜索
                cache_key_core_keyword = chat_with_files_params[name2lock].get("core_keyword") if chat_with_files_params[name2lock] else None
                cache_key_cross_nb = chat_with_files_params[name2lock].get("cross_notebook_context") if chat_with_files_params[name2lock] else None
                cache_key_pinned_nb = chat_with_files_params[name2lock].get("pinned_cross_notebooks") if chat_with_files_params[name2lock] else None
                cache_key_page_scopes = chat_with_files_params[name2lock].get("page_scopes") if chat_with_files_params[name2lock] else None
                cache_key_plans = chat_with_files_params[name2lock].get("structure_plans") if chat_with_files_params[name2lock] else None
                if chat_with_files_params[name2lock] == {} or chat_with_files_params[name2lock]["file_list"] != file_list or \
                        chat_with_files_params[name2lock]["get_way"] != right_select_list or chat_with_files_params[name2lock][
                    "question"] != message or (core_keyword != cache_key_core_keyword) or (
                    cross_notebook_context_on != cache_key_cross_nb) or (pinned_cross_notebooks != cache_key_pinned_nb) or (
                    page_scopes_for_rag != cache_key_page_scopes) or (
                    structure_plans_for_rag != cache_key_plans) or (
                    not cache_matches(chat_with_files_params[name2lock], grading_selection)):
                    print('开始分割文档')
                    # 记录RAG搜索开始时间
                    rag_start_time = time.time()

                    # 这里用作者username去获取存储的相关向量数据
                    segments = util.get_docs_all_split(
                        user_name=username,
                        docs_name_list=file_list,
                        segment_get_way_list=right_select_list,
                        text_for_search=message,
                        core_keyword=core_keyword,  # 🔥 传递核心关键词
                        page_scopes=page_scopes_for_rag,
                        structure_plans=structure_plans_for_rag,
                        grading_selection=grading_selection,
                    )
                    grading_context_status = grading_selection.get('result_status', [])
                    if structure_map_prompt:
                        from langchain_core.documents import Document as _MapDoc
                        map_doc = _MapDoc(
                            page_content=(
                                "以下是本题所涉文档的目录结构（DocStructure），"
                                "用于把握全书/全章位置，不是正文证据：\n"
                                + structure_map_prompt
                            ),
                            metadata={"type": "doc_structure_map", "source": "doc_structure"},
                        )
                        if segments and isinstance(segments[0], list):
                            segments.insert(0, [map_doc])
                        else:
                            segments = [[map_doc]]

                    # 计算RAG搜索用时
                    rag_end_time = time.time()
                    rag_search_time = round(rag_end_time - rag_start_time, 2)
                    print(f'文档分割完毕，RAG搜索用时: {rag_search_time}s, segments: {segments}')
                    last_segments[name2lock] = segments

                    cross_notebook_citation_prefix = ''
                    if cross_notebook_context_on:
                        from app_chat.cross_notebook_context import append_cross_notebook_segments
                        segments, cross_notebook_citation_prefix = append_cross_notebook_segments(
                            segments, username, message,
                            core_keyword=core_keyword,
                            origin_real_name=data.get('originRealName') or name2lock,
                            current_file_list=file_list,
                            manual_notebook_usernames=pinned_cross_notebooks,
                        )
                        last_segments[name2lock] = segments
                else:
                    segments = last_segments[name2lock]
                    grading_context_status = chat_with_files_params[name2lock].get('grading_context_status', [])
                    cross_notebook_citation_prefix = chat_with_files_params[name2lock].get('cross_notebook_citation_prefix', '')
                    # 从缓存中恢复RAG搜索时间
                    if name2lock in chat_with_files_params and 'rag_search_time' in chat_with_files_params[name2lock]:
                        rag_search_time = chat_with_files_params[name2lock]['rag_search_time']
                        print(f'使用缓存的文档分割结果，恢复RAG搜索时间: {rag_search_time}s')
                    else:
                        rag_search_time = 0
                        print('使用缓存的文档分割结果，RAG搜索时间为0')

                if socratic_future is not None:
                    try:
                        socratic_probe_result = socratic_future.result(timeout=35)
                    except Exception as _socratic_e:
                        print(f'[chat_sendParams] 语义反问判定并行等待失败: {_socratic_e}', flush=True)
                        socratic_probe_result = {
                            'ok': False,
                            'should_counter_ask': False,
                            'decision': '否',
                            'error': str(_socratic_e)[:200],
                        }
                if skill_future is not None:
                    try:
                        skill_select_result = skill_future.result(timeout=35)
                    except Exception as _skill_e:
                        print(f'[chat_sendParams] Skill 选择并行等待失败: {_skill_e}', flush=True)
                        skill_select_result = {
                            'ok': False,
                            'selected_skills': [],
                            'injection_block': '',
                            'error': str(_skill_e)[:200],
                        }
        finally:
            if _socratic_pool is not None:
                try:
                    _socratic_pool.shutdown(wait=False)
                except Exception:
                    pass

        # iteration/merge：不注入 Skill
        if req_mode in ('iteration', 'merge'):
            skill_select_result = {
                'ok': True,
                'skipped': True,
                'skip_reason': req_mode,
                'selected_skills': [],
                'injection_block': '',
            }
            print(f'[Skill] 本轮选用: (skipped: {req_mode})', flush=True)
        elif skill_select_result is None:
            skill_select_result = {'ok': True, 'selected_skills': [], 'injection_block': ''}

        # 反问轮：降为 description 级注入
        try:
            from app_chat.skill_router import build_injection_block
            if (
                isinstance(skill_select_result, dict)
                and skill_select_result.get('selected_skills')
                and (socratic_probe_result or {}).get('should_counter_ask')
            ):
                skill_select_result['injection_block'] = build_injection_block(
                    username,
                    skill_select_result.get('selected_skills') or [],
                    counter_ask=True,
                )
        except Exception as _inj_e:
            print(f'[chat_sendParams] Skill 反问降级注入失败: {_inj_e}', flush=True)

        # 这里也用作者username去获取文件夹里存储的勾选Cards的可能图片base64
        base64_images = []
        if 'choosedCardIdList' in data and data['choosedCardIdList']:
            # 如果勾选了卡片问答，存在choosedCardIdList，拆分choosedCardIdList字符串为列表
            CardIndexList = data['choosedCardIdList'].split(',')
            base64_images = get_possible_cardImgs_base64_byIds(username, CardIndexList)

        # 保留各消息的语义反问镜像，避免 construct 整表覆盖
        _prev_socratic_by_message = {}
        try:
            if isinstance(chat_with_files_params.get(name2lock), dict):
                _prev = chat_with_files_params[name2lock].get('socratic_by_message')
                if isinstance(_prev, dict):
                    _prev_socratic_by_message = dict(_prev)
        except Exception:
            _prev_socratic_by_message = {}

        chat_with_files_params[name2lock] = construct_file_data_normal(
            segments=segments,
            user_name=username,
            file_list=file_list,
            get_way=right_select_list,
            question=message,
            history=history,
            origin_real_name=name2lock,
            base64_images=base64_images,
            rounds=rounds,
            cross_notebook_citation_prefix=cross_notebook_citation_prefix if cross_notebook_context_on else None,
        )
        from app_chat.homework_grading.grading_rag import apply_reference_policy
        apply_reference_policy(chat_with_files_params[name2lock], grading_context_status)
        if _prev_socratic_by_message:
            chat_with_files_params[name2lock]['socratic_by_message'] = _prev_socratic_by_message
        # 🔥 保存核心关键词到缓存
        if core_keyword:
            chat_with_files_params[name2lock]["core_keyword"] = core_keyword
        chat_with_files_params[name2lock]["cross_notebook_context"] = cross_notebook_context_on
        chat_with_files_params[name2lock]["pinned_cross_notebooks"] = pinned_cross_notebooks
        if cross_notebook_context_on:
            chat_with_files_params[name2lock]["cross_notebook_citation_prefix"] = cross_notebook_citation_prefix

        # Skill 选择结果：只写在 name2lock（组本下是协作者个人键）
        # 禁止写到共享 username，否则 uzi/uzi2 同开时会互相覆盖对方的 injection
        try:
            chat_with_files_params[name2lock]['skill_select'] = skill_select_result or {}
            chat_with_files_params[name2lock]['skill_injection'] = (skill_select_result or {}).get('injection_block') or ''
            chat_with_files_params[name2lock]['checked_files_all'] = file_list_all
            if isinstance(chat_with_files_params_tmp.get(name2lock), dict):
                chat_with_files_params_tmp[name2lock]['skill_select'] = skill_select_result or {}
                chat_with_files_params_tmp[name2lock]['skill_injection'] = (
                    (skill_select_result or {}).get('injection_block') or ''
                )
                chat_with_files_params_tmp[name2lock]['checked_files_all'] = file_list_all
        except Exception:
            pass

        # 添加RAG搜索用时到params中
        chat_with_files_params[name2lock]['rag_search_time'] = rag_search_time
        chat_with_files_params[name2lock]['page_scopes'] = page_scopes_for_rag
        chat_with_files_params[name2lock]['structure_plans'] = structure_plans_for_rag
        chat_with_files_params[name2lock]['grading_cache_key'] = grading_cache_key
        chat_with_files_params[name2lock]['grading_context_status'] = grading_context_status
        if structure_scope_result is not None:
            chat_with_files_params[name2lock]['structure_scope'] = {
                'triggered': (structure_scope_result or {}).get('triggered'),
                'scopes': (structure_scope_result or {}).get('scopes') or [],
                'note': (structure_scope_result or {}).get('note') or '',
            }
        print(f"[DEBUG] chat_sendParams - 存储RAG时间到chat_with_files_params[{name2lock}]: {rag_search_time}s")

        # 语义反问判定结果：按「原问题」发布共享，主辅窗口同轮必须一致
        if socratic_probe_result is None:
            socratic_probe_result = {
                'ok': False,
                'should_counter_ask': False,
                'decision': '否',
            }
        _bound_msg = message
        if req_mode == 'iteration':
            _bound_msg = str(
                data.get('socraticBoundMessage')
                or prev_socratic.get('bound_message')
                or prev_socratic.get('current_question')
                or ''
            ).strip() or message
        else:
            # normal/merge：与判定用同一原问题绑定，保证多窗口读到同一份
            _bound_msg = str(data.get('socraticBoundMessage') or message or '').strip() or message
        _skip_socratic_store = False
        if req_mode == 'iteration':
            # 迭代不重写共享首轮判定，只在 stream 读取时加深，避免辅窗口首答读到「迭代加深」文案
            _skip_socratic_store = True
            print(
                f'[chat_sendParams] mode=iteration window={req_window_id}：沿用共享首轮判定，不覆盖发布',
                flush=True,
            )
        if not _skip_socratic_store:
            publish_round_socratic_probe(
                owner_keys=[name2lock, username],
                bound_message=_bound_msg,
                probe=socratic_probe_result,
                mode=req_mode,
            )
            store_socratic_probe_on_params(
                chat_with_files_params[name2lock],
                probe=socratic_probe_result,
                bound_message=_bound_msg,
                mode=req_mode,
                window_id=req_window_id,
            )
            try:
                if username and username != name2lock and isinstance(chat_with_files_params.get(username), dict):
                    store_socratic_probe_on_params(
                        chat_with_files_params[username],
                        probe=socratic_probe_result,
                        bound_message=_bound_msg,
                        mode=req_mode,
                        window_id=req_window_id,
                    )
            except Exception:
                pass
        print(
            f"[DEBUG] chat_sendParams - socratic_probe window={req_window_id} decision="
            f"{socratic_probe_result.get('decision')} "
            f"should_counter_ask={socratic_probe_result.get('should_counter_ask')} "
            f"forced={socratic_probe_result.get('forced_by_streak')} "
            f"streak={socratic_probe_result.get('streak_before')}->{socratic_probe_result.get('streak_after')} "
            f"bound_len={len(_bound_msg)} skip_store={_skip_socratic_store}",
            flush=True,
        )

        if data["mode"] != "merge":
            chat_with_files_params_tmp[name2lock] = chat_with_files_params[name2lock]

        print(
            f"[DEBUG: chat_sendParams] 更新后的chat_with_files_params[question_with_history]: {chat_with_files_params[name2lock]['question_with_history']}")

    # ------------------------------文件列表信息更新End--------------------------------

    # ------------------------------前端参数传递Start--------------------------------

    modelID = data['modelID']
    params = data["params"]
    print("前端传来的参数是：" + params)
    # param_dict = json.loads(params)
    params_dict = json.loads(params)

    # param_dict_GPT4 = params_dict['GPT4']
    # param_dict_Mixtral = params_dict['Mixtral']
    # param_dict_Kimi = params_dict['Kimi']
    # param_dict_llama3 = params_dict['llama3']
    # param_dict_Claude = params_dict['Claude']
    # param_dict_Deepseek = params_dict['Deepseek']
    # param_dict_Gemini = params_dict['Gemini']
    # param_dict_Qwq = params_dict['Qwq']

    print("模型ID：" + modelID)

    if modelID == '1000':
        # 保存所有模型的参数
        # 更新config_manager中的所有超参数
        for key, value in params_dict.items():
            # 先根据key获取对应的模型ID
            model_id = config_manager.get_model_id_by_name(key)
            # 然后调用update_model_hyper_para(self, model_id: str, hyper_para_dict: Dict[str, float])方法更新超参数
            config_manager.update_model_hyper_para(model_id, value)
            # 打印参数更新前后的值
            print(f"[INFO] {key}的参数更新前的值为：{config_manager.get_model_hyper_para(model_id)}")
            print(f"[INFO] {key}的参数更新后的值为：{value}")
    else:
        model_name = config_manager.get_model_name_by_id(model_id)
        params = params_dict[model_name]
        config_manager.update_model_hyper_para(model_id, params)

    print("后端设置当时几个模型的参数")

    # if modelID == '1000':
    #     global_var.save_config('1002', **param_dict_GPT4)
    #     global_var.save_config('1003', **param_dict_Mixtral)
    #     global_var.save_config('1004', **param_dict_Kimi)
    #     global_var.save_config('1005', **param_dict_llama3)
    #     global_var.save_config('1006', **param_dict_Claude)
    #     global_var.save_config('1007', **param_dict_Deepseek)
    #     global_var.save_config('1008', **param_dict_Deepseek)
    #     global_var.save_config('1009', **param_dict_Gemini)
    #     global_var.save_config('1010', **param_dict_Qwq)
    # if modelID == '1002':
    #     global_var.save_config(modelID, **param_dict_GPT4)
    #     # global_var.save_gpt4_config(**param_dict_GPT4)
    # if modelID == '1003':
    #     global_var.save_config(modelID, **param_dict_Mixtral)
    #     # global_var.save_mixtral_config(**param_dict_Mixtral)
    # if modelID == '1004':
    #     global_var.save_config(modelID, **param_dict_Kimi)
    #     # global_var.save_kimi_config(**param_dict_Kimi)
    # if modelID == '1005':
    #     global_var.save_config(modelID, **param_dict_llama3)
    #     # global_var.save_llama3_config(**param_dict_llama3)
    # if modelID == '1006':
    #     global_var.save_config(modelID, **param_dict_Claude)
    # if modelID == '1007':
    #     global_var.save_config(modelID, **param_dict_Deepseek)
    # if modelID == '1008':
    #     global_var.save_config(modelID, **param_dict_Deepseek)
    # if modelID == '1009':
    #     global_var.save_config(modelID, **param_dict_Gemini)
    # if modelID == '1010':
    #     global_var.save_config(modelID, **param_dict_Qwq)

    # print("后端设置当时几个模型的参数")
    # # print(global_var.timeConfigGPT4)
    # # print(global_var.timeConfigMixtral)
    # # print(global_var.timeConfigKimi)
    # # print(global_var.timeConfigLlama3)

    # print(global_var.config)
    # print(global_var.mixtralConfig)
    # print(global_var.kimiConfig)
    # print(global_var.llama3Config)
    # print(global_var.claudeConfig)
    # ------------------------------前端参数传递End--------------------------------

    response = {}
    content = ""

    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0

    response['grading_context_status'] = chat_with_files_params.get(name2lock, {}).get('grading_context_status', [])
    # 回传本轮语义反问判定，供前端慢思考决定是否跳过深评/迭代
    try:
        _probe = {}
        if name2lock in chat_with_files_params and isinstance(chat_with_files_params[name2lock], dict):
            _probe = chat_with_files_params[name2lock].get('socratic_probe') or {}
        response['socratic_should_counter_ask'] = bool(_probe.get('should_counter_ask'))
        response['socratic_decision'] = _probe.get('decision') or '否'
        response['socratic_analysis'] = (_probe.get('analysis') or '')[:80]
        response['socratic_forced_by_streak'] = bool(_probe.get('forced_by_streak'))
    except Exception:
        response['socratic_should_counter_ask'] = False
        response['socratic_decision'] = '否'
        response['socratic_analysis'] = ''
        response['socratic_forced_by_streak'] = False

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
                # api_key='[redacted]',
                api_key=_public_config.secret('OPENAI_API_KEY'),
                base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
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
            print(f"[PROMPT_DEBUG][Gemini][no_file] username={username}, useSystemPrompt={useSystemPrompt}")
            print(f"[PROMPT_DEBUG][GPT4][no_file] username={username}, useSystemPrompt={useSystemPrompt}")
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
        print(f"[PROMPT_DEBUG][GPT4][with_file] username={username}, useSystemPrompt={useSystemPrompt}")
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
                api_key=_public_config.secret('OPENAI_API_KEY'),
                base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
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
        print(f"[PROMPT_DEBUG][Gemini][with_file] username={username}, useSystemPrompt={useSystemPrompt}")
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
                api_key=_public_config.secret('OPENAI_API_KEY'),
                base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
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
            print(f"[PROMPT_DEBUG][Claude][no_file] username={username}, useSystemPrompt={useSystemPrompt}")
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
        print(f"[PROMPT_DEBUG][Claude][with_file] username={username}, useSystemPrompt={useSystemPrompt}")
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
            API_KEY = _public_config.secret('DEEPSEEK_API_KEY')
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
                print(f"[PROMPT_DEBUG][Deepseek][no_file] username={username}, role={role}")
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
        print(f"[PROMPT_DEBUG][Deepseek][with_file] username={username}, useSystemPrompt={useSystemPrompt}")
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
            api_key=_public_config.secret('NVIDIA_API_KEY')
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
                api_key=_public_config.secret('KIMI_API_KEY'),
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
                    model='kimi-k3',
                    messages=[
                        {"role": "system", "content": useSystemPrompt},
                        {"role": "user", "content": constructed_data["questionKimi"]},
                    ],
                    temperature=1.0,
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
            # API_KEY = '[redacted]'
            API_KEY_ALI = _public_config.secret('NKCN_LLM_DASHSCOPE_API_KEY')

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
                print(f"[PROMPT_DEBUG][DeepseekR1][no_file] username={username}, role={role}")
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
        print(f"[PROMPT_DEBUG][DeepseekR1][with_file] username={username}, useSystemPrompt={useSystemPrompt}")
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
            # API_KEY = '[redacted]'
            API_KEY_ALI = _public_config.secret('NKCN_LLM_DASHSCOPE_API_KEY')

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


# 为实现规范化复制新增，仅返回一个模型的信息
def construct_file_data_normal(segments, user_name, file_list, get_way, question, history, origin_real_name, base64_images, rounds=None, cross_notebook_citation_prefix=None):
    # print('[normal_qa]get_aq_user_docs_way_split', segments)
    images, seqs, exts, sources, pages = util.parse_image_in_segment_split(
        user_name=user_name,
        all_segments=segments,
    )
    chain_params = normal_qa_new.construct_chain_params(question, user_name, segments, images, seqs, exts, sources, pages, history,
                                            file_list, get_way, origin_real_name, base64_images, rounds=rounds)
    if cross_notebook_citation_prefix:
        chain_params['cross_notebook_citation_prefix'] = cross_notebook_citation_prefix
        prefix_block = cross_notebook_citation_prefix + '\n\n'
        chain_params['text'] = prefix_block + (chain_params.get('text') or '')
        for model_name in chain_params.get('question_with_history', {}):
            chain_params['question_with_history'][model_name] = (
                prefix_block + chain_params['question_with_history'][model_name]
            )
    return chain_params


def construct_data(data):
    username = data["username"]
    originRealName = data.get("originRealName", "")
    if originRealName != "":
        name2RealUse = originRealName
    else:
        name2RealUse = username
    # seed = int(data['seed'])
    # 🔥 seed 可能为 None / 'undefined' / 'null' / ''，需容错（否则 int() 会抛异常）
    seed_raw = data.get('seed', 0)
    try:
        if seed_raw is None or (
                isinstance(seed_raw, str) and seed_raw.strip().lower() in ('', 'undefined', 'null', 'none')):
            seed = 0
        else:
            seed = int(seed_raw)
    except Exception:
        seed = 0
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

    # NK2026 梯子图场景：勾选「××组梯子图填写」或请求中带 target_file（自动化）时注入 _twin/Gxx.md
    try:
        from app_chat.group_twin_gxx import (
            prepend_nk2026_chuchengjia_context_if_needed,
            prepend_nk2026_gxx_context_if_needed,
        )

        _scene_name = data.get("sceneName") or data.get("scene_name") or ""
        _tf = (data.get("target_file") or data.get("targetFile") or "").strip()
        message = prepend_nk2026_gxx_context_if_needed(
            username, _scene_name, file_list, message, target_file=_tf or None
        )
        message = prepend_nk2026_chuchengjia_context_if_needed(
            username, _scene_name, message
        )
    except Exception as _gxx_views_e:
        print(f"[views.construct_data NK2026 Gxx/正本清源 注入] {_gxx_views_e}")

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

    # 添加RAG搜索用时（如果有文档）
    name2lock = name2RealUse
    if name2lock in chat_with_files_params and 'rag_search_time' in chat_with_files_params[name2lock]:
        response['rag_search_time'] = chat_with_files_params[name2lock]['rag_search_time']
    else:
        response['rag_search_time'] = 0

    print(f"RAG搜索用时：{response['rag_search_time']}")
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
    return StreamingHttpResponse(stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def gemini_chat_send(request):
    # print('[app_chat]views: chat_send')
    # print(request.data)
    data = request.POST
    return StreamingHttpResponse(gemini_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def claude_chat_send(request):
    data = request.POST
    return StreamingHttpResponse(stream_generator_sync(data), content_type='text/event-stream')


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
    return StreamingHttpResponse(stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def qwq_chat_send(request):
    data = request.POST
    return StreamingHttpResponse(qwq_stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def rel_questions_request(request):
    print('[DEBUG:rel_questions_request] start')

    data = json.loads(request.body)
    username = data["username"]
    originRealName = data.get("originRealName", "")
    name2RealUse = originRealName if originRealName != "" else username
    message = data["message"]
    messageInitial = message
    fileNameList = data["filenamelist"]
    file_list = fileNameList.split(',') if fileNameList else []
    rightSelectList = data["rightSelectList"]
    right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []
    window_id = data["windowId"]
    model_id = data["model_id"]

    # 新增：获取模型名称
    model_name = config_manager.get_model_name_by_id(model_id)

    if model_name in chat_content[name2RealUse]:
        # 更新历史对话
        print(f'[DEBUG:rel_questions_request] Updating interaction for {name2RealUse} with model {model_name}')
        GLOBAL_STATE.conversation_manager.add_interaction(
            username=name2RealUse,
            model_name=model_name,
            question=messageInitial,
            response=chat_content[name2RealUse][model_name],
        )
        # 更新勾选文档
        GLOBAL_STATE.conversation_manager.update_file_list(
            username=name2RealUse,
            model_name=model_name,
            file_list=file_list,
        )
    else:
        # 异常提醒
        print(f'[Error] {model_name} not in GLOBAL_STATE.chat_content!')

    # 获取有效答案
    valid_answer = data["answer"]
    print('valid_answer:', valid_answer)

    special_prompt = """你要能够根据对话进展提出有推进感的高质量追问。
1. 针对当前回答，深度挖掘更深层的原理或机制性思考，提出追问
2. 横向扩展，引导用户从不同角度或维度思考当前的问题，提出追问
...等等

要求：
- 一定一定要与当前最近一轮的用户问题、此问题的回答强关联（特别是问题，这很重要，是产生推进感的重要抓手，而不是反复绕圈子！！）
- 问题要有明显的递进层次，体现纵向深化和横向扩展
- 结合历史对话脉络，避免重复之前的问题
- 问题要具体、可操作，避免泛泛而谈
- 语言要自然流畅，符合中文表达习惯
- 直接输出问题，无需其他说明"""

    # 生成相关问题
    rel_questions = get_rel_que.get_rel_que_user_doc_way_split(
        user_name=username,
        docs_name=file_list,
        question=message,
        answer=valid_answer,
        get_way=right_select_list,
        special_prompt=special_prompt
    )

    # 构建响应
    response = {"rel_questions": rel_questions}
    return JsonResponse(response)


# @csrf_exempt
# def rel_questions_request(request):
#     print('[DEBUG:rel_questions_request] start')

#     data = json.loads(request.body)
#     username = data["username"]
#     originRealName = data.get("originRealName", "")
#     if originRealName != "":
#         name2RealUse = originRealName
#     else:
#         name2RealUse = username
#     message = data["message"]
#     messageInitial = message
#     fileNameList = data["filenamelist"]
#     file_list = fileNameList.split(',') if fileNameList else []
#     rightSelectList = data["rightSelectList"]
#     right_select_list = [int(item) for item in rightSelectList.split(',')] if rightSelectList else []
#     window_id = data["windowId"]
#     model_id = data["model_id"]

#     global chat_content
#     answer_list = [
#         chat_content[name2RealUse]["gpt4"],
#         chat_content[name2RealUse]["llama"],
#         chat_content[name2RealUse]["kimi"],
#         chat_content[name2RealUse]["claude"],
#         chat_content[name2RealUse]["deepseek"],
#         chat_content[name2RealUse]["dsreasoner"],
#         chat_content[name2RealUse]["Gemini"],
#         chat_content[name2RealUse]["Qwq"]
#     ]
#     # 如果开始综合后，还有追问请求到这里，chat_content[username]都已清空初始化，只有负责综合的1个模型输出到一半，
#     # answerList已经不是当轮对话原始回答内容了，所以这一段保存历史记录的代码需要从下面上移到此处，避免耗时过长，前端预留200ms让这里先完成后，再传综合请求
#     # print(chat_history[username])
#     if len(chat_history[name2RealUse]) == 0 or message != chat_history[name2RealUse][-1]['message']:
#         chat_history[name2RealUse].append({
#             'filelist': deepcopy(file_list),
#             'message': deepcopy(messageInitial),
#             'AImessage': deepcopy(answer_list)
#         })
#     if len(chat_history[name2RealUse]) > 0 and message == chat_history[name2RealUse][-1]['message']:
#         chat_history[name2RealUse][-1]['AImessage'] = deepcopy(answer_list)

#     valid_answer = data["answer"]
#     # valid_answer = get_first_valid_answer(model_names[model_id], chat_content[username], window_id=window_id)
#     # if valid_answer == None:
#     #     valid_answer = chat_content[username][model_names[model_id]]
#     print("chat_content:", chat_content)
#     print('valid_answer:', valid_answer)
#     rel_questions = get_rel_que.get_rel_que_user_doc_way_split(user_name=username, docs_name=file_list,
#                                                                question=message, answer=valid_answer,
#                                                                get_way=right_select_list)
#     # FIXME END
#     # kimi_response = kimi_api.make_requests(message, None, False, 0.8)
#     # content3 = kimi_response.choices[0].message.content
#     # content.append(content3)

#     # 之前content[0]只用了主窗口默认model gpt4的回答，历史功能服务仅保留在主窗口，其他窗口无参考价值，因为内容都不是辅窗口model回答的
#     # 但现在chat_history_used不用了，用下面完整历史记录的版本
#     # chat_history_used[username].append({
#     #     '用户请求': deepcopy(messageInitial),
#     #     '你的回答': deepcopy(list(chat_content[username].values())[0])
#     # })

#     # valid_cnt = 0
#     # for answer in answer_list:
#     #     if valid_cnt >= 3:
#     #         break
#     #     if answer != "" and is_valid_answer(answer):
#     #         valid_cnt += 1
#     # if valid_cnt >= 3:
#     #     chat_history[username].append({
#     #         'filelist': deepcopy(file_list),
#     #         'message': deepcopy(messageInitial),
#     #         'AImessage': deepcopy(answer_list)
#     #     })
#     response = {"rel_questions": rel_questions}
#     return JsonResponse(response)


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
    depth_suggestion = data.get("depth_suggestion", "")  # 前端传来的深度建议

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
                                                               get_way=right_select_list, special_prompt=special_prompt,
                                                               depth_suggestion=depth_suggestion)
    response = {"rel_questions": rel_questions}
    return JsonResponse(response)


@csrf_exempt
def get_depth_suggestion(request):
    """深度建议生成API接口（应用服务器方式）"""
    try:
        data = json.loads(request.body)
        input_text = data.get('input_text', '')
        user_name = data.get('user_name', 'default_user')
        task_type = data.get('task_type', 'qa')  # 新增参数：默认为qa（追问），可选summary（摘要）

        if not input_text:
            return JsonResponse({
                'error': '输入文本不能为空',
                'error_num': 1
            }, status=400)

        # 调用深度建议生成，传递task_type参数
        suggestion = get_rel_que.get_depth_suggestion(input_text, user_name, task_type)

        return JsonResponse({
            'suggestion': suggestion,
            'error_num': 0
        })

    except Exception as e:
        print(f"深度建议API错误: {e}")
        return JsonResponse({
            'error': str(e),
            'error_num': 1
        }, status=500)


@csrf_exempt
def img_getTopics(request):
    data = json.loads(request.body)
    username = data["username"]
    imgtext = data["imgtext"]
    idx1 = imgtext.find("📜 总体分析:")
    idx2 = imgtext.find("├─ 📄 T1 - 玉垒山")
    if idx1 != -1 and idx2 != -1:
        imgtext = imgtext[idx1 + len("📜 总体分析:"):idx2]

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
    depth_suggestion = data.get("depth_suggestion", "")  # 获取深度建议

    prompt = "文本：" + topicRelText + "\n关键词：<" + topicClicked + ">\n"

    # 如果有深度建议，将其附加到prompt中
    if depth_suggestion:
        prompt += "\n【追问策略建议】（小模型提供，供你作为重要参考之一）：\n" + depth_suggestion + "\n\n你的追问问题要能激发读者“醍醐灌顶”、起到一定的“育人”作用、体现“成长”价值！\n\n"

    prompt += global_var.store_memory[username]["prompt"]["LUI2"]["topic_question"]

    # kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)
    # topicRelQuestions = kimi_api.post_process_kimi_response(kimi_response)
    claude_response_text = claude_api.make_claude_text_requests(prompt)
    topicRelQuestions = claude_api.post_process_claude_response(claude_response_text)

    print('topic relative questions from LLM:', topicRelQuestions)
    response = {}
    response['topicRelQuestions'] = topicRelQuestions
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def chat_upload(request):
    # 🔥 修复方案2：获取上传信号量（如果已满，会等待，避免资源耗尽）
    # acquired = upload_semaphore.acquire(blocking=True, timeout=300)  # 最多等待5分钟
    acquired = upload_semaphore.acquire(blocking=True, timeout=900)  # 最多等待15分钟

    if not acquired:
        print(f"[WARNING] 上传队列已满，请求被拒绝")
        return JsonResponse({
            'content': 'Server is busy, please try again later',
            'msg': 'queue_full',
            'error_num': 3
        })

    try:
        data = json.loads(request.body)

        username = data["username"]
        realName = data["realName"]
        model_id = data["model_id"]
        # filename = data["filename"].split('.')[0]
        original_filename = data["filename"]  # 保存原始文件名（包含扩展名）
        filename = os.path.splitext(data["filename"])[0]
        original_extension = os.path.splitext(data["filename"])[1].lstrip('.')  # 原始扩展名（去掉点号）
        base64_encoded_file = data["file"]
        filetype = ALL_FILE_TYPES[data["filetype"]]
        # 对于音频文件，优先使用原始扩展名；其他类型沿用既有映射
        if filetype == "audio" and data["filetype"] == "11":
            filesuffix = original_extension.lower() if original_extension else "mp3"
        else:
            filesuffix = ALL_FILE_SUFFIX[data["filetype"]]
        binary_data = base64.b64decode(base64_encoded_file)
        task_id = data['task_id']  # 从请求中获取task_id
        print(f"[UPLOAD-START] {username}/{filename} - task_id={task_id}")

        # print(filetype + " file:[" + filename + "] received. Writing into current folder...")
        # received_path = './received_dir/' + 'user_raw_file/' + username + '/' + filename + '.' + filesuffix
        # # 从文件路径中提取目录路径
        # directory = os.path.dirname(received_path)
        # # 检查目录是否存在，如果不存在则创建
        # if not os.path.exists(directory):
        #     os.makedirs(directory)

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

        # with open(received_path, 'wb') as file:
        #     # 写入二进制数据
        #     file.write(binary_data)

        # parse_input.get_split_docs_vectors(realName, username, filename + "." + filesuffix, task_id=task_id)
        # print('上传文件结束')
        # response = {}
        # response['content'] = 'dddddddddddd'
        # response['msg'] = 'success'
        # response['error_num'] = 0

        # 两段式处理：第一阶段只处理文本，快速返回
        if filesuffix.lower() == 'zip' or filetype == 'zip' or str(data.get('filetype')) == '5':
            # Skill 包 zip：不向量化；校验结构后导入 skills/
            full_zip_name = filename + '.' + filesuffix
            zip_path = f'./received_dir/user_raw_file/{username}/{full_zip_name}'
            try:
                from app_chat import skills_store as skills_store
                from app_chat import skill_generate as skill_generate
                insp = skills_store.inspect_skill_zip(zip_path)
                if not insp.get('ok'):
                    # 非法结构：删除已写入的 zip，告知前端
                    try:
                        if os.path.isfile(zip_path):
                            os.remove(zip_path)
                    except Exception:
                        pass
                    response = {
                        'content': '',
                        'msg': insp.get('error') or '非 Skill 包 zip',
                        'error_num': 1,
                        'is_skill_pack': False,
                        'reject_zip': True,
                    }
                else:
                    # 有冲突时仍先导入？按默认：返回需冲突处理，先不自动 overwrite
                    existing = set(skills_store.list_skill_dirs(username))
                    conflicts = [n for n in (insp.get('skill_names') or []) if n in existing]
                    if conflicts:
                        response = {
                            'content': 'dddddddddddd',
                            'msg': 'need_conflict_resolution',
                            'error_num': 0,
                            'is_skill_pack': True,
                            'need_conflict_resolution': True,
                            'conflicts': conflicts,
                            'skill_names': insp.get('skill_names') or [],
                            'zip_name': full_zip_name,
                        }
                    else:
                        result = skills_store.import_skill_zip(
                            username, zip_path, full_zip_name, conflict_policy='overwrite',
                        )
                        if result.get('ok'):
                            try:
                                skill_generate.update_notebook_hub(realName, username)
                            except Exception:
                                pass
                            # 标记 split 完成，避免前端一直转圈
                            try:
                                global_var.add_split_file(username, full_zip_name)
                            except Exception:
                                pass
                            # 进度拉满
                            try:
                                global_var.set_task_current_page(task_id, 1)
                                task = global_var.tasks.get(task_id)
                                if task:
                                    task['current_item'] = 1
                                    task['total_items'] = 1
                            except Exception:
                                pass
                            response = {
                                'content': 'dddddddddddd',
                                'msg': 'success',
                                'error_num': 0,
                                'is_skill_pack': True,
                                'imported': result.get('imported') or [],
                                'hub': result.get('hub'),
                            }
                        else:
                            response = {
                                'content': '',
                                'msg': result.get('error') or 'Skill 包导入失败',
                                'error_num': 1,
                                'is_skill_pack': True,
                            }
            except Exception as e:
                print(f'[SkillZip] 处理失败: {e}')
                import traceback
                traceback.print_exc()
                response = {
                    'content': str(e)[:200],
                    'msg': 'error',
                    'error_num': 2,
                    'is_skill_pack': True,
                }
        elif filesuffix.lower() == 'pdf':
            # PDF文件：先处理文本部分，图片在后台异步处理
            try:
                # 第一阶段：只处理文本，不处理图片
                future = file_processing_executor.submit(
                    parse_input.get_split_docs_vectors,
                    realName,
                    username,
                    filename + "." + filesuffix,
                    task_id=task_id,
                    process_images=False  # 不处理图片
                )

                # 等待文本处理完成，设置较短的超时时间
                # split_docs, vector_store = future.result(timeout=300)  # 5分钟超时
                split_docs, vector_store = future.result(timeout=1200)  # 20分钟超时

                # 启动异步图片处理
                parse_input.process_pdf_images_async(realName, username, filename + "." + filesuffix, task_id=task_id)
                print('PDF文档文本处理完成，图片处理已在后台开始')

                response = {
                    'content': 'dddddddddddd',
                    'msg': 'success',
                    'error_num': 0,
                    'is_pdf': True  # 标识是否为PDF文件
                }

                # 🔥 新上传 PDF：先 PreSummary，完成后再生成 Skill（失败也仍 spawn，避免永远无 Skill）
                def process_new_uploaded_pdf_pre_summary_and_skill():
                    try:
                        from llm_langchain.parse_input import process_document_pre_summary, \
                            update_document_pre_summary_status
                        from app_chat.skill_generate import spawn_document_skill_async
                        from zym.models import UserNotebook

                        full_filename = filename + "." + filesuffix
                        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                            realName) + 1 else None
                        presummary_ok = False
                        if book_name:
                            try:
                                UserNotebook.objects.get(username=realName, bookName=book_name)
                                update_document_pre_summary_status(realName, book_name, full_filename, False)
                                print(f"[新上传PDF] 开始 PreSummary（完成后才生成 Skill）: {full_filename}")
                                success, error_msg = process_document_pre_summary(realName, username, full_filename)
                                if success:
                                    update_document_pre_summary_status(realName, book_name, full_filename, True)
                                    presummary_ok = True
                                    print(f"[新上传PDF] ✅ PreSummary 完成: {full_filename}")
                                else:
                                    print(f"[新上传PDF] ❌ PreSummary 失败，仍将生成 Skill（仅原文/OCR）: {full_filename}, {error_msg}")
                            except Exception as e:
                                print(f"[新上传PDF] PreSummary 异常，仍将生成 Skill: {full_filename}, {e}")
                        else:
                            print(f"[新上传PDF] 无 book_name，跳过 PreSummary，直接生成 Skill: {full_filename}")

                        print(f"[新上传PDF] 触发 Skill 生成: {full_filename} (presummary_ok={presummary_ok})")
                        spawn_document_skill_async(realName, username, full_filename)
                    except Exception as e:
                        print(f"[新上传PDF预处理] 后台异常: {e}")
                        import traceback
                        traceback.print_exc()

                import threading
                threading.Thread(target=process_new_uploaded_pdf_pre_summary_and_skill, daemon=True).start()

            except TimeoutError:
                print(f'PDF文本处理超时: task_id={task_id}')
                response = {
                    'content': 'PDF text processing timeout',
                    'msg': 'timeout',
                    'error_num': 1,
                    'is_pdf': True
                }
            except Exception as e:
                print(f'PDF文本处理出错: task_id={task_id}, error={str(e)}')
                response = {
                    'content': f'PDF text processing error: {str(e)}',
                    'msg': 'error',
                    'error_num': 2,
                    'is_pdf': True
                }
        elif filetype == "audio" and data["filetype"] == "11":
            # 音频文件：跳过向量化处理，直接返回
            print(f'[AUDIO] 音频文件 {filename} 上传完成，跳过向量化处理')

            import time
            time.sleep(0.5)  # 等待进度更新线程完成

            full_filename = filename + "." + filesuffix
            try:
                global_var.add_split_file(username, full_filename)
                print(f'[AUDIO] 已设置音频文件 {full_filename} 的 split 状态为 1')
            except Exception as e:
                print(f'[AUDIO] 设置音频文件 split 状态失败: {str(e)}')

            response = {
                'content': 'dddddddddddd',
                'msg': 'success',
                'error_num': 0,
                'is_pdf': False,
                'is_audio': True
            }
        else:
            # 非PDF文件：正常处理
            try:
                # 提交任务到线程池并等待完成
                future = file_processing_executor.submit(
                    parse_input.get_split_docs_vectors,
                    realName,
                    username,
                    filename + "." + filesuffix,
                    task_id=task_id
                )

                # 等待处理完成，设置超时时间为1200秒（20分钟）
                split_docs, vector_store = future.result(timeout=1200)

                print('上传文件结束')
                response = {
                    'content': 'dddddddddddd',
                    'msg': 'success',
                    'error_num': 0,
                    'is_pdf': False
                }

                # 🔥 新上传文档：先 PreSummary，完成后再生成 Skill（失败也仍 spawn）
                def process_new_uploaded_doc_pre_summary():
                    try:
                        from llm_langchain.parse_input import process_document_pre_summary, \
                            update_document_pre_summary_status
                        from app_chat.skill_generate import spawn_document_skill_async
                        from zym.models import UserNotebook

                        full_filename = filename + "." + filesuffix
                        # 只处理PDF和TXT文件
                        if not (full_filename.lower().endswith('.pdf') or full_filename.lower().endswith('.txt')):
                            return

                        # username格式是"用户名_本子名"
                        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                            realName) + 1 else None
                        presummary_ok = False
                        if book_name:
                            try:
                                UserNotebook.objects.get(username=realName, bookName=book_name)
                                update_document_pre_summary_status(realName, book_name, full_filename, False)
                                print(f"[新上传文档] 开始 PreSummary（完成后才生成 Skill）: {full_filename}")
                                success, error_msg = process_document_pre_summary(realName, username, full_filename)
                                if success:
                                    update_document_pre_summary_status(realName, book_name, full_filename, True)
                                    presummary_ok = True
                                    print(f"[新上传文档] ✅ PreSummary 完成: {full_filename}")
                                else:
                                    print(f"[新上传文档] ❌ PreSummary 失败，仍将生成 Skill: {full_filename}, {error_msg}")
                            except Exception as e:
                                print(f"[新上传文档] PreSummary 异常，仍将生成 Skill: {full_filename}, {e}")
                        else:
                            print(f"[新上传文档] 无 book_name，跳过 PreSummary，直接生成 Skill: {full_filename}")

                        print(f"[新上传文档] 触发 Skill 生成: {full_filename} (presummary_ok={presummary_ok})")
                        spawn_document_skill_async(realName, username, full_filename)

                    except Exception as e:
                        print(f"[新上传文档预处理] 后台处理异常: {e}")
                        import traceback
                        traceback.print_exc()

                # 后台异步处理
                import threading
                threading.Thread(target=process_new_uploaded_doc_pre_summary, daemon=True).start()

            except TimeoutError:
                print(f'文件处理超时: task_id={task_id}')
                response = {
                    'content': 'File processing timeout',
                    'msg': 'timeout',
                    'error_num': 1,
                    'is_pdf': False
                }

            except Exception as e:
                print(f'文件处理出错: task_id={task_id}, error={str(e)}')
                response = {
                    'content': f'Processing error: {str(e)}',
                    'msg': 'error',
                    'error_num': 2,
                    'is_pdf': False
                }

        print(f"[UPLOAD-END] {username}/{filename} - task_id={task_id}")
        return JsonResponse(response)

    except Exception as e:
        print(f"[ERROR] 上传处理异常: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'content': f'Upload failed: {str(e)}',
            'msg': 'error',
            'error_num': 2
        })
    finally:
        # 🔥 无论成功或失败，都要释放信号量
        upload_semaphore.release()
        print(f"[INFO] 上传槽位已释放，当前可用: {upload_semaphore._value}/{MAX_CONCURRENT_UPLOADS}")


@csrf_exempt
def check_pdf_image_processing_status(request):
    """
    检查PDF图片处理状态
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        docs_name = data.get('docs_name')

        if not username or not docs_name:
            return JsonResponse({
                'error': '缺少必要参数',
                'error_num': 1
            })

        # 检查是否有图片数据
        images = global_var.get_user_image(username, docs_name)
        has_images = images is not None and len(images) > 0
        image_count = len(images) if images else 0

        # 如果global_var中没有图片数据，检查图片文件是否存在
        if not has_images:
            import os
            file_path = f"./received_dir/user_raw_file/{username}/{docs_name}"
            image_dir = file_path.replace('.pdf', '_image')
            if os.path.exists(image_dir):
                # 计算图片文件数量
                image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                image_count = len(image_files)
                has_images = image_count > 0
                print(f"[状态检查] 从文件系统检测到 {image_count} 张图片")

        # 检查文档分割数据
        split_docs = global_var.get_user_split(username, docs_name)
        has_text_docs = split_docs is not None and len(split_docs) > 0

        # 检查图片类型的文档数量和已处理的图片数量
        image_doc_count = 0
        processed_image_count = 0
        if split_docs:
            for doc in split_docs:
                if doc.metadata.get('type') == 'image':
                    image_doc_count += 1
                    # 检查是否有分析结果（通过seq字段和内容长度判断）
                    if 'seq' in doc.metadata and len(doc.page_content) > 50:
                        processed_image_count += 1

        has_image_docs = image_doc_count > 0

        # 旧文件兼容性处理：更精确的判断逻辑
        if image_count > 0 and processed_image_count == 0 and has_images:
            # 检查是否为旧文件：图片存在但split_docs中没有图片类型的文档
            if not has_image_docs:
                # 这是旧文件：图片已存在但没有图片类型的split_docs
                processed_image_count = image_count
                print(f"[状态检查] 检测到旧文件（无图片split_docs），自动标记为已完成: {docs_name}")
            elif has_image_docs and image_doc_count == 0:
                # 这是旧文件：有图片类型的split_docs但数量为0
                processed_image_count = image_count
                print(f"[状态检查] 检测到旧文件（图片split_docs为空），自动标记为已完成: {docs_name}")

        is_processing_complete = processed_image_count >= image_count and image_count > 0

        print(f"[状态检查] 文档: {docs_name}, 图片总数: {image_count}, 已处理: {processed_image_count}, 完成: {is_processing_complete}")
        print(f"[状态检查] 详细信息: split_docs数量={len(split_docs) if split_docs else 0}, image_doc_count={image_doc_count}")

        # 调试信息：显示每个图片文档的状态
        if split_docs:
            for i, doc in enumerate(split_docs):
                if doc.metadata.get('type') == 'image':
                    content_len = len(doc.page_content)
                    has_seq = 'seq' in doc.metadata
                    has_keywords = any(keyword in doc.page_content for keyword in ['文件中的一张图片，内容为', '分析', '描述'])
                    print(
                        f"[状态检查] 图片文档{i}: seq={doc.metadata.get('seq', 'N/A')}, 内容长度={content_len}, 有seq={has_seq}, 有关键词={has_keywords}")

        return JsonResponse({
            'has_images': has_images,
            'has_text_docs': has_text_docs,
            'has_image_docs': has_image_docs,
            'is_processing_complete': is_processing_complete,
            'image_count': image_count,
            'processed_image_count': processed_image_count,
            'error_num': 0
        })

    except Exception as e:
        print(f"[ERROR] 检查PDF图片处理状态失败: {e}")
        return JsonResponse({
            'error': f'检查状态失败: {str(e)}',
            'error_num': 1
        })


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def init_file_upload(request):
    try:
        data = json.loads(request.body)

        username = data["username"]
        # filename = data["filename"].split('.')[0]
        original_filename = data["filename"]  # 保存原始文件名（包含扩展名）
        filename = os.path.splitext(data["filename"])[0]
        original_extension = os.path.splitext(data["filename"])[1].lstrip('.')  # 原始扩展名（去掉点号）
        base64_encoded_file = data["file"]
        filetype = ALL_FILE_TYPES[data["filetype"]]
        # 对于音频文件，优先使用原始扩展名；其他类型沿用既有映射
        if filetype == "audio" and data["filetype"] == "11":
            filesuffix = original_extension.lower() if original_extension else "mp3"
        else:
            filesuffix = ALL_FILE_SUFFIX[data["filetype"]]
        binary_data = base64.b64decode(base64_encoded_file)
        # task_id = data['task_id']  # 从请求中获取task_id
        # print(f"task_id: {task_id}")

        print(filetype + " file:[" + filename + "] received. Writing into current folder...")
        received_path = './received_dir/' + 'user_raw_file/' + username + '/' + filename + '.' + filesuffix
        # 从文件路径中提取目录路径
        directory = os.path.dirname(received_path)
        # 检查目录是否存在，如果不存在则创建
        if not os.path.exists(directory):
            os.makedirs(directory)

        # 🔥 新增：重新上传文件时，删除对应的翻译文件
        if filesuffix == 'pdf':
            # 检查并删除旧的翻译文件
            translation_file_path = os.path.join(directory, f"{filename}_transFTWYGUHX.pdf")
            if os.path.exists(translation_file_path):
                try:
                    os.remove(translation_file_path)
                    print(f"[文件上传] 已删除旧的翻译文件: {translation_file_path}")
                except Exception as e:
                    print(f"[文件上传] 删除翻译文件失败: {e}")

        with open(received_path, 'wb') as file:
            # 写入二进制数据
            file.write(binary_data)
        print("文件写入成功")

        # 创建唯一的任务ID
        task_id = str(uuid.uuid4())
        # 获取文件总页数
        if filesuffix == 'pdf':
            doc = fitz.open(received_path)
            total_pages = len(doc)
            doc.close()
        elif filetype == "excel" and data["filetype"] in ["9", "10"]:  # Excel文件
            # Excel文件设置2秒完成，每0.5秒更新一次进度
            total_pages = 4  # 2秒 / 0.5秒 = 4次更新
        elif filetype == "audio" and data["filetype"] == "11":  # 音频文件
            total_pages = 1
        else:
            # 对于其他类型文件，可以使用其他方式计算进度
            total_pages = 1

        # 创建上传任务记录
        global_var.set_task_current_page(task_id, 0)
        global_var.set_task_total_pages(task_id, total_pages)

        # 如果是Excel文件，启动快速进度更新
        if filetype == "excel" and data["filetype"] in ["9", "10"]:
            import threading
            def update_excel_progress():
                import time
                for i in range(1, total_pages + 1):
                    time.sleep(0.5)  # 每0.5秒更新一次
                    global_var.set_task_current_page(task_id, i)
                    print(f"[EXCEL] 文件 {filename} 进度更新: {i}/{total_pages}")

                # 确保最后一步达到100%
                global_var.set_task_current_page(task_id, total_pages)
                print(f"[EXCEL] 文件 {filename} 上传进度完成: {total_pages}/{total_pages} (100%)")

            # 在后台线程中更新进度
            progress_thread = threading.Thread(target=update_excel_progress)
            progress_thread.daemon = True
            progress_thread.start()
        elif filetype == "audio" and data["filetype"] == "11":
            import threading
            def update_audio_progress():
                import time
                time.sleep(0.5)
                global_var.set_task_current_page(task_id, total_pages)
                task = global_var.tasks.get(task_id)
                if task:
                    task['current_item'] = 1
                    task['total_items'] = 1
                print(f"[AUDIO] 文件 {filename} 上传进度完成: {total_pages}/{total_pages} (100%)")
            progress_thread = threading.Thread(target=update_audio_progress)
            progress_thread.daemon = True
            progress_thread.start()

        return JsonResponse({
            'error_num': 0,
            'task_id': task_id,
            'total_pages': total_pages
        })
    except Exception as e:
        return JsonResponse({
            'error_num': 1,
            'msg': str(e)
        })


# 使用 Server-Sent Events (SSE) 返回进度
@csrf_exempt
def upload_progress(request, task_id):
    # 重新组合task_id
    # task_id = f"upload_{timestamp}_{random}"
    print(f"Checking progress for task {task_id}")

    def event_stream():
        while True:
            task = global_var.tasks.get(task_id)
            if task is None:
                continue
            # print(f"上传文件任务：{task}")
            data = {
                'current_page': task['current_page'],
                'total_pages': task['total_pages'],
                'current_item': task.get('current_item', -1),
                'total_items': task.get('total_items', -1),
            }
            yield f"data: {json.dumps(data)}\n\n"

            if task['current_page'] >= task['total_pages'] and 'current_item' in task and 'total_items' in task and \
                    task['current_item'] >= task['total_items']:
                break

            time.sleep(1)  # 每秒更新一次进度

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    return response


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


def remove_emojis(text):
    """
    去除文本中的所有emoji图标（保留中文字符）

    Args:
        text (str): 包含emoji的原文本

    Returns:
        str: 去除emoji后的文本
    """
    # 更精确的emoji正则表达式，避免删除中文字符
    # 含 Geometric Shapes Extended（🟠🟢🟡🟣 等彩色圆点，常见于摘要/教学标注）
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # 表情符号
        "\U0001F300-\U0001F5FF"  # 符号和象形文字
        "\U0001F680-\U0001F6FF"  # 交通和地图符号
        "\U0001F1E0-\U0001F1FF"  # 国旗
        "\U0001F780-\U0001F7FF"  # 几何图形扩展（🟠🟢🟡🟣🟤 等）
        "\U0001F900-\U0001F9FF"  # 补充符号
        "\U0001FA70-\U0001FAFF"  # 符号和象形文字扩展-A
        "\U00002600-\U000026FF"  # 杂项符号
        "\U00002700-\U000027BF"  # 装饰符号
        "\u2640-\u2642"  # 性别符号
        "\u2695\u26CE\u26CF"  # 医学等符号
        "\u2763\u2764"  # 心形符号
        "\u200d"  # 零宽连接符
        "\ufe0f"  # 变体选择符
        "]+",
        flags=re.UNICODE
    )

    # 去除emoji
    return emoji_pattern.sub(r'', text)


# 交互式建卡：标题先返回时，语义关键词占位（前端据此展示「还在理解和生成中」）
SEMANTIC_KEYWORDS_PENDING = '（理解生成中）'


def generate_card_content_title_only(content):
    """只生成 contentTitle（不含子场景 Sn: 前缀），带超时与 DeepSeek 兜底。"""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    system_prompt_title = '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，' \
                          '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求' \
                          '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
    prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + content

    def call_kimi_first():
        kimi_response = kimi_api.make_requests(prompt_title, None, False, 0.8)
        return kimi_response.choices[0].message.content

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(call_kimi_first)
            result = future.result(timeout=15)
            return result
    except (FuturesTimeoutError, Exception) as e:
        print(f"[generate_title] 首次调用失败或超时: {e}，尝试使用 DeepSeek 重试...")

    try:
        import os
        from openai import OpenAI
        ds_api_key = os.environ.get('DEEPSEEK_API_KEY') or _public_config.secret('DEEPSEEK_API_KEY')
        client = OpenAI(
            api_key=ds_api_key,
            base_url="https://api.deepseek.com",
            timeout=15.0,
        )
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[
                {"role": "system", "content": system_prompt_title},
                {"role": "user", "content": '需要你摘取或总结出一条标题的文本：\n' + content[:4000]},
            ],
            temperature=0.6,
            max_tokens=50,
            extra_body={'thinking': {'type': 'disabled'}},
        )
        result = (response.choices[0].message.content or '').strip()
        print(f"[generate_title] DeepSeek 重试成功: {result}")
        return result
    except Exception as e2:
        print(f"[generate_title] DeepSeek 重试也失败: {e2}，使用默认标题")
        return "待命名标题"


def resolve_subscene_title_prefix(sceneName, subSceneName):
    """
    解析子场景序号前缀。
    Returns: (prefix, subSceneNameListOrder, index_or_none)
      prefix 如 'S3:'；找不到时为 'S0:'
    """
    sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
    entries = os.listdir(sceneDirPath)
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
        prefix = "S" + str(index + 1) + ":"
        return prefix, subSceneNameListOrder, index
    except ValueError:
        print(f"警告：{subSceneName}不在子场景列表中")
        return "S0:", subSceneNameListOrder, None


def generate_title_and_card_attrs_parallel(content, username, sceneName, subSceneName, is_neuron=False,
                                            provisional_content_title=''):
    """
    交互式建卡：contentTitle 与卡片级四色/DMT 并发完成。
    Returns: (raw_title, four_color_type, dmt_level, is_analyzed_by_new_standard)
    """
    from concurrent.futures import ThreadPoolExecutor
    from app_chat.card_analyzer import analyze_card_with_new_standard
    from app_chat.scene_context_helper import get_scene_summary, get_notebook_description

    scene_summary_info, subscene_summary_info = get_scene_summary(sceneName, subSceneName)
    notebook_desc = get_notebook_description(username, sceneName)
    final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info

    all_cards = Card.objects.filter(username=username).values(
        'cid', 'content', 'contentTitle', 'is_neuron', 'is_evolved', 'selection_count', 'postIndex',
        'four_color_type', 'dmt_level'
    )
    all_cards_data = list(all_cards)
    total_cards_count = len(all_cards_data)

    current_card_data = {
        'content': content,
        # 与标题并发时最终 Sn:标题尚未就绪，用前缀占位；分析主要依据正文
        'contentTitle': provisional_content_title or '',
        'is_neuron': is_neuron,
        'is_evolved': False,
        'selection_count': 0,
        'cid': None,
        'username': username,
    }

    def do_title():
        return generate_card_content_title_only(content)

    def do_card_analyze():
        print("[generate_title_and_card_attrs_parallel] 开始卡片四色/DMT 分析...")
        return analyze_card_with_new_standard(
            current_card_data,
            scene_name=sceneName,
            sub_scene_name=subSceneName,
            scene_summary=final_scene_summary,
            notebook_description=notebook_desc,
            all_cards_data=all_cards_data,
            total_cards_count=total_cards_count,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        title_future = executor.submit(do_title)
        analyze_future = executor.submit(do_card_analyze)
        raw_title = title_future.result()
        four_color_type, dmt_level, is_analyzed = analyze_future.result()

    print(
        f"[generate_title_and_card_attrs_parallel] 完成 title={raw_title}, "
        f"four={four_color_type}, dmt={dmt_level}, analyzed={is_analyzed}"
    )
    return raw_title, four_color_type or '', dmt_level or '', bool(is_analyzed)


def fill_card_semantic_keywords_sync(cid, username, name2RealUse, sceneName, subSceneName, keyTopicsList=None,
                                     also_analyze_card=False):
    """
    为已创建卡片补全语义关键词 + 关键词 DMT/四色/三类知识。
    卡片级四色/DMT 已在建卡时与标题并发完成，默认不再后补。
    """
    from django.db import close_old_connections
    from app_chat.card_keyword_extract import extract_card_semantic_keywords

    close_old_connections()
    try:
        card = Card.objects.get(cid=cid)
    except Card.DoesNotExist:
        print(f"[fill_card_semantic_keywords] 卡片不存在 cid={cid}")
        return None

    content = card.content or ''
    if keyTopicsList is None:
        keyTopicsList = []

    existing = (card.keyWords or '').strip()
    keyWords = existing
    if not existing or existing == SEMANTIC_KEYWORDS_PENDING:
        try:
            keyWords = extract_card_semantic_keywords(
                content,
                key_topics=keyTopicsList,
                username=username,
                scene_name=sceneName,
                with_candidates=True,
            )
        except Exception as e:
            print(f"[fill_card_semantic_keywords] 抽取失败 cid={cid}: {e}")
            keyWords = ''

        if not keyWords:
            keyWords = '关键词解析失败'

        try:
            generate_title_and_analyze_keywords_parallel(
                keyWords, content, username, name2RealUse, sceneName, subSceneName, skip_title=True
            )
        except Exception as e:
            print(f"[fill_card_semantic_keywords] 关键词属性分析失败 cid={cid}: {e}")

        close_old_connections()
        card.keyWords = keyWords
        card.save(update_fields=['keyWords'])
        print(f"[fill_card_semantic_keywords] 关键词完成 cid={cid} keyWords={keyWords}")

    if also_analyze_card and not getattr(card, 'is_analyzed_by_new_standard', False):
        try:
            from app_chat.card_analyzer import analyze_card_with_new_standard
            from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
            scene_summary_info, subscene_summary_info = get_scene_summary(sceneName, subSceneName)
            notebook_desc = get_notebook_description(username, sceneName)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
            all_cards = Card.objects.filter(username=username).values(
                'cid', 'content', 'contentTitle', 'is_neuron', 'is_evolved', 'selection_count', 'postIndex',
                'four_color_type', 'dmt_level'
            )
            all_cards_data = list(all_cards)
            current_card_data = {
                'content': content,
                'contentTitle': card.contentTitle or '',
                'is_neuron': bool(getattr(card, 'is_neuron', False)),
                'is_evolved': bool(getattr(card, 'is_evolved', False)),
                'selection_count': getattr(card, 'selection_count', 0) or 0,
                'cid': card.cid,
                'username': username,
            }
            four_color_type, dmt_level, is_analyzed = analyze_card_with_new_standard(
                current_card_data,
                scene_name=sceneName,
                sub_scene_name=subSceneName,
                scene_summary=final_scene_summary,
                notebook_description=notebook_desc,
                all_cards_data=all_cards_data,
                total_cards_count=len(all_cards_data),
            )
            close_old_connections()
            card.four_color_type = four_color_type or ''
            card.dmt_level = dmt_level or ''
            card.is_analyzed_by_new_standard = bool(is_analyzed)
            card.save(update_fields=['four_color_type', 'dmt_level', 'is_analyzed_by_new_standard'])
            print(
                f"[fill_card_semantic_keywords] 卡片四色/DMT完成 cid={cid} "
                f"four={four_color_type} dmt={dmt_level}"
            )
        except Exception as e:
            print(f"[fill_card_semantic_keywords] 卡片四色/DMT分析失败 cid={cid}: {e}")
            import traceback
            traceback.print_exc()

    return keyWords


def start_fill_card_semantic_keywords_background(cid, username, name2RealUse, sceneName, subSceneName, keyTopicsList=None):
    """后台线程补全语义关键词（不阻塞建卡；卡片级四色/DMT 已在建卡前并发完成）。"""
    topics = list(keyTopicsList or [])

    def _job():
        try:
            fill_card_semantic_keywords_sync(
                cid, username, name2RealUse, sceneName, subSceneName, topics, also_analyze_card=False
            )
        except Exception as e:
            print(f"[fill_card_semantic_keywords] 后台任务异常 cid={cid}: {e}")
            import traceback
            traceback.print_exc()

    threading.Thread(target=_job, daemon=True).start()
    print(f"[fill_card_semantic_keywords] 已启动后台补全 cid={cid}")


def generate_title_and_analyze_keywords_parallel(keyWords, content, username, name2RealUse, sceneName=None,
                                                 subSceneName=None, skip_title=False):
    """
    🔥 并行生成标题和关键词的DMT/四色分析

    Args:
        keyWords: 关键词字符串（如"关键词1，关键词2"）
        content: 卡片内容
        sceneName: 场景名
        subSceneName: 子场景名
        username: 用户名
        name2RealUse: 真实用户名
        skip_title: True 时只做关键词属性分析（建卡标题已前置生成时用）

    Returns:
        (title, keyword_results_dict) 元组
        - title: 生成的标题（skip_title 时为空串）
        - keyword_results_dict: 关键词分析结果字典，格式为 {keyword: {'four_color_type': 'R', 'dmt_level': 'T', 'knowledge_type': 'trad'}}
    """
    from app_chat.keyword_utils import normalize_semantic_keywords
    from concurrent.futures import ThreadPoolExecutor
    from app_chat.keyword_analyzer import analyze_keyword_full_attributes_with_llm, \
        update_notebook_keyword_four_color_dmt
    from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
    import re

    keyWords = normalize_semantic_keywords(keyWords)

    # 提前获取场景信息和本子描述（用于关键词分析）- 如果提供了场景信息
    if sceneName:
        scene_summary_info, subscene_summary_info = get_scene_summary(sceneName, subSceneName)
        notebook_desc = get_notebook_description(username, sceneName)
        final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
    else:
        scene_summary_info, subscene_summary_info = None, None
        notebook_desc = ""
        final_scene_summary = ""

    # 解析关键词列表
    keywords_list = re.split(r'[,，]', keyWords)
    keywords_list = [kw.strip() for kw in keywords_list if kw.strip()]

    def generate_title():
        return generate_card_content_title_only(content)

    def analyze_keywords_four_color_dmt():
        """分析所有关键词的四色/DMT/三类知识属性"""
        keyword_results = {}

        # 🔥 先获取本子的keywordFourColorDMT数据，检查哪些关键词已有分析结果
        existing_keyword_data = {}
        try:
            from zym.models import UserNotebook, scene
            realName = username.split('_')[0] if '_' in username else username
            book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                realName) + 1 else None

            # 如果没有book_name，尝试通过sceneName查找
            if not book_name and sceneName:
                try:
                    scene_obj = scene.objects.get(sceneDescription=sceneName)
                    notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                    if notebook:
                        book_name = notebook.bookName
                except:
                    pass

            # 如果还是没有，尝试查找用户的第一个笔记本
            if not book_name:
                notebook = UserNotebook.objects.filter(username=realName).first()
                if notebook:
                    book_name = notebook.bookName

            # 获取keywordFourColorDMT数据
            if book_name:
                try:
                    notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                    if notebook.keywordFourColorDMT:
                        import json
                        existing_keyword_data = json.loads(notebook.keywordFourColorDMT)
                        print(f"[analyze_keywords_four_color_dmt] 已加载现有关键词数据，共{len(existing_keyword_data)}个关键词")
                except Exception as e:
                    print(f"[analyze_keywords_four_color_dmt] 获取现有关键词数据失败: {e}")
        except Exception as e:
            print(f"[analyze_keywords_four_color_dmt] 检查现有关键词数据时出错: {e}")

        # 只分析没有现有数据的关键词
        for keyword in keywords_list:
            # 🔥 检查该关键词是否已有分析结果
            if keyword in existing_keyword_data:
                existing_data = existing_keyword_data[keyword]
                four_color_type = existing_data.get('four_color_type', '')
                dmt_level = existing_data.get('dmt_level', '')
                knowledge_type = existing_data.get('knowledge_type', '')
                # 如果已有完整的分析结果，跳过
                if four_color_type and dmt_level and knowledge_type:
                    keyword_results[keyword] = {
                        'four_color_type': four_color_type,
                        'dmt_level': dmt_level,
                        'knowledge_type': knowledge_type,
                    }
                    print(
                        f"[analyze_keywords_four_color_dmt] 关键词'{keyword}'已有分析结果，跳过: "
                        f"四色={four_color_type}, DMT={dmt_level}, 三类知识={knowledge_type}")
                    continue
                if four_color_type and dmt_level and not knowledge_type:
                    pass  # 缺三类知识，继续补全

            # 如果没有现有数据或数据不完整，进行分析
            try:
                four_color_type, dmt_level, knowledge_type = analyze_keyword_full_attributes_with_llm(
                    keyword=keyword,
                    card_content=content,
                    scene_name=sceneName,
                    sub_scene_name=subSceneName,
                    scene_summary=final_scene_summary,
                    notebook_description=notebook_desc
                )
                if four_color_type or dmt_level or knowledge_type:
                    keyword_results[keyword] = {
                        'four_color_type': four_color_type,
                        'dmt_level': dmt_level,
                        'knowledge_type': knowledge_type,
                    }
                    print(
                        f"[analyze_keywords_four_color_dmt] 关键词'{keyword}'分析完成: "
                        f"四色={four_color_type}, DMT={dmt_level}, 三类知识={knowledge_type}")
            except Exception as e:
                print(f"[analyze_keywords_four_color_dmt] 分析关键词'{keyword}'失败: {e}")
                keyword_results[keyword] = {'four_color_type': '', 'dmt_level': '', 'knowledge_type': ''}
        return keyword_results

    # 🔥 并行执行标题生成和关键词分析（可跳过标题）
    if skip_title:
        title = ''
        keyword_results = analyze_keywords_four_color_dmt() if keywords_list else {}
    else:
        with ThreadPoolExecutor(max_workers=2) as executor:
            title_future = executor.submit(generate_title)
            keywords_future = executor.submit(analyze_keywords_four_color_dmt)

            # 等待两个任务完成
            title = title_future.result()
            keyword_results = keywords_future.result()

    # 🔥 保存关键词的四色/DMT信息到数据库
    for keyword, result in keyword_results.items():
        if result.get('four_color_type') or result.get('dmt_level') or result.get('knowledge_type'):
            try:
                # 解析book_name
                # realName = name2RealUse.split('_')[0] if '_' in name2RealUse else name2RealUse
                # book_name = name2RealUse[len(realName) + 1:] if '_' in name2RealUse and len(name2RealUse) > len(
                #     realName) + 1 else None
                realName = username.split('_')[0] if '_' in username else username
                book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                    realName) + 1 else None
                if not book_name:
                    from zym.models import UserNotebook
                    # 尝试查找用户的第一个笔记本
                    try:
                        notebook = UserNotebook.objects.filter(username=realName).first()
                        if notebook:
                            book_name = notebook.bookName
                    except:
                        pass
                    # 如果还是没有，且有sceneName，通过scene查找
                    if not book_name and sceneName:
                        from zym.models import scene
                        try:
                            scene_obj = scene.objects.get(sceneDescription=sceneName)
                            notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                            if notebook:
                                book_name = notebook.bookName
                        except:
                            pass

                if book_name:
                    update_notebook_keyword_four_color_dmt(
                        username=username,
                        scene_name=sceneName,
                        book_name=book_name,
                        keyword=keyword,
                        four_color_type=result.get('four_color_type', ''),
                        dmt_level=result.get('dmt_level', ''),
                        knowledge_type=result.get('knowledge_type', ''),
                    )
            except Exception as e:
                print(f"[generate_title_and_analyze_keywords_parallel] 保存关键词'{keyword}'的四色/DMT信息失败: {e}")

    return title, keyword_results


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
    # seed = int(data["seed"])
    # 🔥 seed 可能为 None / 'undefined' / 'null' / ''，需容错（否则 int() 会抛异常）
    seed_raw = data.get("seed", 0)
    try:
        if seed_raw is None or (
                isinstance(seed_raw, str) and seed_raw.strip().lower() in ('', 'undefined', 'null', 'none')):
            seed = 0
        else:
            seed = int(seed_raw)
    except Exception:
        seed = 0
    sceneName = data["sceneName"]
    subSceneName = data["subSceneName"]
    # timeParams = json.loads(data["timeParams"])
    # 🔥 处理timeParams：可能是字典（自动化）或JSON字符串（前端），需容错处理
    timeParams_raw = data.get("timeParams", "{}")
    try:
        if timeParams_raw is None or (isinstance(timeParams_raw, str) and not timeParams_raw.strip()):
            timeParams = {}
        elif isinstance(timeParams_raw, dict):
            timeParams = timeParams_raw
        elif isinstance(timeParams_raw, str):
            timeParams = json.loads(timeParams_raw) if timeParams_raw.strip() else {}
        else:
            timeParams = {}
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        print(f"[card_upload] 解析timeParams失败: {e}，使用默认值{{}}")
        timeParams = {}
    # choosed_card_id_list = json.loads(data.get("choosedCardIdList", "[]"))
    # 🔥 处理choosedCardIdList：可能是列表（自动化）或JSON字符串（前端）
    choosed_card_id_list_raw = data.get("choosedCardIdList", "[]")
    if choosed_card_id_list_raw:
        print(f"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx{choosed_card_id_list_raw}")
    if isinstance(choosed_card_id_list_raw, list):
        choosed_card_id_list = choosed_card_id_list_raw
    elif isinstance(choosed_card_id_list_raw, str):
        choosed_card_id_list = json.loads(choosed_card_id_list_raw) if choosed_card_id_list_raw else []
    else:
        choosed_card_id_list = []
    file_list = data.get("file_list", [])

    # 🔥 获取三窗口模型配置
    three_window_models = None
    try:
        three_window_models_raw = data.get("three_window_models", None)
        if three_window_models_raw:
            if isinstance(three_window_models_raw, str):
                three_window_models = json.loads(three_window_models_raw)
            else:
                three_window_models = three_window_models_raw
            print(f"[card_upload] 三窗口模型配置: {three_window_models}")
    except Exception as e:
        print(f"[card_upload] 处理three_window_models失败: {e}")

    # 获取置信度和腐烂度评分
    confidence_score = float(data.get("confidence_score", 3.0))
    rot_score = float(data.get("rot_score", 2.0))
    print(f'[card_upload] 置信度: {confidence_score}, 腐烂度: {rot_score}')

    content = remove_emojis(content)

    print('[card_upload],seed=', seed, type(seed))

    if status0 == 'true':
        status = 1
    else:
        status = 0

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
    try:
        keyTopicsList = json.loads(keyTopics) if isinstance(keyTopics, str) else (keyTopics or [])
    except Exception:
        keyTopicsList = []

    # 交互式钉卡：标题 + 卡片级四色/DMT 并发完成后建卡返回；语义关键词后台补全
    subSceneOrder, subSceneNameListOrder, index = resolve_subscene_title_prefix(sceneName, subSceneName)
    is_neuron = False
    try:
        if index is not None and index + 1 == len(subSceneNameListOrder):
            is_neuron = True
            print(f"[card_upload] 标记为神经元卡（最后一个子场景）")
    except Exception:
        pass

    gpt4_response_title, four_color_type, dmt_level, is_analyzed_by_new_standard = (
        generate_title_and_card_attrs_parallel(
            content, username, sceneName, subSceneName,
            is_neuron=is_neuron,
            provisional_content_title=subSceneOrder,
        )
    )
    contentTitle = subSceneOrder + gpt4_response_title
    keyWords = SEMANTIC_KEYWORDS_PENDING

    # zyr chat_history
    # TODO: 该处的chat_history[name2RealUse]不知道要怎么用，需要小心处理
    latest_history_list = chat_history[name2RealUse]
    latest_history = {'data': latest_history_list}
    # zyr end

    clean_name = name2RealUse.split('_')[0]

    # 🔥 如果有勾选的卡片,将卡片ID列表设置为新卡片的postIndex
    post_index = ""
    try:
        if choosed_card_id_list and len(choosed_card_id_list) > 0:
            # 将卡片ID列表转换为JSON字符串存储
            post_index = json.dumps(choosed_card_id_list, ensure_ascii=False)
            print(f"[card_upload] 设置新卡片的postIndex: {post_index}")
    except Exception as e:
        print(f"[card_upload] 处理choosedCardIdList失败: {e}")

    # 🔥 保存生成此卡片时勾选的文档列表
    selected_docs_str = ""
    try:
        if isinstance(file_list, str):
            file_list = json.loads(file_list) if file_list else []
        if file_list and len(file_list) > 0:
            selected_docs_str = json.dumps(file_list, ensure_ascii=False)
            print(f"[card_upload] 设置新卡片的selected_docs: {selected_docs_str}")
    except Exception as e:
        print(f"[card_upload] 处理file_list失败: {e}")

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
        writer=clean_name,
        confidence_score=confidence_score,
        rot_score=rot_score,
        postIndex=post_index,  # 🔥 设置后置索引
        selected_docs=selected_docs_str,  # 🔥 保存勾选的文档列表
        three_window_models=three_window_models,  # 🔥 保存三窗口模型配置
        four_color_type=four_color_type,  # 🔥 四色类型
        dmt_level=dmt_level,  # 🔥 DMT层次
        is_neuron=is_neuron,  # 🔥 神经元卡标记
        is_analyzed_by_new_standard=is_analyzed_by_new_standard  # 🔥 新标准分析标记
    )

    # 🔥 语义关键词 + 关键词四色/DMT/三类知识：后台补全，不阻塞前端等待卡
    start_fill_card_semantic_keywords_background(
        card.cid, username, name2RealUse, sceneName, subSceneName, keyTopicsList
    )

    # 🔥 如果是问答卡（status0 == 0），后台更新问题链分类
    if status0 == 0:
        # 保存card.cid以便在后台线程中使用
        new_card_cid = card.cid

        def _background_update_question_category():
            try:
                realName = username.split('_')[0] if '_' in username else username
                book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                    realName) + 1 else None

                if book_name:
                    notebook = UserNotebook.objects.get(username=realName, bookName=book_name)

                    # 重新获取卡片（后台线程中需要重新查询）
                    from app_chat.models import Card
                    card = Card.objects.get(cid=new_card_cid)

                    # 提取问题
                    question = ""
                    if card.history:
                        try:
                            history = json.loads(card.history) if isinstance(card.history, str) else card.history
                            history_data = history.get('data') if isinstance(history, dict) else history
                            if isinstance(history_data, list) and len(history_data) > 0:
                                first_msg = history_data[0]
                                if isinstance(first_msg, dict):
                                    question = first_msg.get('content', '')
                        except:
                            pass

                    if not question and card.content:
                        import re
                        match = re.search(r'提问[：:]\s*([^\n\r]+)', card.content)
                        if match:
                            question = match.group(1).strip()

                    if question:
                        # 获取现有分类
                        existing_categories = {}
                        if notebook.questionChainCategories:
                            try:
                                existing_categories = json.loads(notebook.questionChainCategories)
                            except:
                                existing_categories = {}

                        # 调用分类函数
                        from app_chat.views_smart_sort_questions import classify_single_question
                        result = classify_single_question(
                            str(card.cid),
                            question,
                            existing_categories,
                            username,
                            sceneName
                        )

                        if result:
                            # 更新分类
                            notebook.questionChainCategories = json.dumps(result['updated_categories'],
                                                                          ensure_ascii=False)
                            notebook.save()
                            print(f"[card_upload] 后台成功更新问题链分类: CID={card.cid}, 分类={result['category_name']}")

                            # 统计问答卡数量，每增加10张重新排序
                            qa_cards_count = Card.objects.filter(username=username, status=0).count()
                            if qa_cards_count % 10 == 0:
                                print(f"[card_upload] 问答卡数量达到{qa_cards_count}张，触发重新排序")
                                # 收集所有问题
                                qa_cards = Card.objects.filter(username=username, status=0).order_by('datetime')
                                questions = []
                                for qa_card in qa_cards:
                                    q_question = ""
                                    if qa_card.history:
                                        try:
                                            h = json.loads(qa_card.history) if isinstance(qa_card.history,
                                                                                          str) else qa_card.history
                                            h_data = h.get('data') if isinstance(h, dict) else h
                                            if isinstance(h_data, list) and len(h_data) > 0:
                                                first_msg = h_data[0]
                                                if isinstance(first_msg, dict):
                                                    q_question = first_msg.get('content', '')
                                        except:
                                            pass

                                    if not q_question and qa_card.content:
                                        match = re.search(r'提问[：:]\s*([^\n\r]+)', qa_card.content)
                                        if match:
                                            q_question = match.group(1).strip()

                                    if q_question:
                                        sub_scene = ""
                                        if qa_card.contentTitle:
                                            match = re.search(r'^(S\d+)', qa_card.contentTitle)
                                            if match:
                                                sub_scene = match.group(1)

                                        questions.append({
                                            'cid': str(qa_card.cid),
                                            'question': q_question,
                                            'author': qa_card.writer or qa_card.username or '',
                                            'sub_scene': sub_scene,
                                            'datetime': str(qa_card.datetime) if qa_card.datetime else ''
                                        })

                                if questions:
                                    # 直接调用排序函数（内部调用）
                                    from app_chat.views_smart_sort_questions import smart_sort_questions
                                    from django.test import RequestFactory
                                    factory = RequestFactory()
                                    request_data = {
                                        'username': username,
                                        'scene_name': sceneName,
                                        'questions': questions
                                    }
                                    req = factory.post('/api/smart_sort_questions', data=json.dumps(request_data),
                                                       content_type='application/json')
                                    response = smart_sort_questions(req)
                                    if response.status_code == 200:
                                        print(f"[card_upload] 后台重新排序完成")
                                    else:
                                        print(f"[card_upload] 后台重新排序失败: {response.status_code}")
                        else:
                            print(f"[card_upload] 后台分类失败，跳过更新")
            except Exception as e:
                print(f"[card_upload] 后台更新问题链分类失败: {e}")
                import traceback
                traceback.print_exc()

        # 在后台线程中执行
        thread = threading.Thread(
            target=_background_update_question_category,
            daemon=True
        )
        thread.start()

    return JsonResponse({
        'status': 'success',
        'message': 'Card added successfully.',
        'card_id': card.cid,
        'score': score,
        'error_num': 0,
        'seed': seed,
        'contentTitle': contentTitle,
        'keywords_pending': True,
    }, status=201)


@csrf_exempt
def card_fill_semantic_keywords(request):
    """手动/兜底：为已建卡片补全语义关键词及关键词属性分析。"""
    try:
        data = {}
        try:
            raw = request.body.decode('utf-8') if request.body else ''
            if raw.strip().startswith('{'):
                data = json.loads(raw)
        except Exception:
            data = {}
        if not data:
            data = request.POST or {}

        username = data.get('username')
        originRealName = data.get('originRealName', '') or ''
        cid = data.get('cid') or data.get('card_id')
        sceneName = data.get('sceneName') or data.get('scene_name') or ''
        subSceneName = data.get('subSceneName') or data.get('sub_scene_name') or ''
        keyTopics = data.get('keyTopics', '[]')
        if isinstance(keyTopics, str):
            try:
                keyTopicsList = json.loads(keyTopics) if keyTopics else []
            except Exception:
                keyTopicsList = []
        else:
            keyTopicsList = keyTopics or []

        if not username or not cid:
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 cid'})

        name2RealUse = originRealName if originRealName else username
        keyWords = fill_card_semantic_keywords_sync(
            int(cid), username, name2RealUse, sceneName, subSceneName, keyTopicsList
        )
        if keyWords is None:
            return JsonResponse({'error_num': 1, 'msg': '卡片不存在'})
        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'keyWords': keyWords,
            'keywords_pending': keyWords == SEMANTIC_KEYWORDS_PENDING,
        })
    except Exception as e:
        print(f"[card_fill_semantic_keywords] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error_num': 1, 'msg': str(e)})


@csrf_exempt
def update_card_three_window_models(request):
    """更新卡片的三窗口模型配置"""
    try:
        # 支持FormData和JSON两种格式
        if request.content_type and 'application/json' in request.content_type:
            data = json.loads(request.body)
            username = data.get("username")
            cid = data.get("cid")
            three_window_models = data.get("three_window_models")
        else:
            # FormData格式
            username = request.POST.get("username")
            cid = request.POST.get("cid")
            three_window_models_str = request.POST.get("three_window_models")
            if three_window_models_str:
                three_window_models = json.loads(three_window_models_str)
            else:
                three_window_models = None

        if not username or not cid:
            return JsonResponse({
                'error_num': 1,
                'msg': '缺少必要参数'
            })

        try:
            card = Card.objects.get(cid=cid, username=username)

            # 解析三窗口模型配置
            if isinstance(three_window_models, str):
                three_window_models = json.loads(three_window_models)

            card.three_window_models = three_window_models
            card.save()

            print(f"[update_card_three_window_models] 卡片 {cid} 的三窗口模型配置已更新: {three_window_models}")

            return JsonResponse({
                'error_num': 0,
                'msg': '三窗口模型配置更新成功'
            })
        except Card.DoesNotExist:
            return JsonResponse({
                'error_num': 1,
                'msg': '卡片不存在'
            })
    except Exception as e:
        print(f"[update_card_three_window_models] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'更新失败: {str(e)}'
        })


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

    # 🔥 标记为进化卡
    card.is_evolved = True
    # 🔥 重新判定四色和DMT属性（内容已更新，使用新标准分析）
    from app_chat.card_analyzer import analyze_card_with_new_standard
    from app_chat.scene_context_helper import get_scene_info_from_username

    # 🔥 获取场景信息（传入contentTitle以便提取子场景名）
    scene_name, sub_scene_name, scene_summary, notebook_desc = get_scene_info_from_username(card.username, card.contentTitle)

    # 🔥 获取所有卡片数据（用于判断被勾选次数和总卡片数）
    all_cards = Card.objects.filter(username=card.username).values(
        'cid', 'content', 'contentTitle', 'is_neuron', 'is_evolved', 'selection_count', 'postIndex',
        'four_color_type', 'dmt_level'
    )
    all_cards_data = list(all_cards)
    total_cards_count = len(all_cards_data)

    # 构建卡片数据（用于分析，内容已更新）
    card_data = {
        'cid': card.cid,
        'content': organized_content,
        'contentTitle': card.contentTitle or '',
        'is_neuron': card.is_neuron,
        'is_evolved': card.is_evolved,
        'selection_count': card.selection_count,
        'username': card.username
    }

    # 🔥 使用新标准分析卡片
    print(f"[card_tidyUpById] 开始按照新标准分析卡片（前置存在性评判 + LLM分析）...")
    four_color_type, dmt_level, is_analyzed_by_new_standard = analyze_card_with_new_standard(
        card_data,
        scene_name=scene_name,
        sub_scene_name=sub_scene_name,
        scene_summary=scene_summary,
        notebook_description=notebook_desc,
        all_cards_data=all_cards_data,
        total_cards_count=total_cards_count
    )

    card.four_color_type = four_color_type
    card.dmt_level = dmt_level
    card.is_analyzed_by_new_standard = is_analyzed_by_new_standard

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
        # 🔥 如果是关键词神经元永久卡，保持type为"永久"不变
        if card.type and "永久" in card.type and card.title == "关键词神经元永久卡":
            # 保持type不变，只清空preIndex
            card.preIndex = ""
        else:
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

    # 🔥 重新判定四色和DMT属性（内容已更新，使用新标准分析）
    from app_chat.card_analyzer import analyze_card_with_new_standard
    from app_chat.scene_context_helper import get_scene_info_from_username

    # 🔥 获取场景信息（传入contentTitle以便提取子场景名）
    scene_name, sub_scene_name, scene_summary, notebook_desc = get_scene_info_from_username(card.username,
                                                                                            card.contentTitle)

    # 🔥 获取所有卡片数据（用于判断被勾选次数和总卡片数）
    all_cards = Card.objects.filter(username=card.username).values(
        'cid', 'content', 'contentTitle', 'is_neuron', 'is_evolved', 'selection_count', 'postIndex',
        'four_color_type', 'dmt_level'
    )
    all_cards_data = list(all_cards)
    total_cards_count = len(all_cards_data)

    # 构建卡片数据（用于分析）
    card_data = {
        'cid': card.cid,
        'content': final_result,
        'contentTitle': card.contentTitle or '',
        'is_neuron': card.is_neuron,
        'is_evolved': card.is_evolved,
        'selection_count': card.selection_count,
        'username': card.username
    }

    # 🔥 使用新标准分析卡片
    print(f"[card_updateContentById] 开始按照新标准分析卡片（前置存在性评判 + LLM分析）...")
    four_color_type, dmt_level, is_analyzed_by_new_standard = analyze_card_with_new_standard(
        card_data,
        scene_name=scene_name,
        sub_scene_name=sub_scene_name,
        scene_summary=scene_summary,
        notebook_description=notebook_desc,
        all_cards_data=all_cards_data,
        total_cards_count=total_cards_count
    )

    card.four_color_type = four_color_type
    card.dmt_level = dmt_level
    card.is_analyzed_by_new_standard = is_analyzed_by_new_standard

    print(
        f"[card_updateContentById] 最终判定结果 - 四色类型: {four_color_type}, DMT层次: {dmt_level}, 已按新标准分析: {is_analyzed_by_new_standard}")

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
        # 1.获取用户上传的文件及其大小和时间
        for f in os.listdir(user_path):
            if os.path.isdir(user_path + '/' + f):
                continue
            if f.endswith('_transFTWYGUHX.pdf'):
                continue
            file_path = os.path.join(user_path, f)
            file_list.append(f)
            size_list.append(os.path.getsize(file_path))
        print(file_list)
        # 2.获取场景预设文件及其大小
        file_checked_list, file_checked_size_list = parse_input.get_list_by_scene_name(scene_name=scene_name)
        # 3.获取分割完成的文件
        split_file_list = global_var.store_memory[username]["split_file"]
        # 4.构建元组，包含文件时间信息和四色DMT属性
        from llm_langchain import global_var as langchain_global_var
        from app_chat.homework_classifier import normalize_homework_attrs
        for i in range(len(file_list)):
            file_path = os.path.join(user_path, file_list[i])
            file_time = os.path.getmtime(file_path)  # 获取文件修改时间
            # 🔥 使用文件创建时间而不是修改时间，保持初次上传的排序顺序
            # 如果文件存在，优先使用创建时间；如果是新文件，使用修改时间
            # try:
            #     file_time = os.path.getctime(file_path)  # 获取文件创建时间（初次上传时间）
            # except:
            #     file_time = os.path.getmtime(file_path)  # 如果获取创建时间失败，使用修改时间作为后备

            # 🔥 获取文档的四色DMT属性（优先从数据库读取，如果没有再从segments metadata读取）
            main_four_color = ''
            secondary_four_color = ''
            dmt_level = ''
            homework_attrs = normalize_homework_attrs({})
            # 1. 优先从数据库读取
            try:
                realName = username.split('_')[0] if '_' in username else username
                book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                    realName) + 1 else None

                # 如果没有从username解析出bookName，尝试通过scene_name查找
                if not book_name:
                    try:
                        scene_obj = scene.objects.get(sceneDescription=scene_name)
                        notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                        if notebook:
                            book_name = notebook.bookName
                    except:
                        pass

                if book_name:
                    try:
                        notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                        if notebook.documentFourColorDMT:
                            doc_attrs = json.loads(notebook.documentFourColorDMT)
                            if file_list[i] in doc_attrs:
                                attrs = doc_attrs[file_list[i]]
                                attrs = attrs if isinstance(attrs, dict) else {}
                                main_four_color = attrs.get('main_four_color', '')
                                secondary_four_color = attrs.get('secondary_four_color', '')
                                dmt_level = attrs.get('dmt_level', '')
                                homework_attrs = normalize_homework_attrs(attrs)
                                print(
                                    f"[card_getAllUserFiles] 从数据库读取文件 {file_list[i]} 的四色DMT属性: 主色={main_four_color}, 辅色={secondary_four_color}, DMT={dmt_level}")
                    except Exception as e:
                        print(f"[card_getAllUserFiles] 从数据库读取文件 {file_list[i]} 的四色DMT属性失败: {e}")
            except Exception as e:
                print(f"[card_getAllUserFiles] 获取UserNotebook失败: {e}")

            # 2. 如果数据库中没有，再从segments metadata读取
            if not main_four_color and not dmt_level:
                try:
                    segments = langchain_global_var.get_user_split(username, file_list[i])
                    if segments and len(segments) > 0:
                        first_segment = segments[0]
                        if first_segment.metadata:
                            main_four_color = first_segment.metadata.get('main_four_color', '')
                            secondary_four_color = first_segment.metadata.get('secondary_four_color', '')
                            dmt_level = first_segment.metadata.get('dmt_level', '')
                            homework_attrs = normalize_homework_attrs(first_segment.metadata)
                            if main_four_color or dmt_level:
                                print(
                                    f"[card_getAllUserFiles] 从segments metadata读取文件 {file_list[i]} 的四色DMT属性: 主色={main_four_color}, 辅色={secondary_four_color}, DMT={dmt_level}")
                except Exception as e:
                    print(f"[card_getAllUserFiles] 从segments metadata获取文件 {file_list[i]} 的四色DMT属性失败: {e}")

            # 音频/白名单txt/Skill包zip 特殊处理：
            # 重启后 split_file_list 可能为空，导致这些文件在前端显示为 split=0（不可选中）
            file_extension = os.path.splitext(file_list[i])[1].lower()
            audio_extensions = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm']
            is_audio_file = file_extension in audio_extensions
            is_skill_zip = file_extension == '.zip'
            is_long_txt = file_list[i].endswith("_LONG.txt")
            is_timestamp_txt = re.match(r"^.+_\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2}\.txt$", file_list[i]) is not None
            is_whitelist_txt = is_long_txt or is_timestamp_txt
            file_exists = os.path.exists(file_path) and os.path.isfile(file_path)
            if (is_audio_file or is_whitelist_txt or is_skill_zip) and file_exists:
                split_status = 1
            else:
                split_status = 1 if file_list[i] in split_file_list else 0

            file_info_list.append((file_list[i], size_list[i], file_list[i] in file_checked_list,
                                   split_status, file_time,
                                   main_four_color, secondary_four_color, dmt_level,
                                   homework_attrs.get('is_k12_homework', False),
                                   homework_attrs.get('is_homework_pdf', False),
                                   homework_attrs.get('homework_subject', 'unknown'),
                                   homework_attrs.get('homework_stage', 'unknown'),
                                   homework_attrs.get('homework_confidence', 0.0),
                                   homework_attrs.get('homework_reason', ''),
                                   homework_attrs.get('homework_checked_at', '')))  # 🔥 添加四色DMT/作业属性
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

    # 🔥 为每个文件添加四色DMT属性信息（从文档segments的metadata中获取）
    from llm_langchain import global_var as langchain_global_var
    for i, file_info in enumerate(file_info_list):
        try:
            filename = file_info[0]
            # 获取该文档的segments
            segments = langchain_global_var.get_user_split(username, filename)
            if segments and len(segments) > 0:
                first_segment = segments[0]
                if first_segment.metadata:
                    main_four_color = first_segment.metadata.get('main_four_color', '')
                    secondary_four_color = first_segment.metadata.get('secondary_four_color', '')
                    dmt_level = first_segment.metadata.get('dmt_level', '')
                    # 将四色DMT属性添加到文件信息中（作为元组的新元素）
                    file_info_list[i] = file_info + (main_four_color, secondary_four_color, dmt_level)
                else:
                    file_info_list[i] = file_info + ('', '', '')
            else:
                file_info_list[i] = file_info + ('', '', '')
        except Exception as e:
            print(f"[card_getAllUserFiles] 获取文件 {file_info[0]} 的四色DMT属性失败: {e}")
            file_info_list[i] = file_info + ('', '', '')

    # 🔥 后台异步检测并处理文档预处理章节摘要（不阻塞前端）
    def process_documents_pre_summary_async():
        try:
            from llm_langchain.parse_input import process_documents_pre_summary_batch
            import os

            realName = username.split('_')[0] if '_' in username else username
            book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                realName) + 1 else None

            # 如果没有从username解析出bookName，尝试通过scene_name查找
            if not book_name:
                try:
                    scene_obj = scene.objects.get(sceneDescription=scene_name)
                    notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                    if notebook:
                        book_name = notebook.bookName
                except:
                    pass

            if not book_name:
                print(f"[文档预处理章节摘要] 无法确定book_name，跳过处理")
                return

            # 获取UserNotebook
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
            except Exception as e:
                print(f"[文档预处理章节摘要] 获取UserNotebook失败: {e}")
                return

            # 读取预处理状态
            pre_summary_status = {}
            try:
                if notebook.documentPreSummaryStatus:
                    pre_summary_status = json.loads(notebook.documentPreSummaryStatus)
            except json.JSONDecodeError:
                pre_summary_status = {}

            # 获取用户目录下的所有文件
            user_path = './received_dir/user_raw_file/' + username
            if not os.path.exists(user_path):
                return

            # 筛选出需要处理的文档（PDF和TXT，且状态为未处理或不存在）
            to_process = []
            for f in os.listdir(user_path):
                if os.path.isdir(user_path + '/' + f):
                    continue
                if f.endswith('_transFTWYGUHX.pdf'):
                    continue

                # 只处理PDF和TXT文件
                if not (f.lower().endswith('.pdf') or f.lower().endswith('.txt')):
                    continue

                # 检查状态（如果状态为False或不存在，则需要处理）
                status = pre_summary_status.get(f, False)
                if status == False:
                    to_process.append(f)

            if to_process:
                print(f"[文档预处理章节摘要] 检测到 {len(to_process)} 个文档需要处理")
                # 批量处理（3并发，防重复）
                process_documents_pre_summary_batch(realName, book_name, username, to_process)
            else:
                print(f"[文档预处理章节摘要] 所有文档已处理完成")

        except Exception as e:
            print(f"[文档预处理章节摘要] 后台处理异常: {e}")
            import traceback
            traceback.print_exc()

    # 启动后台异步处理文档预处理章节摘要
    import threading
    threading.Thread(target=process_documents_pre_summary_async, daemon=True).start()

    # 🔥 旧本子 Skill 补生成：与 PreSummary 是否已完成解耦
    # （原先挂在 to_process 里，旧文档 PreSummary 已 true 时永远不会 spawn Skill）
    def backfill_document_skills_async():
        try:
            from app_chat import skills_store as skills_store
            from app_chat.skill_generate import spawn_document_skill_async, update_document_skill_status
            from zym.models import UserNotebook

            realName = username.split('_')[0] if '_' in username else username
            book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
            if not book_name:
                try:
                    scene_obj = scene.objects.get(sceneDescription=scene_name)
                    notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                    if notebook:
                        book_name = notebook.bookName
                except Exception:
                    pass
            if not book_name:
                print(f"[Skill补生成] 无法确定 book_name，跳过: {username}")
                return

            user_path = './received_dir/user_raw_file/' + username
            if not os.path.exists(user_path):
                return

            skill_status = {}
            try:
                nb = UserNotebook.objects.get(username=realName, bookName=book_name)
                raw = getattr(nb, "documentSkillStatus", "") or ""
                skill_status = json.loads(raw) if raw else {}
            except Exception:
                skill_status = {}

            to_skill = []
            for f in os.listdir(user_path):
                if os.path.isdir(os.path.join(user_path, f)):
                    continue
                if f.endswith('_transFTWYGUHX.pdf'):
                    continue
                if not (f.lower().endswith('.pdf') or f.lower().endswith('.txt')):
                    continue
                st = skill_status.get(f)
                if st is True or st == 'pending':
                    continue
                if skills_store.find_skill_by_source_doc(username, f):
                    # 磁盘已有但状态未记：补 true，不重跑模型
                    try:
                        update_document_skill_status(realName, book_name, f, True)
                    except Exception:
                        pass
                    continue
                # 尚无 PreSummary 的留给批量 PreSummary→Skill，避免抢跑吃不到摘要
                file_ext = os.path.splitext(f)[1][1:] if os.path.splitext(f)[1] else ""
                file_base = os.path.splitext(f)[0]
                pre_path = os.path.join(user_path, "pre_summary", f"{file_base}_Presummary_{file_ext}.md")
                if not os.path.isfile(pre_path):
                    print(f"[Skill补生成] 尚无 PreSummary，交由批量链路生成: {f}")
                    continue
                to_skill.append(f)

            if not to_skill:
                print(f"[Skill补生成] 无需补生成: {username}")
                return

            print(f"[Skill补生成] 检测到 {len(to_skill)} 个旧文档需生成 Skill: {to_skill}")
            for docs_name in to_skill:
                try:
                    update_document_skill_status(realName, book_name, docs_name, "pending")
                except Exception:
                    pass
                spawn_document_skill_async(realName, username, docs_name)
                print(f"[Skill补生成] 已 spawn: {docs_name}")
        except Exception as e:
            print(f"[Skill补生成] 后台异常: {e}")
            import traceback
            traceback.print_exc()

    threading.Thread(target=backfill_document_skills_async, daemon=True).start()

    # 🔥 后台异步处理已有文档的四色DMT属性（不阻塞前端）
    def process_existing_documents_async():
        try:
            from llm_langchain import global_var as langchain_global_var
            from langchain_community.vectorstores import Chroma
            import llm_langchain.util as langchain_util
            from app_chat.homework_classifier import (
                analyze_homework_document_attributes,
                has_homework_attrs,
                normalize_homework_attrs,
            )

            print(f"[card_getAllUserFiles] 开始后台处理已有文档的四色DMT属性: username={username}")

            # 获取已分割的文件列表
            split_file_list = langchain_global_var.store_memory.get(username, {}).get("split_file", [])

            # 获取向量数据库
            db_path = langchain_util.db_path
            collection_name = langchain_util.construct_collection(username)

            try:
                # 🔥 使用parse_input中的create_embeddings_with_retry函数
                from llm_langchain.parse_input import create_embeddings_with_retry
                embeddings = create_embeddings_with_retry()
                vector_store = Chroma(
                    collection_name=collection_name,
                    embedding_function=embeddings,
                    persist_directory=db_path
                )
            except Exception as e:
                print(f"[card_getAllUserFiles] 获取向量数据库失败: {e}")
                return

            # 对每个已分割的文件进行处理
            for docs_name in split_file_list:
                # 🔥 检查是否正在处理，避免重复分析
                doc_key = f"{username}:{docs_name}"
                with document_processing_lock:
                    if doc_key in document_processing_docs:
                        print(f"[card_getAllUserFiles] 文档 {docs_name} 正在处理中，跳过")
                        continue
                    document_processing_docs.add(doc_key)

                try:
                    # 获取该文档的所有segment
                    segments = langchain_global_var.get_user_split(username, docs_name)

                    # 如果segments不在内存中，尝试从文件重新加载
                    if not segments or len(segments) == 0:
                        print(f"[card_getAllUserFiles] 文档 {docs_name} 的segments不在内存中，尝试从文件重新加载")
                        try:
                            # 重新加载文档（仅用于分析，不阻塞）
                            import os
                            from llm_langchain.parse_input import get_loader
                            from langchain.text_splitter import RecursiveCharacterTextSplitter

                            file_path = langchain_util.construct_file_path(username, docs_name)
                            if os.path.exists(file_path):
                                loader = get_loader(file_path)
                                text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
                                segments = text_splitter.split_documents(loader.load())
                            else:
                                print(f"[card_getAllUserFiles] 文档文件不存在: {file_path}")
                                continue
                        except Exception as e:
                            print(f"[card_getAllUserFiles] 从文件重新加载文档 {docs_name} 失败: {e}")
                            continue

                    # 🔥 检查文档是否已有四色DMT属性（优先从数据库检查）
                    main_four_color = ''
                    secondary_four_color = ''
                    dmt_level = ''
                    existing_doc_attrs = {}

                    # 1. 先检查数据库
                    try:
                        realName = username.split('_')[0] if '_' in username else username
                        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                            realName) + 1 else None

                        # 如果没有从username解析出bookName，尝试通过scene_name查找
                        if not book_name:
                            try:
                                scene_obj = scene.objects.get(sceneDescription=scene_name)
                                notebook = UserNotebook.objects.filter(username=realName,
                                                                       sid=scene_obj.sid).first()
                                if notebook:
                                    book_name = notebook.bookName
                            except:
                                pass

                        if book_name:
                            try:
                                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                                if notebook.documentFourColorDMT:
                                    doc_attrs = json.loads(notebook.documentFourColorDMT)
                                    if docs_name in doc_attrs:
                                        attrs = doc_attrs[docs_name]
                                        existing_doc_attrs = attrs if isinstance(attrs, dict) else {}
                                        main_four_color = existing_doc_attrs.get('main_four_color', '')
                                        secondary_four_color = existing_doc_attrs.get('secondary_four_color', '')
                                        dmt_level = existing_doc_attrs.get('dmt_level', '')
                            except:
                                pass
                    except:
                        pass

                    # 2. 如果数据库中没有，再检查segments metadata
                    if not main_four_color and not dmt_level:
                        first_segment = segments[0] if segments else None
                        if first_segment and first_segment.metadata:
                            main_four_color = first_segment.metadata.get('main_four_color', '')
                            secondary_four_color = first_segment.metadata.get('secondary_four_color', '')
                            dmt_level = first_segment.metadata.get('dmt_level', '')
                            existing_doc_attrs = dict(first_segment.metadata)

                    is_pdf_doc = docs_name.lower().endswith('.pdf')
                    homework_checked = has_homework_attrs(existing_doc_attrs)

                    # 如果已经有所有属性，跳过；PDF 还要检查是否已有作业判定
                    if main_four_color and dmt_level and (not is_pdf_doc or homework_checked):
                        print(f"[card_getAllUserFiles] 文档 {docs_name} 已有完整属性，跳过")
                        continue

                    # 合并所有segment的完整内容
                    full_content = "\n".join([seg.page_content for seg in segments])

                    # 🔥 获取场景信息
                    from app_chat.scene_context_helper import get_scene_info_from_username
                    scene_name_info, sub_scene_name_info, scene_summary_info, notebook_desc_info = get_scene_info_from_username(
                        username)

                    attributes = {
                        'main_four_color': main_four_color,
                        'secondary_four_color': secondary_four_color,
                        'dmt_level': dmt_level,
                    }
                    if not main_four_color or not dmt_level:
                        # 分析文档属性（传递场景信息）
                        from app_chat.document_analyzer import analyze_document_attributes
                        attributes.update(analyze_document_attributes(
                            full_content,
                            scene_name=scene_name_info,
                            sub_scene_name=sub_scene_name_info,
                            scene_summary=scene_summary_info,
                            notebook_description=notebook_desc_info
                        ))
                    if is_pdf_doc:
                        if homework_checked:
                            attributes.update(normalize_homework_attrs(existing_doc_attrs))
                        else:
                            attributes.update(analyze_homework_document_attributes(
                                full_content,
                                docs_name,
                                scene_name=scene_name_info,
                                sub_scene_name=sub_scene_name_info,
                                scene_summary=scene_summary_info,
                                notebook_description=notebook_desc_info,
                                pdf_path=os.path.join(user_path, docs_name)
                            ))

                    # 更新所有segment的metadata
                    for seg in segments:
                        if not seg.metadata:
                            seg.metadata = {}
                        seg.metadata['main_four_color'] = attributes.get('main_four_color', '')
                        seg.metadata['secondary_four_color'] = attributes.get('secondary_four_color', '')
                        seg.metadata['dmt_level'] = attributes.get('dmt_level', '')
                        for key in (
                            'is_k12_homework', 'is_homework_pdf', 'homework_subject', 'homework_stage',
                            'homework_confidence', 'homework_reason', 'homework_checked_at', 'homework_analyzer_version'
                        ):
                            if key in attributes:
                                seg.metadata[key] = attributes.get(key)

                    # 更新global_var中的segment（如果存在）
                    try:
                        langchain_global_var.set_user_split(username, docs_name, segments)
                    except:
                        pass  # 如果更新失败，不影响流程

                    # 🔥 将属性保存到数据库（UserNotebook.documentFourColorDMT字段）
                    try:
                        # 尝试通过username和scene_name获取UserNotebook
                        # username可能是"用户名_本子名"格式，或者我们需要通过scene_name查找
                        realName = username.split('_')[0] if '_' in username else username
                        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                            realName) + 1 else None

                        # 如果没有从username解析出bookName，尝试通过scene_name查找
                        if not book_name:
                            try:
                                scene_obj = scene.objects.get(sceneDescription=scene_name)
                                notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                                if notebook:
                                    book_name = notebook.bookName
                            except:
                                pass

                        # 如果仍然没有bookName，跳过数据库保存（只保存到内存）
                        if book_name:
                            try:
                                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                                # 读取现有的JSON数据
                                try:
                                    existing_data = json.loads(
                                        notebook.documentFourColorDMT) if notebook.documentFourColorDMT else {}
                                except json.JSONDecodeError:
                                    existing_data = {}

                                # 更新JSON数据：合并写入，保留已有字段
                                current_attrs = existing_data.get(docs_name, {}) if isinstance(existing_data.get(docs_name, {}), dict) else {}
                                for key in ('main_four_color', 'secondary_four_color', 'dmt_level'):
                                    value = attributes.get(key, '')
                                    if value or key not in current_attrs:
                                        current_attrs[key] = value
                                for key in (
                                    'is_k12_homework', 'is_homework_pdf', 'homework_subject', 'homework_stage',
                                    'homework_confidence', 'homework_reason', 'homework_checked_at', 'homework_analyzer_version'
                                ):
                                    if key in attributes:
                                        current_attrs[key] = attributes.get(key)
                                existing_data[docs_name] = current_attrs
                                notebook.documentFourColorDMT = json.dumps(existing_data, ensure_ascii=False)
                                notebook.save()
                                print(f"[card_getAllUserFiles] 已将文档 {docs_name} 的四色DMT属性保存到数据库")
                            except Exception as e:
                                print(f"[card_getAllUserFiles] 保存文档 {docs_name} 的四色DMT属性到数据库失败: {e}")
                    except Exception as e:
                        print(f"[card_getAllUserFiles] 获取UserNotebook失败: {e}")

                    print(
                        f"[card_getAllUserFiles] 文档 {docs_name} 分析完成: 主色={attributes.get('main_four_color')}, 辅色={attributes.get('secondary_four_color')}, DMT={attributes.get('dmt_level')}")

                except Exception as e:
                    print(f"[card_getAllUserFiles] 处理文档 {docs_name} 失败: {e}")
                finally:
                    # 🔥 处理完成后，从正在处理的集合中移除
                    with document_processing_lock:
                        document_processing_docs.discard(doc_key)

            print(f"[card_getAllUserFiles] 已完成所有已有文档的四色DMT属性处理")

        except Exception as e:
            print(f"[card_getAllUserFiles] 后台处理已有文档失败: {e}")

    # 启动后台线程进行处理（不阻塞）
    process_thread = threading.Thread(target=process_existing_documents_async, daemon=True)
    process_thread.start()

    response['content'] = file_info_list
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


@csrf_exempt
def card_getFileByName(request):
    data = json.loads(request.body)

    username = data["username"]
    _ensure_user_runtime_context(username)
    filename = data["filename"]
    fileNameList = data["fileNameList"]
    leftSelectList = data["leftSelectList"]
    rightSelectList = data["rightSelectList"]
    depth_suggestion = data.get("depth_suggestion", "")  # 获取深度建议
    print(username + "请求获取文档摘要:" + filename + "，list info:")
    # file_list = fileNameList.split(',')
    try:
        # 这一步将字符串 '["a,b.txt", "c.txt"]' 还原为列表
        file_list = json.loads(fileNameList)
    except json.JSONDecodeError:
        # 兼容旧数据的兜底逻辑（如果确实传了非JSON的字符串）
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

    # 🔥 检测预处理章节摘要文件，如果没有则生成
    def check_and_process_pre_summary():
        try:
            from llm_langchain.parse_input import process_document_pre_summary

            # 只处理PDF和TXT文件
            if not (filename.lower().endswith('.pdf') or filename.lower().endswith('.txt')):
                return

            # 构建预处理摘要文件路径
            file_ext = os.path.splitext(filename)[1][1:] if os.path.splitext(filename)[1] else ""
            file_base_name = os.path.splitext(filename)[0]
            base_dir = f"./received_dir/user_raw_file/{username}/pre_summary"
            summary_filename = f"{file_base_name}_Presummary_{file_ext}.md"
            summary_path = os.path.join(base_dir, summary_filename)

            realName = data.get("realName", username.split('_')[0] if '_' in username else username)
            # 先保证 PreSummary，再补 Skill（避免新文件 Skill 抢跑吃不到摘要）
            if not os.path.exists(summary_path):
                print(f"[card_getFileByName] 检测到预处理章节摘要文件不存在，开始生成: {filename}")
                success, error_msg = process_document_pre_summary(realName, username, filename)
                if success:
                    print(f"[card_getFileByName] ✅ PreSummary 生成成功: {filename}")
                else:
                    print(f"[card_getFileByName] ❌ PreSummary 生成失败（仍将尝试 Skill）: {filename}, {error_msg}")
            else:
                print(f"[card_getFileByName] PreSummary 已存在: {filename}")

            try:
                from app_chat import skills_store as skills_store
                from app_chat.skill_generate import spawn_document_skill_async
                if not skills_store.find_skill_by_source_doc(username, filename):
                    print(f"[card_getFileByName] 无关联 Skill，在 PreSummary 检查后触发生成: {filename}")
                    spawn_document_skill_async(realName, username, filename)
                else:
                    print(f"[card_getFileByName] 已有关联 Skill，跳过生成: {filename}")
            except Exception as _sk_e:
                print(f"[card_getFileByName] Skill 补生成跳过: {_sk_e}")
        except Exception as e:
            print(f"[card_getFileByName] 检测预处理章节摘要时出错: {e}")
            import traceback
            traceback.print_exc()

    # 🔥 检测图片分析摘要文件，如果没有则补做
    def check_and_process_pre_image_summary():
        try:
            from llm_langchain.parse_input import process_pre_image_summary

            # 只处理PDF文件
            if not filename.lower().endswith('.pdf'):
                return

            # 构建图片分析摘要文件路径
            file_base_name = os.path.splitext(filename)[0]
            pre_image_summary_dir = f"./received_dir/user_raw_file/{username}/pre_image_summary"
            origin_filename = f"{file_base_name}_PreImageOrigin_pdf.md"
            summary_filename = f"{file_base_name}_PreImageSummary_pdf.md"
            origin_path = os.path.join(pre_image_summary_dir, origin_filename)
            summary_path = os.path.join(pre_image_summary_dir, summary_filename)

            # 检查：如果存在PreImageOrigin但没有PreImageSummary，则补做
            if os.path.exists(origin_path) and not os.path.exists(summary_path):
                print(f"[card_getFileByName] 检测到PreImageOrigin存在但PreImageSummary不存在，开始补做: {filename}")
                # 异步生成图片分析摘要（不阻塞返回）
                success, error_msg = process_pre_image_summary(username, filename, origin_path)
                if success:
                    print(f"[card_getFileByName] 图片分析摘要生成成功: {filename}")
                else:
                    print(f"[card_getFileByName] 图片分析摘要生成失败: {filename}, 错误: {error_msg}")
            elif not os.path.exists(origin_path):
                print(f"[card_getFileByName] PreImageOrigin文件不存在，无需补做图片分析摘要: {filename}")
            else:
                print(f"[card_getFileByName] 图片分析摘要文件已存在: {filename}")
        except Exception as e:
            print(f"[card_getFileByName] 检测图片分析摘要时出错: {e}")
            import traceback
            traceback.print_exc()

    # 在后台线程中异步处理，不阻塞主流程
    import threading
    pre_summary_thread = threading.Thread(target=check_and_process_pre_summary, daemon=True)
    pre_summary_thread.start()

    pre_image_summary_thread = threading.Thread(target=check_and_process_pre_image_summary, daemon=True)
    pre_image_summary_thread.start()

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
    original_topic_prompt = None  # 初始化变量
    try:
        # FIXME
        # content = get_suma.get_summary_user_docs_way_split(user_name=username, docs_name=file_list,
        #                                                    get_way=left_select_list)
        # 如果有深度建议，将其传递给topic生成函数
        if depth_suggestion:
            # 解析深度建议，提取主题建议部分
            depth_suggestion_topic = ""  # 主题建议
            if "【主题关键词建议】" in depth_suggestion:
                # 如果有主题建议部分，提取它
                parts = depth_suggestion.split("【主题关键词建议】")
                if len(parts) >= 2:
                    depth_suggestion_topic = parts[1].strip()
            else:
                # 如果没有分隔符，说明是旧格式或纯主题建议
                depth_suggestion_topic = depth_suggestion

            # 将深度建议附加到topic_prompt中
            original_topic_prompt = global_var.store_memory[username]["prompt"]["LUI1"]["topic"]
            enhanced_topic_prompt = original_topic_prompt + "\n\n【主题提取建议】（小模型提供，供你作为重要参考之一）：\n" + depth_suggestion_topic

            # 临时保存增强后的prompt
            global_var.store_memory[username]["prompt"]["LUI1"]["topic"] = enhanced_topic_prompt

        print(f"[views调用] filename={filename}, file_list={file_list}")
        topic = get_topic.get_topic_user_docs_way_split(user_name=username, docs_name=file_list,
                                                        get_way=left_select_list, main_doc_name=filename)

        # 如果有深度建议，恢复原始prompt
        if depth_suggestion:
            global_var.store_memory[username]["prompt"]["LUI1"]["topic"] = original_topic_prompt
        # FIXME END

        # content = '我是后端传来的摘要，因为gpt4要花钱所以只能这样，现在的我花不了一分钱，可以一直点'
        # topic = ['topic1', 'topic2', 'topic3']

        # response['content'] = content
        response['topic'] = topic
        response['msg'] = 'success'
        response['error_num'] = 0
        return JsonResponse(response)
    except Exception as e:
        # 如果有深度建议，恢复原始prompt
        if depth_suggestion:
            global_var.store_memory[username]["prompt"]["LUI1"]["topic"] = original_topic_prompt

        print(str(e))
        response['msg'] = 'failed'
        response['error_num'] = 1
        return JsonResponse(response)


@csrf_exempt
def get_file_summary(request):
    print("[DEBUG] 摘要窗口收到请求：", request.body)
    data = request.POST
    return StreamingHttpResponse(stream_generator_sync_summa(data), content_type='text/event-stream')


@csrf_exempt
def get_model_eval(request):
    print("[DEBUG] 卡片窗口收到请求：", request.body)
    data = request.POST
    return StreamingHttpResponse(stream_generator_sync_rate(data), content_type='text/event-stream')


@csrf_exempt
def card_getTextByName(request):
    data = json.loads(request.body)

    username = data["username"]
    _ensure_user_runtime_context(username)
    filename = data["filename"]
    print(username + "请求获取文档的文本:" + filename)

    file_list = [filename]
    # FIXME
    text, images = parse_input.get_docs_by_user_doc(user_name=username, docs_name=file_list)
    # FIXME END
    # text = ['为什么我也要写死，因为ghp的代码太慢了以至于成功率很低']

    # print(text[0], images[0])
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

    # 获取图片原始文件名（不含扩展名）
    image_basename = os.path.splitext(filename)[0]
    dmt_result_dir = os.path.join(settings.MEDIA_ROOT, 'dmt_analysis', username, 'results')
    latest_file = None
    latest_timestamp = None
    if os.path.exists(dmt_result_dir):
        for file in os.listdir(dmt_result_dir):
            if file.endswith(f"{image_basename}_result.json"):
                # 按下划线分割文件名，获取前缀的时间戳部分
                parts = file.split('_')
                if len(parts) >= 3:
                    timestamp_prefix = f"{parts[0]}_{parts[1]}"
                    try:
                        # 假设时间戳格式为YYYYMMDD_HHMMSS
                        timestamp = datetime.strptime(timestamp_prefix, "%Y%m%d_%H%M%S")
                        if latest_timestamp is None or timestamp > latest_timestamp:
                            latest_timestamp = timestamp
                            latest_file = file
                    except Exception:
                        continue
    response = {}
    # latest_file 现在是时间戳最晚的文件名（如果存在）
    if latest_file:
        # 构建完整的文件路径
        result_file_path = os.path.join(dmt_result_dir, latest_file)
        with open(result_file_path, 'r', encoding='utf-8') as f:
            try:
                content = json.load(f)
                response['result_type'] = 'dmt_analysis'
            except json.JSONDecodeError:
                content = None
                response['result_type'] = 'dmt_analysis_error'
    else:
        content = parse_input.get_pdf_image_sum(user_name=username, doc_name=filename, seq=int(imgid))
        response['result_type'] = 'pdf_image_sum'
    # print(content)
    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0

    # 查找对应的笔记本
    try:
        # 查询对应的笔记本
        notebook = UserNotebook.objects.get(username=realName, bookName=book_name)

        # 检查MayImgDocHLScore字段是否为空
        if notebook.MayImgDocHLScore:
            try:
                # 尝试解析为JSON
                img_scores = json.loads(notebook.MayImgDocHLScore)
                key = f"{filename}-{int(imgid) + 1}" if mode == "pdf" else f"{filename}"
                # 检查是否包含filename的字段
                if key in img_scores:
                    # 将评分添加到响应中
                    response['HLScore'] = img_scores[key]
                else:
                    # 检查是否正在异步计算
                    status_info = get_hlscore_status(key)

                    if status_info['status'] == 'processing':
                        # 正在计算中，返回状态信息
                        # response['HLScore'] = "计算中..."
                        response['HLScoreStatus'] = 'processing'
                    elif status_info['status'] == 'completed':
                        # 计算完成，返回结果
                        response['HLScore'] = status_info['result']
                        response['HLScoreStatus'] = 'completed'
                    elif status_info['status'] == 'failed':
                        # 计算失败，重新启动异步计算
                        # response['HLScore'] = "计算失败，正在重试..."
                        response['HLScoreStatus'] = 'retrying'
                        try:
                            base64_image = global_var.store_memory[username]["images"][filename][int(imgid)]
                            thread = Thread(
                                target=async_calculate_hlscore,
                                args=(username, realName, filename, imgid, content, base64_image, key),
                                daemon=True
                            )
                            thread.start()
                            print(f"重新启动异步线程计算 HLScore: {username}/{filename}-{imgid}")
                        except Exception as e:
                            print(f"重新启动异步 HLScore 计算线程失败: {str(e)}")
                    else:
                        # 首次计算，启动异步线程
                        # response['HLScore'] = "开始计算..."
                        response['HLScoreStatus'] = 'starting'
                        try:
                            base64_image = global_var.store_memory[username]["images"][filename][int(imgid)]
                            # 创建异步线程来计算 HLScore
                            thread = Thread(
                                target=async_calculate_hlscore,
                                args=(username, realName, filename, imgid, content, base64_image, key),
                                daemon=True  # 设置为守护线程，主程序退出时自动结束
                            )
                            thread.start()
                            print(f"已启动异步线程计算 HLScore: {username}/{filename}-{imgid}")

                            # 立即返回，不等待计算完成
                            # 客户端可以在下次请求时获取到计算好的 HLScore

                        except Exception as e:
                            response['HLScore'] = "启动计算失败"
                            response['HLScoreStatus'] = 'error'
                            print(f"启动异步 HLScore 计算线程失败: {str(e)}")
            except json.JSONDecodeError:
                # 如果不是有效的JSON，则忽略
                pass
    except Exception as e:
        # 如果查询出错，记录错误但不影响主要功能
        print(f"获取HLScore出错: {str(e)}")
        # 这里不返回错误，保持原有功能正常

    return JsonResponse(response)


@csrf_exempt
def update_img_text_stream(request):
    print("[DEBUG] 更新图片摘要收到请求：", request.body)
    data = request.POST
    return StreamingHttpResponse(stream_generator_update_img_text(data), content_type='text/event-stream')


def stream_generator_update_img_text(data):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        generator = stream_img_text_generator(data)
        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                break
    finally:
        loop.close()


async def stream_img_text_generator(data, pixel_limit=12000000):
    username = data["username"]
    filename = data["filename"]
    imgid = data["imgid"]
    content = data["content"]
    image_path = util.construct_file_path(username, filename)
    # 打开图片
    image = Image.open(image_path)
    # 获取图片尺寸
    width, height = image.size
    print(username + "请求更新文档图片:" + filename + "-" + imgid)
    # 获取图片后缀
    file_extension = os.path.splitext(image_path)[1][1:]
    file_extension = "jpeg" if file_extension == "jpg" else file_extension

    merge_content = ""
    if content != "":
        merge_content = content

    response_data = {}
    start_time = time.time()
    try:
        # client = OpenAI(
        #     # api_key='[redacted]',
        #     api_key='[redacted]',
        #     base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
        #     default_headers={"x-foo": "true"},
        # )
        if width * height > pixel_limit:
            user_prompt = """请对图片进行专业多层次分析解读，图片可能有不同类型，但广义上都可以归为下面的【学习类文档】，因为图片都是需要学习、认知和理解的，
所以请你从此类型视角开始思考，主要是理解图片要分层的思路，再进一步细化落实到图片所属的具体类别。

【学习类文档分析】(作业/试卷/笔记等)
如果图片含有作业、试卷、笔记等纸质版面，你的表述中必须包含：【理解和陈述】、【评价和建议】这两对，一共四个要素，其中理解是整体性感知，
陈述是对主体中具体内容或文字的识别（类似OCR的文字识别），这一对很基础！至少要占你篇幅的70%以上；评价是对于其书写规范性、位置合理性
等的评述，建议是对书写者改进的建议等，这一对是拔高内容，占20%到30%左右，作为辅助。
请你一定注意不可以过于笼统！例如不能只说“手写层字迹工整，排版规范”，你必须要说具体写了什么内容，主题是什么、有标题吗、与哪些标注关联
之类的具体内容，你需要尽量表述全面、完整，少遗漏信息！如果图片较为复杂，你也需要尽可能地识别，并一定要说具体写了什么文字，这很重要！
方法上，请采用多层次分析法对此类图片进行专业解读（这里涉及的点都要包含）：
1. 版面结构：识别主要区域、是否有子版面划分等，分析空间关系与逻辑连接
2. 多层内容依次解读：
    - 底图层：图片本身的整体感知性理解，即版面内一些显眼突出的形状，你需要通过一定意象感，做一做感知，例如“xx像是xx”这类的描述
    - 印刷层：教材/试题等印刷，具体印了哪些文字
    - 涂鸦层：批注符号、圈点、下划线等标记（涂鸦勾画等其实是思考过程的体现，也很重要，不可以忽视这层！），具体涂鸦了什么
    - 手写层：有特点的、较为正式的手写字迹，务必涉及具体写了什么（即使认不清也要试着认）
3. 层间关联：分析各层次间的对应关系，特别关注手写、涂鸦、印刷内容的对应及关联关系
4. 另外注意：
    - 对图中一些较为特别的点加以强调，例如图中如果有明确的【标题】（一般在版面最上方居中的位置，且黑色加粗）或【主题】，你一定要在最开头就把它识别出来并进行陈述！
    - 涂鸦和手写层虽然都是书写，也有关联性，但你描述时需要分开（格式上分开，内容上要找关联），涂鸦层比较随意，偏向思考过程；手写层比较正式，偏向作答过程
    - 你需要说明作业/试卷/笔记等学习类图片最可能是针对哪些对象的，如什么阶段（小学初中高中大学等）、什么年级等等
    - 如果没有涂鸦笔迹，也需要简单说明一下

另外如果是原理图、绘画或其他类型的非明显分层图片，也可以用多层次注意的类似思路来深入理解
请直接给出自然、完整的图片描述，用中文描述，控制在1000字以内。
"""
            base64_image = global_var.store_memory[username]["images"][filename][int(imgid)]
            messages = [
                {"role": "system", "content": [{"text": "You are a helpful assistant."}]},
                {'role': 'user', 'content': [{"image": f"data:image/{file_extension};base64,{base64_image}"}, {'text': user_prompt}]}
            ]
            response = await asyncio.wait_for(
                to_thread(  # 将同步调用转为异步任务
                    MultiModalConversation.call,
                    api_key=_public_config.secret('NKCN_LLM_DASHSCOPE_API_KEY'),
                    model='qwen-vl-max-latest',
                    messages=messages,
                    vl_high_resolution_images=True,
                    stream=True,
                    incremental_output=True,
                ),
                timeout=time_out  # 自定义超时时间（优先级更高）
            )
            print(f"获取图片描述响应创建用时: {time.time() - start_time}秒")
            start_time = time.time()
            for chunk in response:
                if chunk["output"]["choices"][0]["message"].content:
                    new_content = chunk["output"]["choices"][0]["message"].content[0]["text"]
                    response_data['model'] = 'qwen-vl-max-latest'
                    response_data['content'] = new_content
                    yield json.dumps(response_data, ensure_ascii=False)
        else:
            old_content = get_pdf_image_sum(user_name=username, doc_name=filename, seq=int(imgid))
            if merge_content == "":
                prompt = image_retry_summary_prompt.format(old_content=old_content)
            else:
                prompt = image_merge_summary_prompt.format(old_content=old_content, merge_content=merge_content)
            client = OpenAI(
                api_key=_public_config.secret('OPENAI_API_KEY'),
                base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
                default_headers={"x-foo": "true"},
            )
            base64_image = global_var.store_memory[username]["images"][filename][int(imgid)]
            # 构建消息内容
            content_parts = [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/{file_extension};base64,{base64_image}"
                    }
                }
            ]
            messages = [
                {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant."}],},
                {"role": "user", "content": content_parts}
            ]
            response = await asyncio.wait_for(
                to_thread(  # 将同步调用转为异步任务
                    client.chat.completions.create,
                    # model='qwen-vl-max-latest',
                    model='gpt-4o',
                    messages=messages,
                    # temperature=global_var.config["temperature"],
                    # top_p=global_var.config["top_p"],
                    # frequency_penalty=global_var.config["frequency_penalty"],
                    # presence_penalty=global_var.config["presence_penalty"],
                    # max_tokens=global_var.config["max_tokens"],
                    # n=global_var.config["n"],
                    stream=True,
                    timeout=time_out,  # 原生超时参数（可选）
                ),
                timeout=time_out  # 自定义超时时间（优先级更高）
            )
            print(f"获取图片描述响应创建用时: {time.time() - start_time}秒")
            start_time = time.time()
            for chunk in response:
                # 检查 choices 是否为空
                if not chunk.choices:
                    continue  # 跳过空的 chunk
                new_content = chunk.choices[0].delta.content
                if new_content is None:
                    continue
                # response_data['model'] = 'qwen-vl-max-latest'
                response_data['model'] = 'gpt-4o'
                response_data['content'] = new_content
                yield json.dumps(response_data, ensure_ascii=False)
    except Exception as e:
        print(f"获取图片描述响应 API error: {e}")
        if time.time() - start_time > time_out and chat_content[username]["gpt4"] == "":
            print(f"获取图片描述响应 API调用超时, 超时时间: {time.time() - start_time}秒")
        new_content = "获取图片描述响应 API调用出错"
        # response_data['model'] = 'qwen-vl-max-latest'
        response_data['model'] = 'gpt-4o'
        response_data['content'] = new_content
        yield json.dumps(response_data, ensure_ascii=False)


@csrf_exempt
def card_updateImgText(request):
    data = json.loads(request.body)

    username = data["username"]
    filename = data["filename"]
    imgid = data["imgid"]
    content = data["content"]
    if 'imgtext' in data:
        imgtext = data["imgtext"]
    print(username + "请求更新文档图片:" + filename + "-" + imgid)

    merge_content = ""
    if content != "":
        merge_content = content

    start_time = time.time()
    content = parse_input.update_pdf_image_sum(user_name=username, doc_name=filename, seq=int(imgid),
                                               merge_content=merge_content, imgtext=imgtext)
    end_time = time.time()
    processing_time = end_time - start_time
    print(f"更新矢量存储此文档此 <图片> 解析文本时间: {processing_time:.2f}秒")

    response = {}
    response['content'] = content
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


def extract_cross_document_suggestion_preview(content):
    """
    专门提取文档交叉梳理建议卡片的预览内容
    重点突出A、B、C三个部分的核心信息

    Args:
        content: 卡片内容（以【文档全面交叉梳理建议卡片】开头）

    Returns:
        格式化的预览内容字符串，去掉markdown字符，突出重点
    """
    import re

    if not content:
        return ''

    # 移除开头的"【文档全面交叉梳理建议卡片】"
    content = re.sub(r'^【文档全面交叉梳理建议卡片】\s*\n*', '', content, flags=re.IGNORECASE).strip()

    preview_parts = []
    max_length_per_section = 100  # 每个部分最多100字

    def extract_meaningful_content(text, max_length):
        """提取有意义的内容，跳过编号、列表标记等，提取实质性内容"""
        if not text:
            return None

        # 去掉markdown字符，但保留换行以便分析结构
        text_with_newlines = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)

        # 去掉markdown标记
        clean_text = re.sub(r'[#*_`\[\]()]', '', text_with_newlines)
        # 将多个连续换行和空格合并为单个空格
        clean_text = re.sub(r'\s+', ' ', clean_text)
        clean_text = clean_text.strip()

        if not clean_text:
            return None

        # 🔥 跳过开头的编号、列表标记等无关内容（重复处理，确保彻底清除）
        # 匹配常见的开头模式：数字+点、字母+点、数字+空格等
        max_iterations = 5  # 最多清理5次，确保去除所有前缀标记
        for _ in range(max_iterations):
            original_text = clean_text
            clean_text = re.sub(r'^[\d一二三四五六七八九十]+[\.、。\s:：]+', '', clean_text)
            clean_text = re.sub(r'^[a-zA-Z][\.、。\s:：]+', '', clean_text)
            clean_text = re.sub(r'^[-\*\•]\s*', '', clean_text)
            clean_text = re.sub(r'^目标[：:]?\s*', '', clean_text, flags=re.IGNORECASE)
            clean_text = re.sub(r'^方向[一二三\d]+[：:]?\s*', '', clean_text, flags=re.IGNORECASE)
            clean_text = clean_text.strip()
            # 如果没有变化，说明已经清理干净
            if clean_text == original_text:
                break

        if not clean_text:
            return None

        # 🔥 如果清理后的文本太短（少于5个字符），说明可能是无效内容，返回None
        if len(clean_text) < 5:
            return None

        # 如果总长度在限制内，直接返回
        if len(clean_text) <= max_length:
            return clean_text

        # 🔥 优先提取前2-3句完整的话，确保有足够信息量
        sentence_endings = ['。', '！', '？', '.', '!', '?']
        sentences = []
        current_pos = 0

        # 找到所有句子结束符
        while current_pos < len(clean_text):
            next_end = -1
            for ending in sentence_endings:
                idx = clean_text.find(ending, current_pos)
                if idx >= 0 and (next_end == -1 or idx < next_end):
                    next_end = idx

            if next_end >= 0:
                sentence = clean_text[current_pos:next_end + 1].strip()
                if sentence:
                    sentences.append(sentence)
                current_pos = next_end + 1
            else:
                break

        # 如果找到了句子，优先返回前2-3句（不超过max_length）
        if sentences:
            result_text = ''
            for i, sentence in enumerate(sentences):
                if i >= 3:  # 最多3句
                    break
                test_text = result_text + sentence if result_text else sentence
                if len(test_text) <= max_length - 3:  # 留出"..."的空间
                    result_text = test_text
                else:
                    # 如果加上这句会超限，检查是否能加一句的片段
                    if i == 0 and len(sentence) > max_length - 3:
                        # 第一句就超限，返回第一句的截断版本
                        return extract_first_sentence_within_limit(sentence, max_length - 3)
                    break

            if result_text:
                return result_text + ('...' if len(clean_text) > len(result_text) else '')

        # 如果没有找到句子结束符，使用截断逻辑
        return extract_first_sentence_within_limit(clean_text, max_length)

    def extract_first_sentence_within_limit(text, max_length):
        """在限制长度内提取第一句完整的话"""
        sentence_endings = ['。', '！', '？', '.', '!', '?']

        # 找到第一个句子结束符
        first_sentence_end = -1
        for ending in sentence_endings:
            idx = text.find(ending)
            if idx >= 0 and (first_sentence_end == -1 or idx < first_sentence_end):
                first_sentence_end = idx

        if first_sentence_end >= 0:
            if first_sentence_end + 1 <= max_length:
                return text[:first_sentence_end + 1] + '...'
            else:
                # 第一句就超限，尝试在限制内找到合适的截断点
                truncate_pos = max_length - 3
                for i in range(truncate_pos, max(0, truncate_pos - 20), -1):
                    if text[i] in ['，', ',', '、', '；', ';']:
                        return text[:i + 1] + '...'
                return text[:truncate_pos] + '...'

        # 如果找不到句子结束符，在限制长度内截断
        if len(text) > max_length:
            truncate_pos = max_length - 3
            for i in range(truncate_pos, max(0, truncate_pos - 20), -1):
                if text[i] in [' ', '，', ',', '、', '；', ';']:
                    return text[:i + 1] + '...'
            return text[:truncate_pos] + '...'

        return text

    def find_best_content_segment(text_content, max_length):
        """找到最有意义的内容段落，跳过开头可能的标题、编号等"""
        if not text_content:
            return None

        # 按段落分割（双换行或段落标记）
        paragraphs = re.split(r'\n\s*\n|###', text_content)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        # 如果没有明显的段落分割，尝试按单换行分割
        if len(paragraphs) <= 1:
            paragraphs = [line.strip() for line in text_content.split('\n') if line.strip()]

        # 找到第一个有实质性内容的段落（长度大于20字）
        for para in paragraphs:
            # 清理段落
            clean_para = re.sub(r'[#*_`\[\]()]', '', para)
            clean_para = re.sub(r'\s+', ' ', clean_para).strip()

            # 跳过太短的段落（可能是标题或编号）
            if len(clean_para) < 20:
                continue

            # 尝试提取这个段落的有意义内容
            extracted = extract_meaningful_content(clean_para, max_length)
            if extracted and len(extracted) >= 20:  # 确保有足够内容
                return extracted

        # 如果没有找到合适的段落，使用原来的方法
        return extract_meaningful_content(text_content, max_length)

    # 提取A部分：权威置信度要求
    section_a_match = re.search(r'##\s*A\.\s*权威置信度要求\s*\n(.*?)(?=##\s*B\.|$)', content, re.DOTALL | re.IGNORECASE)
    if section_a_match:
        section_a_content = section_a_match.group(1).strip()
        extracted = find_best_content_segment(section_a_content, max_length_per_section)
        if extracted and len(extracted) >= 20:  # 确保有足够内容
            preview_parts.append(f"A. {extracted}")

    # 提取B部分：本子目标任务描述摘要（注意：B和C顺序已交换）
    section_b_match = re.search(r'##\s*B\.\s*本子目标任务描述摘要\s*\n(.*?)(?=##\s*C\.|$)', content,
                                re.DOTALL | re.IGNORECASE)
    if section_b_match:
        section_b_content = section_b_match.group(1).strip()
        extracted = find_best_content_segment(section_b_content, max_length_per_section)
        if extracted and len(extracted) >= 20:  # 确保有足够内容
            preview_parts.append(f"B. {extracted}")

    # 提取C部分：文档二次浓缩整理建议（注意：B和C顺序已交换）
    section_c_match = re.search(r'##\s*C\.\s*文档二次浓缩整理建议\s*\n(.*?)$', content, re.DOTALL | re.IGNORECASE)
    if section_c_match:
        section_c_content = section_c_match.group(1).strip()
        extracted = find_best_content_segment(section_c_content, max_length_per_section)
        if extracted and len(extracted) >= 20:  # 确保有足够内容
            preview_parts.append(f"C. {extracted}")

    # 如果没有提取到任何部分，使用简单截取（确保完整句子）
    if not preview_parts:
        # 去掉所有markdown字符
        clean_content = re.sub(r'\*\*([^*]+)\*\*', r'\1', content)
        clean_content = re.sub(r'[#*_`\[\]()]', '', clean_content)
        clean_content = re.sub(r'\s+', ' ', clean_content)
        clean_content = clean_content.strip()
        extracted = extract_meaningful_content(clean_content, 200)
        if extracted and len(extracted) > 10:
            preview_parts.append(extracted)

    # 组合预览内容，用换行分隔各部分
    preview = '\n'.join(preview_parts)
    preview = "【文档全面交叉梳理建议卡片】" + preview
    # if len(preview) > 300:
    #     preview = preview[:297] + '...'

    return preview


def extract_card_preview_content(key_words, content):
    """
    提取卡片预览内容：
    第一行：关键词（每个不超过8字，总长度不超过一行）
    第二三行：重要内容（加粗、标题等）

    Args:
        key_words: 关键词字符串
        content: 卡片内容（可能包含markdown格式）

    Returns:
        格式化的预览内容字符串（3行）
    """
    import re

    # 第一行：提取关键词（每个不超过8字/单词，总长度不超过一行约50字）
    first_line = ""
    if key_words:
        # 🔥 优先按逗号、顿号分割，空格不作为分隔符（保留短语中的空格）
        # 先按逗号和顿号分割
        keywords_list = re.split(r'[,，、]+', str(key_words))
        # 筛选出每个不超过10字/单词的关键词
        valid_keywords = []
        total_length = 0
        max_line_length = 17  # 一行最大长度

        def count_keyword_length(keyword):
            """
            计算关键词的长度：
            - 中文：按字符数（len）
            - 英文：按单词数（split by space）
            - 混合：分别计算中文字符数和英文单词数，取较大值
            """
            # 检测是否包含中文字符
            has_chinese = bool(re.search(r'[\u4e00-\u9fff]', keyword))
            # 检测是否包含英文单词
            has_english = bool(re.search(r'[a-zA-Z]', keyword))

            if has_chinese and has_english:
                # 混合：分别计算
                chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', keyword))
                english_words = len(re.findall(r'[a-zA-Z]+', keyword))
                return max(chinese_chars, english_words)
            elif has_chinese:
                # 纯中文：按字符数
                return len(keyword)
            else:
                # 纯英文：按单词数
                words = keyword.split()
                return len(words)

        for kw in keywords_list:
            kw_clean = kw.strip()
            # 去除首尾空格，但保留中间空格（如"Tree of Thoughts"）
            if kw_clean:
                kw_length = count_keyword_length(kw_clean)
                if kw_length <= 10:  # 单个关键词不超过10字/单词
                    # 检查添加后是否超过一行长度（考虑分隔符）
                    separator_len = 1 if valid_keywords else 0  # 分隔符长度（顿号"、"）
                    # 总长度按字符数计算（用于显示）
                    display_length = total_length + separator_len + kw_length
                    if display_length <= max_line_length:
                        valid_keywords.append(kw_clean)
                        total_length = display_length
                    else:
                        break  # 超过一行长度，停止添加

        if valid_keywords:
            first_line = ",".join(valid_keywords)  # 用顿号连接
    else:
        first_line = ""

    # 🔥 提取重要内容，记录每行的类型（标题、加粗、句子）
    important_items = []  # [(text, type), ...]

    if content:
        # 🔥 首先提取"回答："后的主体内容（去掉```代码块、thinking、checking等思考过程）
        answer_content_main = None

        # 匹配"回答："后的内容
        answer_pattern = r'回答[：:]\s*(.+?)(?=\n提问[：:]|\n回答[：:]|$)'
        answer_matches = re.findall(answer_pattern, content, re.DOTALL)

        if answer_matches:
            answer_content = answer_matches[0].strip()

            # 🔥 去除```代码块（包括```thinking、```checking、```等）
            # 移除所有```...```块
            answer_content = re.sub(r'```[^`]*```', '', answer_content, flags=re.DOTALL)
            # 移除```thinking\n...```格式的块
            answer_content = re.sub(r'```thinking\s*\n[^`]*```', '', answer_content,
                                    flags=re.DOTALL | re.IGNORECASE)
            # 移除```checking\n...```格式的块
            answer_content = re.sub(r'```checking\s*\n[^`]*```', '', answer_content,
                                    flags=re.DOTALL | re.IGNORECASE)
            # 移除其他类似格式
            answer_content = re.sub(r'```[a-zA-Z_]*\s*\n[^`]*```', '', answer_content, flags=re.DOTALL)

            # 清理多余的空行
            answer_content = re.sub(r'\n{3,}', '\n\n', answer_content)

            answer_content_main = answer_content.strip()

        # 🔥 优先从回答主体内容中提取，如果没有回答部分，则从整个content提取
        content_to_analyze = answer_content_main if answer_content_main else content

        if content_to_analyze:
            # 1. 提取标题（#、##、###等）
            heading_pattern = r'^(#{1,6})\s+(.+)$'
            headings = re.findall(heading_pattern, content_to_analyze, re.MULTILINE)
            if headings:
                # 优先提取最高层级的标题（最少#的）
                headings_sorted = sorted(headings, key=lambda x: len(x[0]))
                title_text = headings_sorted[0][1].strip()
                # 去除markdown格式符号（保留标题文本）
                title_text = re.sub(r'[*_`~]', '', title_text)
                if title_text:
                    important_items.append((title_text[:40], 'heading'))

            # 2. 提取加粗文本（**text**或__text__）
            bold_pattern = r'\*\*([^*]+)\*\*|__([^_]+)__'
            bold_texts = re.findall(bold_pattern, content_to_analyze)
            for match in bold_texts:
                bold_text = match[0] or match[1]  # 取非空组
                if bold_text:
                    # 清理文本，去除多余空格
                    bold_text = re.sub(r'\s+', ' ', bold_text.strip())
                    if len(bold_text) <= 50:
                        if not any(item[0] == bold_text[:40] for item in important_items):
                            important_items.append((bold_text[:40], 'bold'))
                            if len(important_items) >= 6:
                                break

            # 3. 提取关键句子
            if len(important_items) < 6 and answer_content_main:
                lines = answer_content_main.split('\n')
                for line in lines:
                    line_clean = line.strip()
                    if (line_clean and not line_clean.startswith('```') and
                            not line_clean.startswith('>') and
                            not re.match(r'^(提问|回答)[：:]', line_clean) and len(line_clean) > 10):
                        line_clean = re.sub(r'[*_`~#\[\]()]', '', line_clean)
                        line_clean = re.sub(r'\s+', ' ', line_clean.strip())
                        if line_clean and not any(item[0] == line_clean[:50] for item in important_items):
                            important_items.append((line_clean[:50], 'sentence'))
                            if len(important_items) >= 6:
                                break

            # 4. 最后回退
            if not important_items:
                lines = content.split('\n')
                for line in lines:
                    line_clean = line.strip()
                    if (line_clean and not line_clean.startswith('```') and
                            not line_clean.startswith('>') and
                            not re.match(r'^(提问|回答)[：:]', line_clean) and len(line_clean) > 5):
                        line_clean = re.sub(r'[*_`~#\[\]()]', '', line_clean)
                        line_clean = re.sub(r'\s+', ' ', line_clean.strip())
                        if line_clean:
                            important_items.append((line_clean[:50], 'sentence'))
                            if len(important_items) >= 6:
                                break

    # 🔥 组合预览内容，使用标记前缀区分类型
    preview_lines = []
    if first_line:
        preview_lines.append(f"🔑 {first_line}")  # 关键词标记

    # 🔥 检查content是否为文档摘要卡（单文档【文件摘要】或多增量【综合摘要】）
    content_stripped = content.strip() if content else ""
    is_file_summary = content_stripped.startswith("【文件摘要】")
    is_multi_summary = content_stripped.startswith("【综合摘要】")
    first_item_added = False  # 标记是否已经添加了第一个item

    for text, item_type in important_items[:6]:
        # 如果是第一个item且为文档摘要卡，在text前加上对应标记
        if (is_file_summary or is_multi_summary) and not first_item_added:
            text = f"{'【综合摘要】' if is_multi_summary else '【文件摘要】'}{text}"
            first_item_added = True

        if item_type == 'heading':
            preview_lines.append(f"📄 {text}")  # 标题标记
        elif item_type == 'bold':
            preview_lines.append(f"▸ {text}")  # 加粗标记（重点）
        elif item_type == 'sentence':
            preview_lines.append(f"• {text}")  # 句子标记

    # 组合成最终预览内容
    if preview_lines:
        preview_content = "\n".join(preview_lines) + "\n......"
    else:
        # 如果仍然没有提取到任何内容，提取内容的前两行非空内容
        if content:
            lines = content.split('\n')
            extracted = []
            for line in lines:
                line_clean = line.strip()
                if line_clean and len(line_clean) > 3:
                    line_clean = re.sub(r'[*_`~#\[\]()]', '', line_clean)
                    line_clean = re.sub(r'\s+', ' ', line_clean.strip())
                    if line_clean:
                        extracted.append(line_clean[:50])
                        if len(extracted) >= 2:
                            break
            if extracted:
                preview_content = "\n".join(extracted) + "\n......"
            else:
                preview_content = content[:100] + "\n......"
        else:
            preview_content = "\n......"

    return preview_content


@csrf_exempt
def card_getAllUserCards(request):
    data = json.loads(request.body)

    username = data["username"]
    print(f"[card_getAllUserCards] {username} 请求获取存储的所有卡片...")

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
        'interGrowthT2TA', 'interGrowthGL2GM', 'interGrowthTA2GL', 'question_comment',
        'confidence_score', 'rot_score',
        'four_color_type', 'dmt_level', 'is_neuron', 'is_evolved', 'selection_count', 'selected_docs', 'three_window_models',
        'is_analyzed_by_new_standard'  # 🔥 新增字段
    ]

    # 查询并只获取指定字段
    cards = Card.objects.filter(username=username).order_by('-datetime').values(*fields_to_include)
    cards_data = list(cards)  # 转换 QuerySet 为字典列表
    print(f"[card_getAllUserCards] 查询到 {len(cards_data)} 张卡片")

    # 处理content字段和为其他大字段设置默认值
    for card in cards_data:
        # 计算完整内容的字数（在截取之前）
        full_content = card.get('content', '')
        card['word_count'] = count_words_another(full_content)
        # 🔥 添加content_preview字段：包含content的前100个字符，用于前端提取提问内容
        card['content_preview'] = full_content[:100] if full_content else ''

        # 🔥 检测是否为文档交叉梳理建议卡片，使用专门的预览处理
        is_cross_doc_suggestion = full_content and full_content.strip().startswith('【文档全面交叉梳理建议卡片】')

        if is_cross_doc_suggestion:
            # 🔥 文档交叉梳理建议卡片：使用专门的预览提取函数，突出重点
            print("文档交叉梳理建议卡片：使用专门的预览提取函数，突出重点")
            card['content_preview'] = extract_cross_document_suggestion_preview(full_content)

        # # 截取content字段的前100个字符
        # if card['content']:
        #     card['content'] = card['content'][:100] + "\n......(加载中)"
        # 🔥 优化：提取关键词和重要内容作为预览
        if card['content']:
            key_words = card.get('keyWords', '')
            card['content'] = extract_card_preview_content(key_words, full_content)

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

    # 🔥 更新selection_count统计
    from collections import defaultdict
    selection_count_map = defaultdict(int)
    for card in cards_data:
        post_index_str = card.get('postIndex', '')
        if post_index_str:
            try:
                post_index_list = json.loads(post_index_str) if isinstance(post_index_str, str) else post_index_str
                if isinstance(post_index_list, list):
                    for selected_cid in post_index_list:
                        selected_cid_int = int(selected_cid) if isinstance(selected_cid, str) else selected_cid
                        selection_count_map[selected_cid_int] += 1
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    # 🔥 批量更新数据库中的selection_count
    for cid, count in selection_count_map.items():
        try:
            Card.objects.filter(cid=cid).update(selection_count=count)
        except Exception as e:
            print(f"更新卡片{cid}的selection_count失败: {e}")

    for card in cards_data:
        cid = card['cid']
        card['selection_count'] = selection_count_map.get(cid, 0)

    # 🔥 批量更新is_neuron（判断最后一个子场景）
    # 按username分组，从场景定义中获取最后一个子场景编号，而不是基于已存在的卡片
    from collections import defaultdict
    import pandas as pd
    import os
    from app_chat.scene_context_helper import get_scene_info_from_username

    # 按username分组卡片
    cards_by_username = defaultdict(list)  # key: username, value: [card, ...]
    for card in cards_data:
        username = card.get('username', '')
        if username:
            cards_by_username[username].append(card)

    # 对每个username，获取场景信息并确定最后一个子场景编号
    neuron_cids = set()
    all_cids = {card['cid'] for card in cards_data}  # 所有卡片的cid，用于后续标记非神经元卡

    for username, user_cards in cards_by_username.items():
        try:
            # 从username获取scene_name
            scene_name, _, _, _ = get_scene_info_from_username(username)
            if not scene_name:
                print(f"[批量更新is_neuron] 无法获取username={username}的场景信息，跳过")
                continue

            # 读取场景的prompt.xlsx，获取所有子场景列表
            scene_dir_path = f'./received_dir/scene_excel/{scene_name}'
            prompt_excel_path = os.path.join(scene_dir_path, 'prompt.xlsx')

            if not os.path.exists(prompt_excel_path):
                print(f"[批量更新is_neuron] 场景{scene_name}的prompt.xlsx不存在，跳过")
                continue

            # 从LUI1表格读取子场景列表（与card_upload中的逻辑一致）
            excel_data = pd.read_excel(prompt_excel_path, sheet_name='LUI1')
            sub_scene_col = 1
            if excel_data.shape[1] <= sub_scene_col:
                print(f"[批量更新is_neuron] 场景{scene_name}的prompt.xlsx列数不足，跳过")
                continue

            first_subscene_col_name = excel_data.columns[sub_scene_col]
            subscene_name_list = excel_data.iloc[:, sub_scene_col].dropna().tolist()
            subscene_name_list_order = [first_subscene_col_name] + subscene_name_list

            # 最后一个子场景的编号（从1开始，所以是列表长度）
            last_subscene_num = len(subscene_name_list_order)
            print(f"[批量更新is_neuron] username={username}, scene_name={scene_name}, 最后一个子场景编号={last_subscene_num}")

            # 遍历该username的所有卡片，标记神经元卡
            for card in user_cards:
                content_title = card.get('contentTitle', '')
                if not content_title:
                    continue

                # 提取子场景编号
                subscene_match = re.search(r'^S(\d+)[:：]', content_title)
                if subscene_match:
                    subscene_num = int(subscene_match.group(1))
                    # 只有属于最后一个子场景的卡片才标记为神经元卡
                    if subscene_num == last_subscene_num:
                        neuron_cids.add(card['cid'])
                        card['is_neuron'] = True
                    else:
                        card['is_neuron'] = False

        except Exception as e:
            print(f"[批量更新is_neuron] 处理username={username}时出错: {e}")
            import traceback
            traceback.print_exc()
            continue

    # 🔥 批量更新数据库中的is_neuron
    try:
        # 标记神经元卡
        if neuron_cids:
            Card.objects.filter(cid__in=neuron_cids).update(is_neuron=True)

        # 将其他卡片标记为非神经元卡
        non_neuron_cids = all_cids - neuron_cids
        if non_neuron_cids:
            Card.objects.filter(cid__in=non_neuron_cids).update(is_neuron=False)

        print(f"[批量更新is_neuron] 完成：{len(neuron_cids)}张神经元卡，{len(non_neuron_cids)}张非神经元卡")
    except Exception as e:
        print(f"[批量更新is_neuron] 更新数据库失败: {e}")

    # 🔥 后台异步处理旧卡片的四色DMT化（使用新标准，不阻塞前端显示）
    cards_needing_analysis = []
    total_cards_count = len(cards_data)
    for card in cards_data:
        is_analyzed_by_new_standard = card.get('is_analyzed_by_new_standard', False)
        # 🔥 如果未按新标准分析过，需要后台处理
        if not is_analyzed_by_new_standard:
            cards_needing_analysis.append({
                'cid': card['cid']
                # 不需要传递content，后台处理函数会从数据库重新获取完整内容
            })

    # 在后台线程中异步处理
    if cards_needing_analysis:
        print(
            f"[card_getAllUserCards] 总共有 {total_cards_count} 张卡片，发现 {len(cards_needing_analysis)} 张卡片需要后台处理四色DMT属性（使用新标准）")
        import threading
        thread = threading.Thread(
            target=_background_update_cards_four_color_dmt,
            args=(username, cards_needing_analysis),
            daemon=True
        )
        thread.start()
    else:
        print(f"[card_getAllUserCards] 总共有 {total_cards_count} 张卡片，所有卡片已按新标准分析过，无需后台处理")

    # 🔥 获取笔记本的关键词四色DMT信息
    keyword_four_color_dmt = {}
    semantic_reorganize_meta = {}
    try:
        from zym.models import UserNotebook, scene
        from app_chat.semantic_keyword_service import semantic_reorganize_meta_for_api

        # 解析username格式
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

        # 如果没有book_name，尝试从卡片中推断或查找
        if not book_name:
            # 尝试从第一张卡片的信息推断
            if cards_data:
                # 可以通过查找UserNotebook来获取book_name
                try:
                    # 尝试查找第一个匹配的笔记本
                    notebooks = UserNotebook.objects.filter(username=realName)
                    if notebooks.exists():
                        # 如果有多个笔记本，可能需要更复杂的逻辑，这里先取第一个
                        notebook = notebooks.first()
                        book_name = notebook.bookName
                except:
                    pass

        if book_name:
            try:
                notebook_for_meta = UserNotebook.objects.get(username=realName, bookName=book_name)
                notebook = notebook_for_meta
                if notebook.keywordFourColorDMT:
                    keyword_four_color_dmt = json.loads(notebook.keywordFourColorDMT)
                    print(f"[card_getAllUserCards] 成功获取关键词四色DMT信息，共 {len(keyword_four_color_dmt)} 个关键词")
                semantic_reorganize_meta = semantic_reorganize_meta_for_api(notebook, full_username=username)
            except UserNotebook.DoesNotExist:
                print(f"[card_getAllUserCards] 笔记本 {realName}/{book_name} 不存在，无法获取关键词四色DMT信息")
            except Exception as e:
                print(f"[card_getAllUserCards] 获取关键词四色DMT信息失败: {e}")
        else:
            print(f"[card_getAllUserCards] 无法确定book_name，跳过获取关键词四色DMT信息")
    except Exception as e:
        print(f"[card_getAllUserCards] 获取关键词四色DMT信息时出错: {e}")

    # 🔥 如果关键词四色DMT信息为空或很少，启动后台分析任务（针对旧本子）
    if len(keyword_four_color_dmt) == 0 and cards_data:
        try:
            from app_chat.keyword_analyzer import analyze_and_update_keywords_for_notebook
            from app_chat.scene_context_helper import get_scene_info_from_username

            # 获取场景信息
            scene_name, _, _, _ = get_scene_info_from_username(username)

            print(f"[card_getAllUserCards] 检测到关键词四色DMT信息为空，启动后台分析任务（场景: {scene_name}）")
            # 在后台线程中执行，不阻塞主请求
            thread = threading.Thread(
                target=analyze_and_update_keywords_for_notebook,
                args=(username, scene_name),
                daemon=True
            )
            thread.start()
        except Exception as e:
            print(f"[card_getAllUserCards] 启动关键词后台分析任务失败: {e}")

    # 🔥 部落知识关键词（is_tribal 或 knowledge_type=trib）
    tribal_keywords = []
    try:
        for kw, attr in keyword_four_color_dmt.items():
            if not isinstance(attr, dict):
                continue
            if attr.get('is_tribal') or attr.get('knowledge_type') == 'trib':
                tribal_keywords.append(kw)
    except Exception:
        pass

    response = {}
    response['content'] = cards_data
    response['keyword_four_color_dmt'] = keyword_four_color_dmt  # 🔥 新增关键词四色DMT信息
    response['semantic_reorganize_meta'] = semantic_reorganize_meta
    response['tribal_keywords'] = tribal_keywords  # 🔥 部落知识关键词列表，用于节点图菱形显示
    response['msg'] = 'success'
    response['error_num'] = 0
    return JsonResponse(response)


def _background_update_cards_four_color_dmt(username, cards_needing_analysis):
    """
    后台异步处理旧卡片的四色DMT化（使用新标准）
    不阻塞主请求，在后台线程中执行
    """
    from app_chat.card_analyzer import analyze_card_with_new_standard

    print(f"[_background_update_cards_four_color_dmt] 开始后台处理 {len(cards_needing_analysis)} 张卡片（使用新标准）")

    # 🔥 获取所有卡片数据（用于判断被勾选次数和总卡片数）
    all_cards = Card.objects.filter(username=username).values(
        'cid', 'content', 'contentTitle', 'is_neuron', 'is_evolved', 'selection_count', 'postIndex',
        'four_color_type', 'dmt_level'
    )
    all_cards_data = list(all_cards)
    total_cards_count = len(all_cards_data)

    for card_info in cards_needing_analysis:
        try:
            cid = card_info['cid']

            # 从数据库获取完整卡片
            try:
                card = Card.objects.get(cid=cid, username=username)

                # 检查是否已经按新标准分析过
                if card.is_analyzed_by_new_standard:
                    print(f"[_background_update_cards_four_color_dmt] 卡片{cid}已按新标准分析过，跳过")
                    continue

                # 将卡片对象转换为字典格式（用于分析函数）
                card_data = {
                    'cid': card.cid,
                    'content': card.content or '',
                    'contentTitle': card.contentTitle or '',
                    'is_neuron': card.is_neuron,
                    'is_evolved': card.is_evolved,
                    'selection_count': card.selection_count,
                    'username': card.username
                }

            except Card.DoesNotExist:
                print(f"[_background_update_cards_four_color_dmt] 卡片{cid}不存在，跳过")
                continue

            # 🔥 使用新标准分析卡片
            four_color_type, dmt_level, is_analyzed_by_new_standard = analyze_card_with_new_standard(
                card_data,
                scene_name=None,  # 会在函数内部自动获取
                sub_scene_name=None,
                scene_summary="",
                notebook_description="",
                all_cards_data=all_cards_data,
                total_cards_count=total_cards_count
            )

            # 更新数据库
            update_dict = {
                'four_color_type': four_color_type,
                'dmt_level': dmt_level,
                'is_analyzed_by_new_standard': is_analyzed_by_new_standard
            }

            Card.objects.filter(cid=cid).update(**update_dict)
            print(f"[_background_update_cards_four_color_dmt] 卡片{cid}更新完成: {update_dict}")

        except Exception as e:
            print(f"[_background_update_cards_four_color_dmt] 处理卡片{card_info.get('cid')}时出错: {e}")
            import traceback
            traceback.print_exc()

    print(f"[_background_update_cards_four_color_dmt] 后台处理完成")


@csrf_exempt
def card_getFilteredCards(request):
    """获取筛分后的高价值卡片（DMT四色化卡片层）"""
    data = json.loads(request.body)
    username = data["username"]
    filter_type = data.get("filter_type", "all")  # "all" 或 "high_value"

    print(f"{username} 请求获取筛分后的卡片，筛分类型: {filter_type}")

    # 获取所有卡片（排除大字段，包含新增字段）
    fields_to_include = [
        'cid', 'datetime', 'username', 'model_id', 'status',
        'content', 'title', 'score', 'time_params', 'seed',
        'color', 'keyWords', 'contentTitle', 'scoreSFT',
        'colorSFT', 'type', 'preIndex', 'postIndex', 'writer',
        'interGrowthT2TA', 'interGrowthGL2GM', 'interGrowthTA2GL', 'question_comment',
        'confidence_score', 'rot_score',
        'four_color_type', 'dmt_level', 'is_neuron', 'is_evolved', 'selection_count', 'selected_docs', 'three_window_models',
        'is_analyzed_by_new_standard'
    ]

    # 🔥 先不排序，直接获取所有卡片（筛分后再排序）
    cards = Card.objects.filter(username=username).values(*fields_to_include)
    cards_data = list(cards)

    # 更新selection_count统计
    from collections import defaultdict
    selection_count_map = defaultdict(int)
    for card in cards_data:
        post_index_str = card.get('postIndex', '')
        if post_index_str:
            try:
                post_index_list = json.loads(post_index_str) if isinstance(post_index_str, str) else post_index_str
                if isinstance(post_index_list, list):
                    for selected_cid in post_index_list:
                        selected_cid_int = int(selected_cid) if isinstance(selected_cid, str) else selected_cid
                        selection_count_map[selected_cid_int] += 1
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    # 🔥 批量更新数据库中的selection_count
    for cid, count in selection_count_map.items():
        try:
            Card.objects.filter(cid=cid).update(selection_count=count)
        except Exception as e:
            print(f"更新卡片{cid}的selection_count失败: {e}")

    for card in cards_data:
        cid = card['cid']
        card['selection_count'] = selection_count_map.get(cid, 0)

    # 🔥 DMT保底措施：被勾选次数排前2的卡片至少给M
    if selection_count_map:
        # 找出被勾选次数最多的前2个卡片
        sorted_selection = sorted(selection_count_map.items(), key=lambda x: x[1], reverse=True)
        top2_cids = [cid for cid, count in sorted_selection[:2] if count > 0]
        if top2_cids:
            print(f"[card_getFilteredCards] 被勾选次数排前2的卡片: {top2_cids}")
            for card in cards_data:
                if card['cid'] in top2_cids:
                    current_dmt = card.get('dmt_level', '')
                    if not current_dmt or current_dmt == 'D':
                        card['dmt_level'] = 'M'
                        print(f"[card_getFilteredCards] 卡片{card['cid']}（被勾选次数排前2）保底设置为M")
                        # 同时更新数据库
                        try:
                            Card.objects.filter(cid=card['cid']).update(dmt_level='M')
                        except Exception as e:
                            print(f"[card_getFilteredCards] 更新卡片{card['cid']}的DMT失败: {e}")

    # 🔥 批量更新is_neuron（判断最后一个子场景）
    # 按username分组，从场景定义中获取最后一个子场景编号，而不是基于已存在的卡片
    import pandas as pd
    import os
    from app_chat.scene_context_helper import get_scene_info_from_username

    # 按username分组卡片
    cards_by_username = defaultdict(list)  # key: username, value: [card, ...]
    for card in cards_data:
        username = card.get('username', '')
        if username:
            cards_by_username[username].append(card)

    # 对每个username，获取场景信息并确定最后一个子场景编号
    neuron_cids = set()
    all_cids = {card['cid'] for card in cards_data}  # 所有卡片的cid，用于后续标记非神经元卡

    for username, user_cards in cards_by_username.items():
        try:
            # 从username获取scene_name
            scene_name, _, _, _ = get_scene_info_from_username(username)
            if not scene_name:
                print(f"[card_getFilteredCards 批量更新is_neuron] 无法获取username={username}的场景信息，跳过")
                continue

            # 读取场景的prompt.xlsx，获取所有子场景列表
            scene_dir_path = f'./received_dir/scene_excel/{scene_name}'
            prompt_excel_path = os.path.join(scene_dir_path, 'prompt.xlsx')

            if not os.path.exists(prompt_excel_path):
                print(f"[card_getFilteredCards 批量更新is_neuron] 场景{scene_name}的prompt.xlsx不存在，跳过")
                continue

            # 从LUI1表格读取子场景列表（与card_upload中的逻辑一致）
            excel_data = pd.read_excel(prompt_excel_path, sheet_name='LUI1')
            sub_scene_col = 1
            if excel_data.shape[1] <= sub_scene_col:
                print(f"[card_getFilteredCards 批量更新is_neuron] 场景{scene_name}的prompt.xlsx列数不足，跳过")
                continue

            first_subscene_col_name = excel_data.columns[sub_scene_col]
            subscene_name_list = excel_data.iloc[:, sub_scene_col].dropna().tolist()
            subscene_name_list_order = [first_subscene_col_name] + subscene_name_list

            # 最后一个子场景的编号（从1开始，所以是列表长度）
            last_subscene_num = len(subscene_name_list_order)
            print(
                f"[card_getFilteredCards 批量更新is_neuron] username={username}, scene_name={scene_name}, 最后一个子场景编号={last_subscene_num}")

            # 遍历该username的所有卡片，标记神经元卡
            for card in user_cards:
                content_title = card.get('contentTitle', '')
                if not content_title:
                    continue

                # 提取子场景编号
                subscene_match = re.search(r'^S(\d+)[:：]', content_title)
                if subscene_match:
                    subscene_num = int(subscene_match.group(1))
                    # 只有属于最后一个子场景的卡片才标记为神经元卡
                    if subscene_num == last_subscene_num:
                        neuron_cids.add(card['cid'])
                        card['is_neuron'] = True
                    else:
                        card['is_neuron'] = False

        except Exception as e:
            print(f"[card_getFilteredCards 批量更新is_neuron] 处理username={username}时出错: {e}")
            import traceback
            traceback.print_exc()
            continue

    # 🔥 批量更新数据库中的is_neuron
    try:
        # 标记神经元卡
        if neuron_cids:
            Card.objects.filter(cid__in=neuron_cids).update(is_neuron=True)

        # 将其他卡片标记为非神经元卡
        non_neuron_cids = all_cids - neuron_cids
        if non_neuron_cids:
            Card.objects.filter(cid__in=non_neuron_cids).update(is_neuron=False)

        print(f"[card_getFilteredCards 批量更新is_neuron] 完成：{len(neuron_cids)}张神经元卡，{len(non_neuron_cids)}张非神经元卡")
    except Exception as e:
        print(f"[card_getFilteredCards 批量更新is_neuron] 更新数据库失败: {e}")

    # 🔥 先筛分，确定固定的高价值卡片集合（不依赖datetime排序）
    # 注意：筛分需要使用完整的content字段来提取问题，所以要在截断之前进行
    from app_chat.card_filter import get_filtered_cards
    high_value_cards, _ = get_filtered_cards(cards_data)

    # 🔥 处理content字段（筛分后再截断，节省传输数据）- 优化：提取关键词和重要内容
    for card in cards_data:
        full_content = card.get('content', '')
        card['word_count'] = count_words_another(full_content)
        # 🔥 添加content_preview字段：包含content的前100个字符，用于前端提取提问内容
        card['content_preview'] = full_content[:100] if full_content else ''

        # 🔥 检测是否为目录卡片，提取完整的目录部分
        is_directory_card = card.get('title') == '本子输出目录卡'
        if is_directory_card and full_content:
            # 提取目录部分（第一个"# "之前的内容，注意现在用# xxx分隔，而不是## xxx）
            lines = full_content.split('\n')
            directory_end_idx = len(lines)
            for i, line in enumerate(lines):
                if line.strip().startswith('# ') and i > 0:  # 不是第一行，且是章节标题（# xxx）
                    directory_end_idx = i
                    break
            directory_content = '\n'.join(lines[:directory_end_idx]).strip()
            if directory_content:
                card['content_preview'] = directory_content
            else:
                # 如果没有找到"# "，使用前500字（目录通常不会太长）
                card['content_preview'] = full_content[:500] if len(full_content) > 500 else full_content

        # 🔥 检测是否为文档交叉梳理建议卡片，使用专门的预览处理
        is_cross_doc_suggestion = full_content and full_content.strip().startswith('【文档全面交叉梳理建议卡片】')

        if is_cross_doc_suggestion:
            # 🔥 文档交叉梳理建议卡片：使用专门的预览提取函数，突出重点
            print("文档交叉梳理建议卡片：使用专门的预览提取函数，突出重点")
            card['content_preview'] = extract_cross_document_suggestion_preview(full_content)
            print(card['content_preview'])

        # 🔥 优化：提取关键词和重要内容作为预览
        if card['content']:
            # card['content'] = card['content'][:100] + "\n......(加载中)"
            key_words = card.get('keyWords', '')
            card['content'] = extract_card_preview_content(key_words, full_content)
        card['history'] = None
        card['reason'] = ""
        card['reasonSFT'] = ""
        card['subareaAndHLAndSugTA2GL'] = ""
        card['lastContent'] = ""

    # 标注哪些卡片已有附图（用于前端列表初次加载即显示有图图标）
    try:
        from app_chat.views_card_image import get_cids_with_card_image
        cids_with_image = get_cids_with_card_image(username)
        for card in cards_data:
            card['has_card_image'] = card['cid'] in cids_with_image
    except Exception as e:
        print(f"[card_getFilteredCards] 获取卡片附图状态失败: {e}")
        for card in cards_data:
            card['has_card_image'] = False

    high_value_cids = {card['cid'] for card in high_value_cards}

    # # 🔥 分别对高价值卡片和其他卡片按datetime排序，然后合并
    # other_cards = [card for card in cards_data if card['cid'] not in high_value_cids]
    #
    # # 高价值卡片内部按datetime排序（最新的在前）
    # high_value_cards_ordered = sorted(
    #     high_value_cards,
    #     key=lambda x: x.get('datetime', ''),
    #     reverse=True
    # )
    #
    # # 其他卡片按datetime排序（最新的在前）
    # other_cards_ordered = sorted(
    #     other_cards,
    #     key=lambda x: x.get('datetime', ''),
    #     reverse=True
    # )
    #
    # # 合并：高价值卡片在前，其他卡片在后
    # all_cards_ordered = high_value_cards_ordered + other_cards_ordered

    # 🔥 获取本子的keywordFourColorDMT数据，用于判断卡片是否包含有分析过的关键词
    keyword_dmt_data = {}
    try:
        from zym.models import UserNotebook
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
            realName) + 1 else None

        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                if notebook.keywordFourColorDMT:
                    keyword_dmt_data = json.loads(notebook.keywordFourColorDMT)
            except UserNotebook.DoesNotExist:
                pass
            except Exception as e:
                print(f"[card_getFilteredCards] 加载keywordFourColorDMT数据失败: {e}")
    except Exception as e:
        print(f"[card_getFilteredCards] 获取keywordFourColorDMT数据异常: {e}")

    # 🔥 判断卡片是否包含有分析过四色/DMT的关键词
    cards_with_dmt_keywords = []
    cards_without_dmt_keywords = []

    for card in cards_data:
        has_dmt_keyword = False
        key_words = card.get('keyWords', '')
        if key_words:
            keywords_list = [k.strip() for k in re.split(r'[,，]', key_words) if k.strip()]
            # 检查是否至少有一个关键词有四色/DMT数据
            for keyword in keywords_list:
                if keyword in keyword_dmt_data:
                    keyword_data = keyword_dmt_data[keyword]
                    if keyword_data.get('four_color_type') or keyword_data.get('dmt_level'):
                        has_dmt_keyword = True
                        break

        if has_dmt_keyword:
            cards_with_dmt_keywords.append(card)
        else:
            cards_without_dmt_keywords.append(card)

    # 🔥 分别对有四色/DMT属性的卡片和其他卡片按datetime排序，然后合并
    # 有四色/DMT属性的卡片内部按datetime排序（最新的在前）
    cards_with_dmt_ordered = sorted(
        cards_with_dmt_keywords,
        key=lambda x: x.get('datetime', ''),
        reverse=True
    )

    # 其他卡片按datetime排序（最新的在前）
    cards_without_dmt_ordered = sorted(
        cards_without_dmt_keywords,
        key=lambda x: x.get('datetime', ''),
        reverse=True
    )

    # 🔥 合并：有四色/DMT属性的卡片在前，其他卡片在后
    all_cards_ordered = cards_with_dmt_ordered + cards_without_dmt_ordered

    # 🔥 保持向后兼容：high_value_cards_ordered 和 other_cards_ordered
    high_value_cards_ordered = sorted(
        high_value_cards,
        key=lambda x: x.get('datetime', ''),
        reverse=True
    )
    other_cards = [card for card in cards_data if card['cid'] not in high_value_cids]
    other_cards_ordered = sorted(
        other_cards,
        key=lambda x: x.get('datetime', ''),
        reverse=True
    )

    # 🔥 后台异步处理旧卡片的四色DMT化（使用新标准，不阻塞前端显示）
    # 根据筛分类型选择要处理的卡片列表
    cards_to_check = high_value_cards_ordered if filter_type == "high_value" else all_cards_ordered
    cards_needing_analysis = []
    for card in cards_to_check:
        # 🔥 处理 NULL 值的情况（旧数据可能没有这个字段）
        is_analyzed_by_new_standard = card.get('is_analyzed_by_new_standard')
        if is_analyzed_by_new_standard is None or is_analyzed_by_new_standard is False:
            # 未按新标准分析过，需要后台处理
            cards_needing_analysis.append({
                'cid': card['cid']
                # 不需要传递content，后台处理函数会从数据库重新获取完整内容
            })

    # 在后台线程中异步处理
    if cards_needing_analysis:
        print(f"[card_getFilteredCards] 发现 {len(cards_needing_analysis)} 张卡片需要后台处理四色DMT属性")
        thread = threading.Thread(
            target=_background_update_cards_four_color_dmt,
            args=(username, cards_needing_analysis),
            daemon=True
        )
        thread.start()

    # 🔥 获取笔记本的关键词四色DMT信息
    keyword_four_color_dmt = {}
    semantic_reorganize_meta = {}
    notebook = None
    try:
        from zym.models import UserNotebook, scene
        from app_chat.semantic_keyword_service import semantic_reorganize_meta_for_api

        # 解析username格式
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

        # 如果没有book_name，尝试从卡片中推断或查找
        if not book_name:
            # 尝试查找第一个匹配的笔记本
            try:
                notebooks = UserNotebook.objects.filter(username=realName)
                if notebooks.exists():
                    notebook = notebooks.first()
                    book_name = notebook.bookName
            except:
                pass

        notebook_description = None  # 🔥 本子描述（中文）
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                if notebook.keywordFourColorDMT:
                    keyword_four_color_dmt = json.loads(notebook.keywordFourColorDMT)
                    print(f"[card_getFilteredCards] 成功获取关键词四色DMT信息，共 {len(keyword_four_color_dmt)} 个关键词")
                # 🔥 获取本子描述（中文）
                notebook_description = notebook.bookdescription if hasattr(notebook, 'bookdescription') else None
                semantic_reorganize_meta = semantic_reorganize_meta_for_api(notebook, full_username=username)
            except UserNotebook.DoesNotExist:
                print(f"[card_getFilteredCards] 笔记本 {realName}/{book_name} 不存在，无法获取关键词四色DMT信息")
            except Exception as e:
                print(f"[card_getFilteredCards] 获取关键词四色DMT信息失败: {e}")
        else:
            print(f"[card_getFilteredCards] 无法确定book_name，跳过获取关键词四色DMT信息")
    except Exception as e:
        print(f"[card_getFilteredCards] 获取关键词四色DMT信息时出错: {e}")

    # 🔥 如果关键词四色DMT信息为空或很少，启动后台分析任务（针对旧本子）
    if len(keyword_four_color_dmt) == 0 and cards_data:
        try:
            from app_chat.keyword_analyzer import analyze_and_update_keywords_for_notebook
            from app_chat.scene_context_helper import get_scene_info_from_username

            # 获取场景信息
            scene_name, _, _, _ = get_scene_info_from_username(username)

            print(f"[card_getFilteredCards] 检测到关键词四色DMT信息为空，启动后台分析任务（场景: {scene_name}）")
            # 在后台线程中执行，不阻塞主请求
            thread = threading.Thread(
                target=analyze_and_update_keywords_for_notebook,
                args=(username, scene_name),
                daemon=True
            )
            thread.start()
        except Exception as e:
            print(f"[card_getFilteredCards] 启动关键词后台分析任务失败: {e}")

    # 🔥 获取问题链排序状态和排序后的CID顺序
    question_chain_sorted = False
    question_chain_sorted_order = []
    question_chain_categories = {}
    try:
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None
        if book_name:
            notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
            question_chain_sorted = notebook.questionChainSorted if hasattr(notebook, 'questionChainSorted') else False
            if question_chain_sorted and hasattr(notebook, 'questionChainSortedOrder') and notebook.questionChainSortedOrder:
                try:
                    question_chain_sorted_order = json.loads(notebook.questionChainSortedOrder)
                except:
                    question_chain_sorted_order = []
            # 🔥 检查分类信息（不管是否排序过）
            if hasattr(notebook, 'questionChainCategories') and notebook.questionChainCategories:
                try:
                    question_chain_categories = json.loads(notebook.questionChainCategories)
                except:
                    question_chain_categories = {}
            else:
                question_chain_categories = {}

            # 🔥 如果没有分类信息，后台异步补全（不阻塞前端）
            if not question_chain_categories:
                print(f"[card_getFilteredCards] 发现没有questionChainCategories，后台异步补全")

                def _background_complete_question_categories():
                    try:
                        # 收集所有问答卡的问题
                        from app_chat.models import Card
                        import re
                        from app_chat.scene_context_helper import get_scene_info_from_username

                        # 获取场景名
                        scene_name, _, _, _ = get_scene_info_from_username(username)

                        qa_cards = Card.objects.filter(username=username, status=0).order_by('datetime')
                        questions = []
                        for qa_card in qa_cards:
                            q_question = ""
                            if qa_card.history:
                                try:
                                    h = json.loads(qa_card.history) if isinstance(qa_card.history,
                                                                                  str) else qa_card.history
                                    h_data = h.get('data') if isinstance(h, dict) else h
                                    if isinstance(h_data, list) and len(h_data) > 0:
                                        first_msg = h_data[0]
                                        if isinstance(first_msg, dict):
                                            q_question = first_msg.get('content', '')
                                except:
                                    pass

                            if not q_question and qa_card.content:
                                match = re.search(r'提问[：:]\s*([^\n\r]+)', qa_card.content)
                                if match:
                                    q_question = match.group(1).strip()

                            if q_question:
                                sub_scene = ""
                                if qa_card.contentTitle:
                                    match = re.search(r'^(S\d+)', qa_card.contentTitle)
                                    if match:
                                        sub_scene = match.group(1)

                                questions.append({
                                    'cid': str(qa_card.cid),
                                    'question': q_question,
                                    'author': qa_card.writer or qa_card.username or '',
                                    'sub_scene': sub_scene,
                                    'datetime': str(qa_card.datetime) if qa_card.datetime else ''
                                })

                        if questions:
                            # 调用排序和分类API（内部调用）
                            from app_chat.views_smart_sort_questions import smart_sort_questions
                            from django.test import RequestFactory
                            factory = RequestFactory()
                            request_data = {
                                'username': username,
                                'scene_name': scene_name,
                                'questions': questions
                            }
                            req = factory.post('/api/smart_sort_questions', data=json.dumps(request_data),
                                               content_type='application/json')
                            response = smart_sort_questions(req)
                            if response.status_code == 200:
                                print(f"[card_getFilteredCards] 后台补全问题链分类成功")
                            else:
                                print(f"[card_getFilteredCards] 后台补全问题链分类失败: {response.status_code}")
                    except Exception as e:
                        print(f"[card_getFilteredCards] 后台补全问题链分类出错: {e}")
                        import traceback
                        traceback.print_exc()

                thread = threading.Thread(
                    target=_background_complete_question_categories,
                    daemon=True
                )
                thread.start()
    except Exception as e:
        print(f"[card_getFilteredCards] 获取questionChainSorted状态失败: {e}")
        question_chain_sorted = False
        question_chain_sorted_order = []
        question_chain_categories = {}

    # 🔥 部落知识关键词（is_tribal为True的）
    tribal_keywords_filtered = []
    try:
        for kw, attr in keyword_four_color_dmt.items():
            if isinstance(attr, dict) and attr.get('is_tribal'):
                tribal_keywords_filtered.append(kw)
    except Exception:
        pass

    # 根据筛分类型返回
    if filter_type == "high_value":
        # 只返回高价值卡片
        response = {
            'content': high_value_cards_ordered,
            'msg': 'success',
            'error_num': 0,
            'high_value_cids': list(high_value_cids),  # 🔥 明确返回高价值卡片ID列表
            'keyword_four_color_dmt': keyword_four_color_dmt,  # 🔥 新增关键词四色DMT信息
            'tribal_keywords': tribal_keywords_filtered,
            'notebook_description': notebook_description,  # 🔥 新增本子描述（中文）
            'question_chain_sorted': question_chain_sorted,  # 🔥 新增问题链排序状态
            'question_chain_sorted_order': question_chain_sorted_order,  # 🔥 新增问题链排序后的CID顺序
            'question_chain_categories': question_chain_categories,  # 🔥 新增问题链分类信息
            'keyword_fusion_relations': json.loads(notebook.keywordFusionRelations) if notebook and notebook.keywordFusionRelations else {},
            'semantic_reorganize_meta': semantic_reorganize_meta,
        }
    else:
        # 返回所有卡片（高价值卡片在前）
        response = {
            'content': all_cards_ordered,
            'msg': 'success',
            'error_num': 0,
            'high_value_cids': list(high_value_cids),  # 🔥 明确返回高价值卡片ID列表
            'keyword_four_color_dmt': keyword_four_color_dmt,  # 🔥 新增关键词四色DMT信息
            'tribal_keywords': tribal_keywords_filtered,
            'notebook_description': notebook_description,  # 🔥 新增本子描述（中文）
            'question_chain_sorted': question_chain_sorted,  # 🔥 新增问题链排序状态
            'question_chain_sorted_order': question_chain_sorted_order,  # 🔥 新增问题链排序后的CID顺序
            'question_chain_categories': question_chain_categories,  # 🔥 新增问题链分类信息
            'keyword_fusion_relations': json.loads(notebook.keywordFusionRelations) if notebook and notebook.keywordFusionRelations else {},  # 🔥 新增关键词融合关系
            'semantic_reorganize_meta': semantic_reorganize_meta,
        }

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
        'selected_docs': card.selected_docs,  # 🔥 返回勾选的文档列表
        'three_window_models': card.three_window_models,  # 🔥 返回三窗口模型配置
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
    isForSmallModel = data.get("isForSmallModel", False)  # 新增参数

    CardContentList = []
    finalContent = ''
    CardIndexList = data['choosedCardIdList'].split(',')

    # 如果是为小模型生成精简内容，只做基础获取和精简
    if isForSmallModel:
        for i, id_str in enumerate(CardIndexList):
            id = int(id_str)
            card = Card.objects.get(cid=id)
            cardContent = card.content

            # 精简到400字
            cardContent = limit_content_to_400_chars(cardContent)
            finalContent += cardContent + "\n\n"

        # 直接返回，不做后面的处理
        response = {}
        response['content'] = finalContent
        response['msg'] = 'success'
        response['error_num'] = 0
        return JsonResponse(response)

    # 原有完整流程
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
        # 解释精要卡过长：问答只注入总览/学情/枢纽 + 各页整体（不含逐题）
        try:
            from app_chat.homework_grading.excerpt_card_render import (
                is_excerpt_grading_card,
                trim_excerpt_card_for_qa,
            )
            title = card.contentTitle or ''
            if is_excerpt_grading_card(cardContent, title):
                cardContent = trim_excerpt_card_for_qa(cardContent, title)
        except Exception as exc:
            print(f'[getCardsContentByIds] 解释精要截取跳过 cid={id}: {exc}', flush=True)
        content = '[重要素材文本' + str(i + 1) + ']:\n' + '标题：' + card.contentTitle + '\n内容：' + cardContent + '\n\n'
        CardContentList.append(content)

    # 设置字/单词数量限制
    WORD_LIMIT = 6000

    # 🔥 注释掉自动处理postIndex的逻辑，避免勾选一张卡片时自动加入其他卡片
    # 如果用户需要，可以通过其他方式显式传入
    # # 处理每个卡片的后置索引
    # for id_str in CardIndexList:
    #     id = int(id_str)
    #     card = Card.objects.get(cid=id)
    #
    #     # 检查是否有有效的postIndex
    #     if card.postIndex and card.postIndex != "":
    #         try:
    #             # 解析JSON字符串为Python列表
    #             post_index_list = json.loads(card.postIndex)
    #
    #             # 遍历后置索引卡片
    #             for post_id in post_index_list:
    #                 try:
    #                     # 检查是否已达到字/单词数量限制
    #                     current_total_words = get_total_words_count(CardContentList)
    #                     if current_total_words >= WORD_LIMIT:
    #                         print(f"已达到{WORD_LIMIT}字/单词限制，停止添加更多内容")
    #                         break  # 跳出当前后置索引卡片循环
    #
    #                     # 获取后置索引卡片
    #                     post_card = Card.objects.get(cid=int(post_id))
    #                     post_card_content = post_card.content
    #
    #                     # 处理后置索引卡片内容
    #                     index = post_card_content.find("回答：")
    #                     if index != -1:
    #                         post_card_content = post_card_content[index + len("回答："):]
    #
    #                     # 检查与现有内容的重复率
    #                     skip_card = False
    #                     for existing_content in CardContentList:
    #                         # 提取现有内容中的实际文本（去掉'[重要素材文本X]:'前缀和末尾的换行符）
    #                         if ']:\n' in existing_content:
    #                             existing_text = existing_content.split(']:\n', 1)[1].strip()
    #                         else:
    #                             existing_text = existing_content.strip()
    #
    #                         # 计算重复率
    #                         overlap_ratio = calculate_overlap_ratio(post_card_content, existing_text)
    #                         if overlap_ratio > 0.6:  # 重复率超过60%
    #                             skip_card = True
    #                             break
    #
    #                     # 如果不需要跳过，则添加到CardContentList
    #                     if not skip_card:
    #                         new_index = len(CardContentList) + 1
    #                         new_content = '[重要素材文本' + str(new_index) + ']:\n' + post_card_content + '\n\n'
    #                         new_content_word_count = count_words(new_content)
    #
    #                         # 检查添加新内容后是否会超过限制
    #                         if current_total_words + new_content_word_count <= WORD_LIMIT:
    #                             CardContentList.append(new_content)
    #                         else:
    #                             print(f"添加新内容将超过{WORD_LIMIT}字/单词限制，停止添加")
    #                             break  # 跳出当前后置索引卡片循环
    #
    #                 except Card.DoesNotExist:
    #                     # 如果后置索引卡片不存在，则跳过
    #                     continue
    #                 except Exception as e:
    #                     # 处理其他可能的异常
    #                     print(f"处理后置索引卡片时出错: {e}")
    #                     continue
    #             # 如果已达到字/单词数量限制，跳出外部循环
    #             if get_total_words_count(CardContentList) >= WORD_LIMIT:
    #                 break
    #         except json.JSONDecodeError:
    #             # 如果postIndex不是有效的JSON，则跳过
    #             print(f"卡片ID {id} 的postIndex不是有效的JSON: {card.postIndex}")
    #             continue
    #         except Exception as e:
    #             # 处理其他可能的异常
    #             print(f"处理卡片ID {id} 的postIndex时出错: {e}")
    #             continue

    for cardText in CardContentList:
        finalContent += cardText

    response = {}
    response['content'] = finalContent
    response['msg'] = 'success'
    response['error_num'] = 0

    return JsonResponse(response)


@csrf_exempt
def card_updateType(request):
    """更新卡片的四色类型和DMT层次"""
    # 支持FormData和JSON两种格式
    if request.content_type and 'application/json' in request.content_type:
        data = json.loads(request.body)
        username = data.get("username")
        cid = data.get("cid")
        four_color_type = data.get("four_color_type", "")
        dmt_level = data.get("dmt_level", "")
    else:
        username = request.POST.get("username")
        cid = request.POST.get("cid")
        four_color_type = request.POST.get("four_color_type", "")
        dmt_level = request.POST.get("dmt_level", "")

    try:
        card = Card.objects.get(cid=cid, username=username)
        card.four_color_type = four_color_type
        card.dmt_level = dmt_level
        card.save()

        return JsonResponse({
            'msg': 'success',
            'error_num': 0
        })
    except Card.DoesNotExist:
        return JsonResponse({
            'msg': '卡片不存在',
            'error_num': 1
        })
    except Exception as e:
        return JsonResponse({
            'msg': f'更新失败: {str(e)}',
            'error_num': 1
        })


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


def get_small_model_server_url(username):
    """
    根据username从全局变量获取小模型ID，返回对应的服务器URL
    3007 -> 127.0.0.1
    3001-3006 -> 127.0.0.1
    """
    from app_chat.global_state import GLOBAL_STATE
    model_id = GLOBAL_STATE.user_little_model_id.get(username, "3003")
    if str(model_id) == "3007":
        return _public_config.endpoint('NKCN_SERVICE_8000_URL', 'http://localhost:8000')
    else:
        return _public_config.endpoint('NKCN_SERVICE_8000_URL', 'http://localhost:8000')


def little_model_switch(username, model_id):
    try:
        # command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","model_id":"{model_id}"}}\' http://localhost:8000/model_switch/'
        # 更新全局变量
        from app_chat.global_state import GLOBAL_STATE
        GLOBAL_STATE.user_little_model_id[username] = str(model_id)
        server_url = get_small_model_server_url(username)
        command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","model_id":"{model_id}"}}\' {server_url}/model_switch/'
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
    global translation_requests

    if os.path.exists(new_pdf_path):
        # 🔥 检测旧文档：如果原文档是中文，翻译文档也是中文（中译中错误），则删除翻译文档并重新翻译
        try:
            from app_chat.baidu_trans_doc import detect_pdf_language
            original_lang = detect_pdf_language(full_file_path)
            translated_lang = detect_pdf_language(new_pdf_path)

            if original_lang == 'zh' and translated_lang == 'zh':
                # 原文档是中文，翻译文档也是中文（中译中错误），删除翻译文档
                print(f"检测到旧文档错误：原文档({original_lang})和翻译文档({translated_lang})都是中文，删除错误翻译并重新翻译")
                try:
                    os.remove(new_pdf_path)
                    print(f"已删除错误的翻译文档: {new_pdf_path}")
                    # 删除后重新翻译（英文）
                    translate(pdf_relative_path, full_file_path, new_pdf_path, request_key)
                    status = 'no'  # 标记为未完成，等待重新翻译
                except Exception as e:
                    print(f"删除翻译文档失败: {e}")
                    status = 'completed'  # 如果删除失败，仍返回已完成状态
            else:
                # 正常情况，翻译文档已存在且正确
                print(f"返回给前端查询结果: 已完成")
                status = 'completed'
        except Exception as e:
            print(f"检测翻译文档语言时出错: {e}，继续使用现有翻译文档")
            status = 'completed'

        # # 🔥 新增：检测翻译后的PDF是否也是扫描件
        # try:
        #     import sys
        #     import os as os_module
        #     sys.path.append(os_module.path.dirname(os_module.path.dirname(os_module.path.abspath(__file__))))
        #     from llm_langchain.pdf_ocr_utils import check_pdf_type_by_word, run_remote_ocr, md_to_pdf

        #     translated_pdf_type = check_pdf_type_by_word(new_pdf_path)

        #     if translated_pdf_type == 'scanned':
        #         print(f"[check_translation_status] 警告：翻译后的PDF也是扫描件！")

        #         # 🔥 修复：先从translation_requests中获取翻译请求上下文
        #         translation_request = translation_requests.get(request_key, {})

        #         # 获取原始文件路径和重试次数
        #         original_file = translation_request.get('original_file_path', full_file_path)  # 默认使用当前文件路径
        #         retry_count = translation_request.get('retry_count', 0)
        #         target_pdf = translation_request.get('target_pdf_path', new_pdf_path)

        #         # 最多重试1次，避免无限循环
        #         if retry_count < 1 and original_file and os_module.path.exists(original_file):
        #             print(f"[check_translation_status] 翻译文档确实是扫描件，准备OCR处理后重新翻译...")

        #             # 删除错误的翻译结果
        #             try:
        #                 os.remove(new_pdf_path)
        #                 print(f"[check_translation_status] 已删除扫描件翻译结果: {new_pdf_path}")
        #             except Exception as e:
        #                 print(f"[check_translation_status] 删除失败: {e}")

        #             # 准备OCR处理
        #             file_dir = os_module.path.dirname(original_file)
        #             file_base = os_module.path.splitext(os_module.path.basename(original_file))[0]
        #             ocr_dir = os_module.path.join(file_dir, f"{file_base}_ocr")
        #             md_path = os_module.path.join(ocr_dir, f"{file_base}_ocr.md")
        #             converted_pdf_path = os_module.path.join(ocr_dir, f"{file_base}_converted.pdf")

        #             # 检查是否已有转换后的PDF
        #             need_ocr = not os_module.path.exists(md_path)

        #             if need_ocr:
        #                 print(f"[check_translation_status] 开始OCR处理原始扫描件...")
        #                 # 执行OCR
        #                 ocr_success, md_path, _ = run_remote_ocr(original_file, ocr_dir)
        #                 if not ocr_success or not os_module.path.exists(md_path):
        #                     print(f"[check_translation_status] OCR处理失败，无法重新翻译")
        #                     if request_key in translation_requests:
        #                         translation_requests[request_key]['isFail'] = True
        #                     status = 'fail'
        #                     return JsonResponse({'status': status})

        #             if not os_module.path.exists(converted_pdf_path) and os_module.path.exists(md_path):
        #                 print(f"[check_translation_status] OCR成功，将markdown转换为PDF...")
        #                 # markdown转PDF
        #                 conversion_success = md_to_pdf(md_path, converted_pdf_path)

        #                 if not conversion_success or not os_module.path.exists(converted_pdf_path):
        #                     print(f"[check_translation_status] Markdown转PDF失败，无法重新翻译")
        #                     if request_key in translation_requests:
        #                         translation_requests[request_key]['isFail'] = True
        #                     status = 'fail'
        #                     return JsonResponse({'status': status})

        #             # 使用转换后的PDF重新翻译
        #             if os_module.path.exists(converted_pdf_path):
        #                 print(f"[check_translation_status] 使用转换后的PDF重新发起翻译...")
        #                 file_name = os_module.path.basename(original_file)

        #                 # 🔥 关键：更新翻译请求信息，包括增加retry_count
        #                 if request_key in translation_requests:
        #                     translation_requests[request_key]['converted_pdf_path'] = converted_pdf_path
        #                     translation_requests[request_key]['ocr_attempted'] = True
        #                     translation_requests[request_key]['retry_count'] = retry_count + 1  # 增加重试次数
        #                     print(f"[check_translation_status] 更新retry_count: {retry_count} -> {retry_count + 1}")
        #                 else:
        #                     # 如果translation_requests中没有记录，创建一个新的
        #                     translation_requests[request_key] = {
        #                         'original_file_path': original_file,
        #                         'target_pdf_path': target_pdf,
        #                         'converted_pdf_path': converted_pdf_path,
        #                         'ocr_attempted': True,
        #                         'retry_count': 1  # 第一次重试
        #                     }
        #                     print(f"[check_translation_status] 创建新的翻译请求记录，retry_count=1")

        #                 # 🔥 修复：使用转换后的PDF（converted_pdf_path）进行翻译，而不是原始扫描件
        #                 translate(file_name, converted_pdf_path, target_pdf, request_key)
        #                 print(f"[check_translation_status] 已使用OCR转换后的PDF进行翻译: {converted_pdf_path}")

        #                 # 标记为处理中，前端继续轮询
        #                 status = 'no'
        #                 print(f"[check_translation_status] 已重新提交翻译任务，前端继续轮询")
        #                 return JsonResponse({'status': status})
        #         else:
        #             # 达到最大重试次数，标记为失败
        #             if retry_count >= 1:
        #                 print(f"[check_translation_status] 已达到最大重试次数({retry_count})，放弃重试")
        #             if request_key in translation_requests:
        #                 translation_requests[request_key]['isFail'] = True
        #                 translation_requests.pop(request_key)  # 清理失败的请求
        #             status = 'fail'
        #             # 🔥 修复：失败后直接返回，不继续执行后续代码
        #             return JsonResponse({'status': status})
        #     else:
        #         # PDF类型正常，翻译成功
        #         print(f"[check_translation_status] 翻译后的PDF类型正常: {translated_pdf_type}")
        #         # 🔥 确保status为completed（可能被前面的代码修改）
        #         status = 'completed'

        # except Exception as e:
        #     print(f"[check_translation_status] 翻译后PDF检测/重新翻译失败: {e}")
        #     import traceback
        #     traceback.print_exc()
            # 检测失败不影响主流程，status保持为之前设置的值（completed）

        # 🔥 修复：只有在翻译真正完成时才清理translation_requests
        # 如果重新翻译，已经在上面return了，不会执行到这里
        if request_key in translation_requests and status == 'completed':
            # 翻译已完成，清理请求记录
            translation_requests.pop(request_key)
            print(f"[check_translation_status] 翻译完成，清理请求记录: {request_key}")
    else:
        if request_key in translation_requests:
            translation_request = translation_requests[request_key]
            if translation_request['isFail']:
                print(f"返回给前端查询结果: 失败")
                status = 'fail'
                # 找到匹配的字典并移除
                translation_requests.pop(request_key)
            else:
                print(f"返回给前端查询结果: 未完成")
                status = 'no'
        else:
            if userbook in global_var.unable_to_be_translated \
                    and pdf_relative_path in global_var.unable_to_be_translated[userbook]:
                print(f"文件 {full_file_path} 是图片，不进行翻译")
                print(f"返回给前端查询结果: 失败")
                status = 'unable'
            else:
                global_var.unable_to_be_translated.setdefault(userbook, list())
                if not full_file_path.endswith('.pdf'):
                    # 不是PDF文件（可能是图片），不进行翻译
                    global_var.unable_to_be_translated[userbook].append(pdf_relative_path)
                    print(f"文件 {full_file_path} 不是PDF文件，不进行翻译")
                    print(f"返回给前端查询结果: 失败")
                    status = 'unable'
                else:
                    print(f"返回给前端查询结果: 未完成")
                    status = 'no'
                    translate(pdf_relative_path, full_file_path, new_pdf_path, request_key)

                # docs = parse_input.get_split_by_user_docs(userbook, [pdf_relative_path])
                # if docs:
                #     # 如果doc[0](Document对象)的metadata中的"file_path"是图片，则不进行翻译
                #     if docs[0].metadata.get("file_path", "").endswith(('.pdf')):
                #         print(f"返回给前端查询结果: 未完成")
                #         status = 'no'
                #         translate(pdf_relative_path, full_file_path, new_pdf_path, request_key)
                #     else:
                #         global_var.unable_to_be_translated[userbook].append(pdf_relative_path)
                #         print(f"文件 {full_file_path} 是图片，不进行翻译")
                #         print(f"返回给前端查询结果: 失败")
                #         status = 'unable'

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
        # 🔥 新增：检查是否为扫描件，如果是则返回布局PDF
        try:
            from llm_langchain.pdf_ocr_utils import check_pdf_type_by_word, generate_layout_pdf
            from llm_langchain import global_var

            # 检查是否为扫描件（先从缓存获取）
            file_key = f"{userbook}/{pdf_relative_path}"
            pdf_type = global_var.get_pdf_type(file_key)

            # 如果缓存没有，则重新检测
            if pdf_type is None:
                print(f"[布局PDF] 缓存未命中，重新检测PDF类型: {full_file_path}")
                pdf_type = check_pdf_type_by_word(full_file_path)
                global_var.set_pdf_type(file_key, pdf_type)

            is_scanned = (pdf_type == 'scanned')
            print(f"[布局PDF] PDF类型: {pdf_type}, 是否扫描件: {is_scanned}")

            # 如果是扫描件，尝试返回布局PDF
            if is_scanned:
                file_base = os.path.splitext(os.path.basename(full_file_path))[0]
                file_dir = os.path.dirname(full_file_path)

                # OCR目录和布局PDF路径（统一放在OCR目录下）
                ocr_dir = os.path.join(file_dir, f"{file_base}_ocr")
                layout_pdf_path = os.path.join(ocr_dir, f"{file_base}_layouts.pdf")

                # 如果布局PDF不存在，尝试生成
                if not os.path.exists(layout_pdf_path):
                    print(f"[布局PDF] 布局PDF不存在，尝试生成: {layout_pdf_path}")

                    # 尝试查找OCR txt文件
                    txt_path = os.path.join(ocr_dir, f"{file_base}_raw.txt")

                    if os.path.exists(txt_path):
                        # 有OCR结果，可以生成布局PDF
                        print(f"[布局PDF] 找到OCR结果，开始生成布局PDF")
                        success, generated_path = generate_layout_pdf(full_file_path, txt_path, layout_pdf_path)

                        if success and os.path.exists(layout_pdf_path):
                            print(f"[布局PDF] 布局PDF生成成功: {layout_pdf_path}")
                        else:
                            print(f"[布局PDF] 布局PDF生成失败")
                            layout_pdf_path = None
                    else:
                        print(f"[布局PDF] 未找到OCR结果文件: {txt_path}，无法生成布局PDF")
                        layout_pdf_path = None

                # 如果布局PDF存在，返回布局PDF
                if layout_pdf_path and os.path.exists(layout_pdf_path):
                    print(f"[布局PDF] 返回布局PDF: {layout_pdf_path}")
                    response = StreamingHttpResponse(open(layout_pdf_path, 'rb'), content_type='application/pdf')
                    response['Access-Control-Allow-Origin'] = '*'
                    response['X-Frame-Options'] = 'ALLOWALL'
                    return response
                else:
                    print(f"[布局PDF] 布局PDF不可用，返回原始PDF")

        except Exception as e:
            print(f"[布局PDF] 处理布局PDF时出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时继续正常流程

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
                # 🔥 检测旧文档：如果原文档是中文，翻译文档也是中文（中译中错误），则删除翻译文档并重新翻译
                if os.path.exists(new_pdf_path):
                    try:
                        from app_chat.baidu_trans_doc import detect_pdf_language
                        original_lang = detect_pdf_language(full_file_path)
                        translated_lang = detect_pdf_language(new_pdf_path)

                        if original_lang == 'zh' and translated_lang == 'zh':
                            # 原文档是中文，翻译文档也是中文（中译中错误），删除翻译文档
                            print(
                                f"[pdf_stream_handler] 检测到旧文档错误：原文档({original_lang})和翻译文档({translated_lang})都是中文，删除错误翻译并重新翻译")
                            try:
                                os.remove(new_pdf_path)
                                print(f"[pdf_stream_handler] 已删除错误的翻译文档: {new_pdf_path}")
                                # 删除后重新翻译（英文），使用新的request_key
                                request_key = userbook + "_" + pdf_relative_path
                                translate(pdf_relative_path, full_file_path, new_pdf_path, request_key)
                                # 返回原文件，等待翻译完成
                                print("[pdf_stream_handler] 已启动重新翻译，暂时返回原文件")
                                response = StreamingHttpResponse(open(full_file_path, 'rb'),
                                                                 content_type='application/pdf')
                                response['Access-Control-Allow-Origin'] = '*'
                                response['X-Frame-Options'] = 'ALLOWALL'
                                return response
                            except Exception as e:
                                print(f"[pdf_stream_handler] 删除翻译文档失败: {e}，继续使用现有翻译文档")
                    except Exception as e:
                        print(f"[pdf_stream_handler] 检测翻译文档语言时出错: {e}，继续使用现有翻译文档")

                # 翻译文档存在且正确，返回翻译文档
                if os.path.exists(new_pdf_path):
                    response = StreamingHttpResponse(open(new_pdf_path, 'rb'), content_type='application/pdf')
                    print("文件已读取")
                    response['Access-Control-Allow-Origin'] = '*'
                    response['X-Frame-Options'] = 'ALLOWALL'
                    return response
                else:
                    # 翻译文档不存在，返回原文件
                    print("翻译文档不存在，返回原文件")
                    response = StreamingHttpResponse(open(full_file_path, 'rb'), content_type='application/pdf')
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
def serve_pdf(request):
    """
    处理PDF文件请求，并返回文件流
    """
    try:
        # 获取请求参数
        pdf_relative_path = request.GET.get('url')
        userbook = request.GET.get('userbook')
        scene = request.GET.get('sceneName', '')

        # 日志记录
        print(f"用户 {userbook} 请求PDF文件: {pdf_relative_path}")

        # 验证参数
        if not pdf_relative_path or not userbook:
            return JsonResponse({'error': '缺少必要参数'}, status=400)

        # 安全检查：防止路径遍历攻击
        if '..' in pdf_relative_path or pdf_relative_path.startswith('/'):
            return JsonResponse({'error': '非法的文件路径'}, status=403)

        # 拼接完整的原文件路径
        base_path = './received_dir/user_raw_file/'
        userbook_path = os.path.join(base_path, userbook)
        fs = FileSystemStorage(location=userbook_path)
        full_file_path = fs.path(pdf_relative_path)
        if scene != '' and (scene == '阅读_result' or ('_result' in scene and '中英文专业阅读' in scene)):
            full_file_path = os.path.join(os.path.dirname(full_file_path),
                                          os.path.basename(full_file_path).replace('.pdf', '_transFTWYGUHX.pdf'))
        print("实际路径-----------------------")
        print(full_file_path)

        # 检查文件是否存在
        if not os.path.exists(full_file_path):
            print(f"文件不存在: {full_file_path}")
            return JsonResponse({'error': '文件不存在'}, status=404)

        # 短期记忆块 .txt：若存在已保存的 Summary，合并后返回供回溯使用
        if full_file_path.lower().endswith('.txt'):
            block_id = os.path.splitext(os.path.basename(pdf_relative_path))[0]
            summary_dir = os.path.join(userbook_path, 'audio_block_summary')
            summary_path = os.path.join(summary_dir, f"{block_id}_Summary.txt")
            if os.path.isfile(summary_path):
                try:
                    with open(full_file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    with open(summary_path, 'r', encoding='utf-8') as f:
                        summary_text = f.read()

                    # 若块内已有 Summary 行则替换，否则在 [BLOCK_BODY] 后追加
                    lines = content.split('\n')
                    out_lines = []
                    in_body = False
                    summary_written = False
                    for line in lines:
                        if line.strip() == '[BLOCK_BODY]':
                            in_body = True
                            out_lines.append(line)
                            continue
                        if in_body and line.strip().startswith('Summary:'):
                            out_lines.append('Summary: ' + summary_text.replace('\n', ' ').strip())
                            summary_written = True
                            continue
                        out_lines.append(line)
                    if in_body and not summary_written:
                        out_lines.append('Summary: ' + summary_text.replace('\n', ' ').strip())
                    merged = '\n'.join(out_lines)

                    from django.http import HttpResponse
                    resp = HttpResponse(merged, content_type='text/plain; charset=utf-8')
                    resp['Access-Control-Allow-Origin'] = '*'
                    return resp
                except Exception as e:
                    print(f"[serve_pdf] 合并 audio_block_summary 时出错: {e}")
                    import traceback
                    traceback.print_exc()

        if not full_file_path.endswith('_transFTWYGUHX.pdf'):  # 翻译后的PDF不处理布局PDF
            # 🔥 新增：检查是否为扫描件，如果是则返回布局PDF
            try:
                from llm_langchain.pdf_ocr_utils import check_pdf_type_by_word, generate_layout_pdf
                from llm_langchain import global_var

                # 检查是否为扫描件（先从缓存获取）
                file_key = f"{userbook}/{os.path.basename(full_file_path)}"
                pdf_type = global_var.get_pdf_type(file_key)

                # 如果缓存没有，则重新检测
                if pdf_type is None:
                    print(f"[布局PDF] 缓存未命中，重新检测PDF类型: {full_file_path}")
                    pdf_type = check_pdf_type_by_word(full_file_path)
                    global_var.set_pdf_type(file_key, pdf_type)

                is_scanned = (pdf_type == 'scanned')
                print(f"[布局PDF] PDF类型: {pdf_type}, 是否扫描件: {is_scanned}")

                # 如果是扫描件，尝试返回布局PDF
                if is_scanned:
                    file_base = os.path.splitext(os.path.basename(full_file_path))[0]
                    file_dir = os.path.dirname(full_file_path)
                    ocr_dir = os.path.join(file_dir, f"{file_base}_ocr")

                    # 尝试查找已有的布局PDF
                    layout_pdf_path = os.path.join(ocr_dir, f"{file_base}_layouts.pdf")

                    # 如果布局PDF不存在，尝试生成
                    if not os.path.exists(layout_pdf_path):
                        print(f"[布局PDF] 布局PDF不存在，尝试生成: {layout_pdf_path}")

                        # 尝试查找OCR txt文件
                        txt_path = os.path.join(ocr_dir, f"{file_base}_raw.txt")

                        if os.path.exists(txt_path):
                            # 有OCR结果，可以生成布局PDF
                            print(f"[布局PDF] 找到OCR结果，开始生成布局PDF")
                            success, generated_path = generate_layout_pdf(full_file_path, txt_path, layout_pdf_path)

                            if success and os.path.exists(layout_pdf_path):
                                print(f"[布局PDF] 布局PDF生成成功: {layout_pdf_path}")
                            else:
                                print(f"[布局PDF] 布局PDF生成失败")
                                layout_pdf_path = None
                        else:
                            print(f"[布局PDF] 未找到OCR结果文件: {txt_path}，无法生成布局PDF")
                            layout_pdf_path = None

                    # 如果布局PDF存在，返回布局PDF
                    if layout_pdf_path and os.path.exists(layout_pdf_path):
                        print(f"[布局PDF] 返回布局PDF: {layout_pdf_path}")
                        full_file_path = layout_pdf_path  # 使用布局PDF路径替换
                    else:
                        print(f"[布局PDF] 布局PDF不可用，返回原始PDF")

            except Exception as e:
                print(f"[布局PDF] 处理布局PDF时出错: {e}")
                import traceback
                traceback.print_exc()
                # 出错时继续正常流程

        # 确定文件的MIME类型
        content_type, _ = mimetypes.guess_type(full_file_path)
        if not content_type:
            content_type = 'application/pdf'  # 默认为PDF

        # 打开文件并创建响应
        file = open(full_file_path, 'rb')
        response = FileResponse(file, content_type=content_type)

        # # 设置Content-Disposition头（可选，用于控制是下载还是在浏览器中显示）
        # # response['Content-Disposition'] = f'inline; filename="{os.path.basename(file_path)}"'
        # 🔥 设置Content-Disposition（控制浏览器“下载”默认文件名）
        # 支持 query: download_name=xxx.pdf（UTF-8）
        try:
            download_name = request.GET.get('download_name', '') or ''
            # 只取basename，避免注入路径
            desired_name = os.path.basename(download_name) if download_name else os.path.basename(full_file_path)
            desired_name = desired_name.replace('\r', '').replace('\n', '').replace('"', '')
            if not desired_name.lower().endswith('.pdf') and content_type == 'application/pdf':
                desired_name = desired_name + '.pdf'

            from urllib.parse import quote
            ascii_fallback = re.sub(r'[^A-Za-z0-9._-]+', '_', desired_name) or 'file.pdf'
            response[
                'Content-Disposition'] = f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{quote(desired_name)}"
        except Exception as _e:
            # 回退到不设置也可正常显示
            pass

        # 设置Content-Length头
        response['Content-Length'] = os.path.getsize(full_file_path)

        return response

    except Exception as e:
        print(f"提供PDF文件时出错: {str(e)}")
        return JsonResponse({'error': f'服务器错误: {str(e)}'}, status=500)


@csrf_exempt
def save_audio_block_summary(request):
    """
    保存短期记忆块的多模态推理 Summary（仅写文件不落库）。
    路径：received_dir/user_raw_file/{userbook}/audio_block_summary/{block_id}_Summary.txt
    POST JSON: { "userbook": "xxx", "block_id": "xxx", "summary_text": "..." }
    """
    if request.method == 'OPTIONS':
        resp = JsonResponse({'ok': True})
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '仅支持 POST'}, status=405)

    try:
        try:
            data = json.loads(request.body)
        except Exception:
            data = {}

        userbook = (data.get('userbook') or '').strip()
        block_id = (data.get('block_id') or '').strip()
        summary_text = data.get('summary_text', '')
        if not userbook or not block_id:
            return JsonResponse({'error_num': 1, 'msg': '缺少 userbook 或 block_id'}, status=400)
        if '..' in userbook or '..' in block_id or '/' in block_id or '\\' in block_id:
            return JsonResponse({'error_num': 1, 'msg': '非法参数'}, status=400)

        base_path = './received_dir/user_raw_file/'
        userbook_path = os.path.join(base_path, userbook)
        summary_dir = os.path.join(userbook_path, 'audio_block_summary')
        os.makedirs(summary_dir, exist_ok=True)
        summary_path = os.path.join(summary_dir, f"{block_id}_Summary.txt")
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary_text if isinstance(summary_text, str) else str(summary_text))

        try:
            schedule_memory_tier_consolidation(userbook, block_id)
        except Exception as _tier_exc:
            print(f"[save_audio_block_summary] 记忆分层调度失败（已忽略）: {_tier_exc}")

        resp = JsonResponse({'error_num': 0, 'msg': 'success'})
        resp['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        print(f"[save_audio_block_summary] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error_num': 2, 'msg': str(e)}, status=500)


@csrf_exempt
def get_audio_block_summary(request):
    """
    读取单个短期记忆块已保存的 Summary 文件内容。
    GET: ?userbook=xxx&block_id=xxx
    """
    if request.method == 'OPTIONS':
        resp = JsonResponse({'ok': True})
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    if request.method != 'GET':
        return JsonResponse({'error': '仅支持 GET'}, status=405)

    userbook = (request.GET.get('userbook') or '').strip()
    block_id = (request.GET.get('block_id') or '').strip()
    if not userbook or not block_id:
        return JsonResponse({'error': '缺少 userbook 或 block_id'}, status=400)
    if '..' in userbook or '..' in block_id or '/' in block_id or '\\' in block_id:
        return JsonResponse({'error': '非法参数'}, status=403)

    base_path = './received_dir/user_raw_file/'
    userbook_path = os.path.join(base_path, userbook)
    summary_dir = os.path.join(userbook_path, 'audio_block_summary')
    summary_path = os.path.join(summary_dir, f"{block_id}_Summary.txt")
    if not os.path.isfile(summary_path):
        return JsonResponse({'error': 'Summary 文件不存在'}, status=404)

    try:
        with open(summary_path, 'r', encoding='utf-8') as f:
            content = f.read()
        from django.http import HttpResponse
        resp = HttpResponse(content, content_type='text/plain; charset=utf-8')
        resp['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        print(f"[get_audio_block_summary] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def list_audio_block_summaries(request):
    """
    列出当前 userbook 下所有已存在 Summary 文件的 Block_ID。
    GET: ?userbook=xxx
    """
    if request.method == 'OPTIONS':
        resp = JsonResponse({'ok': True})
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    if request.method != 'GET':
        return JsonResponse({'error': '仅支持 GET'}, status=405)

    userbook = (request.GET.get('userbook') or '').strip()
    if not userbook or '..' in userbook or userbook.startswith('/'):
        return JsonResponse({'error': '缺少或非法 userbook'}, status=400)

    base_path = './received_dir/user_raw_file/'
    summary_dir = os.path.join(base_path, userbook, 'audio_block_summary')
    block_ids = []
    if os.path.isdir(summary_dir):
        for name in os.listdir(summary_dir):
            if name.endswith('_Summary.txt'):
                bid = name[:-len('_Summary.txt')]
                if bid:
                    block_ids.append(bid)

    def sort_key(bid):
        m = re.match(r'^(.+)_(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})$', bid)
        return (m.group(2), bid) if m else (bid, bid)

    block_ids.sort(key=sort_key)
    resp = JsonResponse({'block_ids': block_ids})
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


@csrf_exempt
def get_memory_tier_context(request):
    """
    读取某用户前缀下的中期/长期叙事记忆，供回溯提示拼接。
    GET: ?userbook=xxx&user_id=xxx  （user_id 为短期块名的前缀，如 esp32-test）
    """
    if request.method == 'OPTIONS':
        resp = JsonResponse({'ok': True})
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    if request.method != 'GET':
        return JsonResponse({'error': '仅支持 GET'}, status=405)

    userbook = (request.GET.get('userbook') or '').strip()
    user_id = (request.GET.get('user_id') or '').strip()
    if not userbook or not user_id:
        return JsonResponse({'error': '缺少 userbook 或 user_id'}, status=400)
    if '..' in userbook or '/' in user_id or '\\' in user_id or '..' in user_id:
        return JsonResponse({'error': '非法参数'}, status=403)

    try:
        ctx = get_memory_tier_context_for_user(userbook, user_id)
        resp = JsonResponse({
            'error_num': 0,
            'long_narrative': ctx.get('long_narrative') or '',
            'mid_excerpts': ctx.get('mid_excerpts') or [],
        })
        resp['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        print(f"[get_memory_tier_context] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({'error_num': 1, 'msg': str(e)}, status=500)


@csrf_exempt
def check_ocr_origin_converted_pdf(request):
    """
    检查某个PDF是否存在OCR转换后的PDF（xxx_ocr/xxx_origin_converted.pdf 或 xxx_ocr/xxx_origin_convert.pdf）。
    返回JSON，带CORS头，供前端跨域fetch检测用。
    """
    # 处理预检
    if request.method == 'OPTIONS':
        resp = JsonResponse({'ok': True})
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    try:
        userbook = request.GET.get('userbook', '')
        filename = request.GET.get('filename', '')

        if not userbook or not filename:
            resp = JsonResponse({'exists': False, 'rel_path': ''}, status=200)
            resp['Access-Control-Allow-Origin'] = '*'
            return resp

        # 安全检查：防止路径遍历
        if '..' in userbook or '..' in filename or userbook.startswith('/') or filename.startswith('/'):
            resp = JsonResponse({'exists': False, 'rel_path': ''}, status=200)
            resp['Access-Control-Allow-Origin'] = '*'
            return resp

        base_path = './received_dir/user_raw_file/'
        userbook_path = os.path.join(base_path, userbook)

        file_base = os.path.splitext(os.path.basename(filename))[0]
        ocr_dir = os.path.join(userbook_path, f"{file_base}_ocr")

        candidates = [
            os.path.join(ocr_dir, f"{file_base}_origin_converted.pdf"),
            os.path.join(ocr_dir, f"{file_base}_origin_convert.pdf"),
        ]

        found_abs = None
        for p in candidates:
            if os.path.exists(p):
                found_abs = p
                break

        if not found_abs:
            resp = JsonResponse({'exists': False, 'rel_path': ''}, status=200)
            resp['Access-Control-Allow-Origin'] = '*'
            return resp

        # 组装相对路径（相对于 userbook 目录，供 /api/pdf/?url=... 使用）
        rel_path = os.path.relpath(found_abs, userbook_path).replace('\\', '/')
        resp = JsonResponse({'exists': True, 'rel_path': rel_path}, status=200)
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    except Exception as e:
        resp = JsonResponse({'exists': False, 'rel_path': '', 'error': str(e)}, status=200)
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp


@csrf_exempt
def check_ocr_converted_pdf(request):
    """
    检查某个PDF是否存在OCR转换后的PDF（xxx_ocr/xxx_converted.pdf 或 xxx_ocr/xxx_convert.pdf）。
    返回JSON，带CORS头，供前端跨域fetch检测用。
    """
    # 处理预检
    if request.method == 'OPTIONS':
        resp = JsonResponse({'ok': True})
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    try:
        userbook = request.GET.get('userbook', '')
        filename = request.GET.get('filename', '')

        if not userbook or not filename:
            resp = JsonResponse({'exists': False, 'rel_path': ''}, status=200)
            resp['Access-Control-Allow-Origin'] = '*'
            return resp

        # 安全检查：防止路径遍历
        if '..' in userbook or '..' in filename or userbook.startswith('/') or filename.startswith('/'):
            resp = JsonResponse({'exists': False, 'rel_path': ''}, status=200)
            resp['Access-Control-Allow-Origin'] = '*'
            return resp

        base_path = './received_dir/user_raw_file/'
        userbook_path = os.path.join(base_path, userbook)

        file_base = os.path.splitext(os.path.basename(filename))[0]
        ocr_dir = os.path.join(userbook_path, f"{file_base}_ocr")

        candidates = [
            os.path.join(ocr_dir, f"{file_base}_converted.pdf"),
            os.path.join(ocr_dir, f"{file_base}_convert.pdf"),
        ]

        found_abs = None
        for p in candidates:
            if os.path.exists(p):
                found_abs = p
                break

        if not found_abs:
            resp = JsonResponse({'exists': False, 'rel_path': ''}, status=200)
            resp['Access-Control-Allow-Origin'] = '*'
            return resp

        # 组装相对路径（相对于 userbook 目录，供 /api/pdf/?url=... 使用）
        rel_path = os.path.relpath(found_abs, userbook_path).replace('\\', '/')
        resp = JsonResponse({'exists': True, 'rel_path': rel_path}, status=200)
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp

    except Exception as e:
        resp = JsonResponse({'exists': False, 'rel_path': '', 'error': str(e)}, status=200)
        resp['Access-Control-Allow-Origin'] = '*'
        resp['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        resp['Access-Control-Allow-Headers'] = 'Content-Type'
        return resp


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


@csrf_exempt
def save_deleted_files(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get('username')
            scene_name = data.get('sceneName')
            filenames = data.get('deletedFiles', [])
            print(f"[save_deleted_files]{filenames}")

            # 先删除该用户在该场景下的所有记录
            DeletedFile.objects.filter(username=username, scene_name=scene_name).delete()

            # 保存新的删除记录；对应 Skill 标 orphaned（不自动删磁盘）
            try:
                from app_chat.skills_store import mark_orphaned_for_file
            except Exception:
                mark_orphaned_for_file = None
            for filename in filenames:
                DeletedFile.objects.create(
                    username=username,
                    filename=filename,
                    scene_name=scene_name
                )
                if mark_orphaned_for_file and username and filename:
                    try:
                        mark_orphaned_for_file(username, filename)
                    except Exception as _oe:
                        print(f"[save_deleted_files] orphaned 标记失败 {filename}: {_oe}")

            return JsonResponse({'error_num': 0})
        except Exception as e:
            return JsonResponse({'error_num': 1, 'msg': str(e)})


def get_deleted_files(request):
    if request.method == 'GET':
        try:
            username = request.GET.get('username')
            scene_name = request.GET.get('sceneName')

            deleted_files = DeletedFile.objects.filter(
                username=username,
                scene_name=scene_name
            ).values_list('filename', flat=True)
            print(f"[get_deleted_files]{deleted_files}")
            return JsonResponse({
                'error_num': 0,
                'content': list(deleted_files)
            })
        except Exception as e:
            return JsonResponse({'error_num': 1, 'msg': str(e)})


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
    OPEN_AI_KEY = _public_config.secret('KIMI_API_KEY')  # kimi
    base_url = "https://api.moonshot.cn/v1"

    try:
        print("reget_topics------------------")
        chat_model = ChatOpenAI(temperature=1.0,
                                openai_api_key=OPEN_AI_KEY,
                                openai_api_base=base_url,
                                # streaming=True,
                                model_name="kimi-k3",
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
        originRealName = request.POST.get('originRealName', '')
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
        originRealName = data.get('originRealName', '')
        content = data["content"]
        sceneName = data["sceneName"]
        subSceneName = data["subSceneName"]
        keyTopics = data.get('keyTopics', '[]')

    try:
        # 将 keyTopics 字符串解析为列表
        try:
            keyTopicsList = json.loads(keyTopics) if isinstance(keyTopics, str) else (keyTopics or [])
        except Exception:
            keyTopicsList = []

        # 交互式 Add Card：标题 + 卡片级四色/DMT 并发完成后建卡；语义关键词后台补全
        name2RealUse = originRealName if originRealName != "" else username
        subSceneOrder, subSceneNameListOrder, index = resolve_subscene_title_prefix(sceneName, subSceneName)
        is_neuron = False
        try:
            if index is not None and index + 1 == len(subSceneNameListOrder):
                is_neuron = True
                print(f"[add_card_directly] 标记为神经元卡（最后一个子场景）")
        except Exception:
            pass

        # 🔥 移除emoji，避免MySQL utf8字符集不支持4字节UTF-8字符的问题
        content = remove_emojis(content)

        # 批改配置卡：建卡前校验模板 + 材料标识须与本子文件完全同名
        try:
            from app_chat.grading_config_card import (
                is_grading_config_content,
                list_notebook_filenames,
                validate_grading_config_for_create,
            )
            if is_grading_config_content(content):
                try:
                    ok_cfg, cfg_errs = validate_grading_config_for_create(
                        content, list_notebook_filenames(username)
                    )
                    if not ok_cfg:
                        return JsonResponse({
                            'error_num': 1,
                            'msg': '；'.join(cfg_errs) if cfg_errs else '批改配置卡校验失败',
                        })
                except Exception as _val_e:
                    print(f'[add_card_directly] 批改配置卡校验异常: {_val_e}')
                    return JsonResponse({
                        'error_num': 1,
                        'msg': f'批改配置卡校验异常: {str(_val_e)[:200]}',
                    })
        except Exception as _cfg_e:
            print(f'[add_card_directly] 批改配置卡模块加载失败（非配置卡仍继续）: {_cfg_e}')

        gpt4_response_title, four_color_type, dmt_level, is_analyzed_by_new_standard = (
            generate_title_and_card_attrs_parallel(
                content, username, sceneName, subSceneName,
                is_neuron=is_neuron,
                provisional_content_title=subSceneOrder,
            )
        )
        # 批改配置卡标题可识别
        if '【批改配置卡】' in (content or ''):
            gpt4_response_title = '批改配置卡'
        contentTitle = subSceneOrder + gpt4_response_title
        keyWords = SEMANTIC_KEYWORDS_PENDING

        # score, color, reason = red_bule_rate.get_rate(username, content)
        score = -2
        color = "紫"
        reason = ""

        # 确定作者信息
        if originRealName != "":
            writer = originRealName
        else:
            writer = username

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
            contentTitle=contentTitle,
            writer=writer,  # 添加作者信息
            four_color_type=four_color_type,  # 🔥 四色类型
            dmt_level=dmt_level,  # 🔥 DMT层次
            is_neuron=is_neuron,  # 🔥 神经元卡标记
            is_analyzed_by_new_standard=is_analyzed_by_new_standard  # 🔥 新标准分析标记
        )
        card.save()
        print("add_card_directly: success-----------------")

        # 语义关键词后台补全
        start_fill_card_semantic_keywords_background(
            card.cid, username, name2RealUse, sceneName, subSceneName, keyTopicsList
        )

        # 🔥 检测是否为目录卡片（在后台异步执行，不阻塞主请求）
        def _check_directory_card_add_card():
            try:
                from app_chat.views_generate_output_article import check_and_update_directory_card
                from django.test import RequestFactory
                factory = RequestFactory()
                request_data = {
                    'card_id': card.cid,
                    'username': username,
                    'scene_name': sceneName,
                    'content': content
                }
                req = factory.post('/api/check_and_update_directory_card', data=json.dumps(request_data),
                                   content_type='application/json')
                response = check_and_update_directory_card(req)
                if response.status_code == 200:
                    result = json.loads(response.content)
                    if result.get('is_directory'):
                        print(
                            f"[add_card_directly] 检测到目录卡片，已更新title和contentTitle: {result.get('title')}, {result.get('contentTitle')}")
            except Exception as e:
                print(f"[add_card_directly] 检测目录卡片失败: {e}")
                import traceback
                traceback.print_exc()

        # 在后台线程中执行目录卡片检测
        dir_check_thread = threading.Thread(
            target=_check_directory_card_add_card,
            daemon=True
        )
        dir_check_thread.start()

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
            'contentTitle': contentTitle,
            'keywords_pending': True,
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

            from app_chat.card_keyword_extract import extract_card_semantic_keywords
            keyWords = extract_card_semantic_keywords(
                contentTotalSample,
                key_topics=keyTopicsList,
                with_candidates=True,
            )
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
        # command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' http://localhost:8000/invoke_rate'
        server_url = get_small_model_server_url(username)
        command = f'curl -X POST -H "Content-Type: application/json" -d \'{{"username":"{username}","text":"{text}"}}\' {server_url}/invoke_rate'
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
        text = data.get('text', '')  # GCS输入
        text_for_d = data.get('text_for_d', '')  # D输入（新增）

        # 将实际换行符 \n 替换为显式的 \\n
        text = text.replace("\n", "\\n")
        if text_for_d:
            text_for_d = text_for_d.replace("\n", "\\n")
        else:
            text_for_d = text  # 如果未提供，使用与GCS相同的输入

        session_id = data.get('sessionId', str(uuid.uuid4()))
        add_mode = data.get('add_mode', '')  # 获取评估模式参数
        include_d_part = data.get('include_d_part', True)  # 获取D部分参数，默认为True
        gcs_content_mode = data.get('gcs_content_mode', 'simple_reason')  # GCS内容模式
        d_content_mode = data.get('d_content_mode', 'inspire_framework')  # D内容模式

        # 存储会话数据
        SESSION_STORE[session_id] = {
            'username': username,
            'text': text,
            'text_for_d': text_for_d,  # 新增：D部分的输入
            'add_mode': add_mode,
            'include_d_part': include_d_part,
            'gcs_content_mode': gcs_content_mode,
            'd_content_mode': d_content_mode,
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
    add_mode = ''
    if session_id and session_id in SESSION_STORE:
        # 从会话存储获取数据
        session_data = SESSION_STORE[session_id]
        username = session_data['username']
        text = session_data['text']  # GCS输入
        text_for_d = session_data.get('text_for_d', text)  # D输入（新增）
        add_mode = session_data.get('add_mode', '')
        include_d_part = session_data.get('include_d_part', True)
        gcs_content_mode = session_data.get('gcs_content_mode', 'simple_reason')
        d_content_mode = session_data.get('d_content_mode', 'inspire_framework')
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
            server_url = get_small_model_server_url(username)
            future = session.post(
                f'{server_url}/invoke_rate_stream',
                json={
                    "username": username,
                    "text": text,  # GCS输入
                    "text_for_d": text_for_d,  # D输入（新增）
                    "add_mode": add_mode,
                    "include_d_part": include_d_part,
                    "gcs_content_mode": gcs_content_mode,
                    "d_content_mode": d_content_mode
                },
                stream=True
            )
            response = future.result()

            # 检查响应状态
            if response.status_code != 200:
                yield f"data: {json.dumps({'error': f'响应状态码: {response.status_code}'})}\n\n"
                return

            # 流式传输响应
            num = 0
            full_content = ""  # 累积完整内容用于解析评分
            for chunk in response.iter_lines():
                if chunk:
                    # 确保输出格式符合SSE规范
                    line = chunk.decode('utf-8')
                    if num < 10:
                        print(line)
                        num += 1

                    # 累积内容
                    if line.startswith('data: '):
                        content_part = line[6:]  # 去掉 "data: " 前缀
                        try:
                            parsed = json.loads(content_part)
                            if 'content' in parsed:
                                full_content += parsed['content']
                        except:
                            full_content += content_part

                    if not line.startswith('data: '):
                        line = f"data: {line}"
                    yield line + '\n\n'

            # 解析评分信息（如果有）
            if add_mode and '置信度' in full_content and '腐烂度' in full_content:
                # 匹配格式：X.X_颜色_置信度X.X_腐烂度X.X_内容
                match = re.search(r'(\d+\.?\d*)_[^_]+_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)_', full_content)
                if match:
                    red_blue_score = float(match.group(1))  # 原有红蓝评分
                    confidence_score = float(match.group(2))
                    rot_score = float(match.group(3))
                    scores = {
                        'red_blue_score': red_blue_score,  # 红蓝评分
                        'confidence_score': confidence_score,
                        'rot_score': rot_score
                    }
                    print(f"[DEBUG] 解析到评分 - 红蓝: {red_blue_score}, 置信度: {confidence_score}, 腐烂度: {rot_score}")
                    yield f"data: {json.dumps({'scores': scores})}\n\n"

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
def card_eval(request):
    data = json.loads(request.body)
    cid = data["cid"]
    content = data["content"]

    try:
        card = Card.objects.get(cid=cid)

        # 填充红蓝微调评测模型打分等字段,保存更改
        print(content)
        score = float(extract_number(content))
        print("card_eval-------------------------")
        print(score)
        color = extract_color(content)
        print(color)
        reason = extract_reason(content)
        print(reason)
        # 更新字段, 保存到数据库
        card.score = score
        card.color = color
        if card.score >= 1.0 and card.color != "紫":
            card.color = "紫"
        card.reason = reason
        card.save()

        return JsonResponse({
            'status': 'success',
            'score': score,
            'error_num': 0,
        }, status=201)
    except Exception as e:
        print(str(e))
        return JsonResponse({
            'status': 'fail',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def card_evalSFT(request):
    data = json.loads(request.body)
    cid = data["cid"]
    content = data["content"]

    try:
        card = Card.objects.get(cid=cid)
        print("card_evalSFT-------------------------")
        print(content)
        # 填充红蓝微调评测模型打分等字段,保存更改
        scoreSFT = float(extract_number_SFT(content))
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
        }, status=200)
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
                                openai_api_base=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
                                default_headers={"x-foo": "true"},
                                model_name="gpt-4o",
                                max_tokens=1000)
        content = ""
        if voiceText != "No":
            messages = [HumanMessage(content=[
                {
                    "type": "text",
                    "text": f"""请仔细分析这张图片，用户的具体问题是：{voiceText}

                分析要求：
                1. 【深度解答】：针对用户问题给出专业、准确的回答，要有实际价值，避免空话套话
                2. 【分类识别】：快速判断图片类型（文档/报告、商品/物品、错误/问题、场景/环境、数据/图表、其他）
                3. 【关键信息提取】：识别图中的核心信息，如文字内容、数值数据、状态信息、品牌型号等
                4. 【实用建议】：基于分析给出可操作的建议或下一步行动

                回复格式：
                **图片类型**：[简要说明图片属于什么类型]
                **核心发现**：[提取的关键信息，如重要数据、文字内容、问题症状等]
                **专业解答**：[针对用户问题的深度分析，150-250字，要有专业性和实用性]
                **建议行动**：[具体的操作建议或解决方案，2-3条实用建议]

                注意：
                - 如果是技术问题，给出可能原因和解决方法
                - 如果是商品咨询，分析功能特点和使用建议  
                - 如果是文档内容，提取要点并解释含义
                - 如果是数据图表，分析趋势和关键指标
                - 避免"看起来""似乎"等不确定表述，要给出明确判断"""
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
                    "text": """请仔细分析这张图片，判断用户可能的需求并提供有价值的见解。

                分析框架：
                1. 【图片分类】：首先判断图片类型和用户可能的意图
                   - 文档类：合同、报告、账单、说明书等 → 解读要点、风险提醒
                   - 商品类：产品、食物、购物截图等 → 分析特点、比较建议
                   - 技术类：错误页面、设备问题、软件界面等 → 诊断问题、解决方案
                   - 场景类：环境、活动、场所等 → 识别关键要素、提供见解
                   - 数据类：图表、报表、统计等 → 解读趋势、重要发现
                   - 学习类：习题、知识点、学习资料等 → 知识解释、学习建议

                2. 【深度分析】：基于图片类型进行专业分析，提供真正有用的信息

                回复格式：
                **识别结果**：[图片类型 + 可能的用户需求]
                **关键信息**：[提取的重要内容，如文字、数据、状态等]
                **深度见解**：[专业分析，150-250字，要有深度和价值，避免表面描述]
                **实用建议**：[针对性的操作建议，2-3条具体可行的建议]

                要求：
                - 提供专业级别的分析，不要停留在表面描述
                - 发现一般人容易忽略的细节和要点
                - 给出可以立即执行的具体建议
                - 如果涉及专业领域，用通俗语言解释专业概念
                - 重点关注实用性和可操作性"""
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


def compress_image_base64(base64_image, target_size_mb=0.2):
    """压缩base64图片到指定大小"""
    try:
        # 提取数据部分（移除 Base64 前缀，如果有的话）
        if ',' in base64_image:
            base64_image = base64_image.split(',')[1]

        # 解码图片
        image_data = base64.b64decode(base64_image)
        img = Image.open(io.BytesIO(image_data))

        # 目标大小（字节）
        target_size = target_size_mb * 1024 * 1024

        # 如果图片已经小于目标大小，直接返回
        if len(image_data) <= target_size:
            return base64_image

        # 压缩质量从90开始
        quality = 90
        while quality > 20:
            output = io.BytesIO()

            # 如果图片太大，先缩小尺寸
            if len(image_data) > target_size * 3:
                # 计算缩放比例
                ratio = (target_size * 2 / len(image_data)) ** 0.5
                new_size = (int(img.width * ratio), int(img.height * ratio))
                resized_img = img.resize(new_size, Image.Resampling.LANCZOS)
                resized_img.save(output, format='JPEG', quality=quality, optimize=True)
            else:
                img.save(output, format='JPEG', quality=quality, optimize=True)

            compressed_data = output.getvalue()

            if len(compressed_data) <= target_size:
                return base64.b64encode(compressed_data).decode('utf-8')

            quality -= 10

        # 如果还是太大，最后一次大幅缩小
        ratio = (target_size / len(image_data)) ** 0.5
        new_size = (int(img.width * ratio), int(img.height * ratio))
        final_img = img.resize(new_size, Image.Resampling.LANCZOS)

        output = io.BytesIO()
        final_img.save(output, format='JPEG', quality=60, optimize=True)
        return base64.b64encode(output.getvalue()).decode('utf-8')

    except Exception as e:
        print(f"图片压缩失败: {e}")
        return base64_image


def save_card_background(username, image_base64, content, contentHL, prompt):
    """后台保存卡片数据"""
    try:
        score = float(extract_number(contentHL))
        color = extract_color(contentHL)
        reason = extract_reason(contentHL)

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
                sid = 1  # 默认场景ID

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
        cardContent = prompt + "\n\n批改修正的指导建议:\n" + content

        # 生成关键词和标题（admin 可切模型；尽量≤6，必要时≤8）
        from app_chat.card_keyword_extract import extract_card_semantic_keywords
        keyWords = extract_card_semantic_keywords(
            cardContent,
            notebook_description="拍卡视频笔记分析",
            with_candidates=False,
            username=username + "_shootCardAnalysis",
        )

        # system_prompt_title = (
        #     '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，'
        #     '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求'
        #     '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        # )
        # prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + cardContent
        # kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)
        # contentTitle = kimi_response_title.choices[0].message.content

        # 🔥 并行生成标题和关键词的DMT/四色分析（注意：这个函数没有sceneName，使用None）
        contentTitle, keyword_results = generate_title_and_analyze_keywords_parallel(
            keyWords, cardContent, username + "_shootCardAnalysis", username, None, None
        )

        # 创建卡片
        card = Card.objects.create(
            status=0,
            content=cardContent,
            title="直接生成卡片",
            model_id=0,
            username=username + "_shootCardAnalysis",
            score=score,
            color=color,
            reason=reason,
            keyWords=keyWords,
            contentTitle=contentTitle
        )
        card.save()

        # 步骤4: 保存图片
        image_dir = f"./received_dir/user_raw_file/{username}_shootCardAnalysis/cardImage"
        os.makedirs(image_dir, exist_ok=True)

        # 提取数据部分
        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]

        image_data = base64.b64decode(image_base64)
        image_path = os.path.join(image_dir, f"{card.cid}.jpg")

        with open(image_path, 'wb') as f:
            f.write(image_data)

        print(f"后台保存卡片完成: {card.cid}")

    except Exception as e:
        print(f"后台保存卡片失败: {e}")


def stream_card_analysis(data):
    """流式生成卡片分析结果"""
    try:
        username = data["username"]
        image_base64 = data["image"]

        # 获取响应级别参数（默认5s级别）
        response_level = data.get("response_level", "5s")

        # 根据响应级别设置图片压缩大小
        compression_map = {
            "3s": 0.1,  # 3秒响应
            "5s": 0.2,  # 5秒响应
            "10s": 0.4  # 10秒响应
        }
        target_size = compression_map.get(response_level, 0.2)

        # 提取教育相关字段
        subject = data.get("学科", "未知学科")
        school = data.get("学校", "未知学校")
        grade = data.get("年级", "未知年级")
        class_name = data.get("班级", "未知班级")
        term = data.get("学期", "未知学期")
        unit = data.get("单元", "未知单元")
        class_stage = data.get("课程阶段", "未知阶段")
        layout_type = data.get("版面类别", "未知版面")

        if layout_type == "01":
            layout_type = "黑板"
        elif layout_type == "02":
            layout_type = "PPT"
        else:
            layout_type = "其他版面"

        # 压缩图片
        compressed_image = compress_image_base64(image_base64, target_size_mb=target_size)

        # 构建分析提示词（保留核心分析方法）
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

        请你作为一名专业的{subject}教师，采用多层次分析法对图片内容进行解读：

        【版面结构分析】
        分析图片的整体版面关系和区域划分，识别主要区域和子版面。

        【多层次内容识别】
        将图片内容分层解读：
        1. 印刷层：识别教材、试卷等印刷文字内容
        2. 涂鸦层：识别批注符号、勾画、圈点、下划线等标记
        3. 手写层：识别学生或教师的手写字迹

        【层间关联分析】
        通过不同层次间的关联，提高理解准确度：
        - 当手写字迹不清时，参考周围涂鸦符号的语义
        - 分析印刷内容与涂鸦、手写内容的关联

        【教学专业评估】
        基于上述分析，提供专业评估：
        1. 详细描述图片中的内容
        2. 对学生作业进行专业批改，指出正误
        3. 给出具体的修改建议和改进方向
        4. 分析学生可能的知识盲点
        5. 提供有针对性的指导建议

        请详细、专业地给出分析和批改意见，语言温和鼓励但不失严谨。"""

        # 红蓝融合评估提示词（保留核心评估规则）
        promptHLBase = f"""你是一名{subject}教师，请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。

        背景信息：
        - 学校: {school}
        - 年级: {grade}
        - 班级: {class_name}
        - 学期: {term}
        - 学科: {subject}
        - 单元: {unit}
        - 课程阶段: {class_stage}
        - 版面类别: {layout_type}"""

        promptHL = """你是根据学生传来的卡片图文信息进行打分的专家。如果图文信息与认知、教育、群组学习等有关，请依据红蓝融合理念评分。

        红蓝融合五层理念：
        第一层：人文<红>和科技<蓝>的融合
        第二层：认知<红>和行动<蓝>的融合（知行合一）
        第三层：自上而下贯彻带领<红>+自下而上创造示范<蓝>的融合
        第四层：目标<红>和任务<蓝>的融合
        第五层：静态边界堤坝<红>和动态筛分洪流<蓝>的融合

        评分规则：
        - 1-5分对应五个层次，层次越高得分越高
        - 只体现<红>或<蓝>其中一个，不超过1分
        - 0.4分：仅红或仅蓝；0.6分：以蓝表红；0.8分：红蓝组合但不融合
        - 3-5分需体现群组视角，4-5分需体现先进组织意识

        输出格式：分值_颜色_理由和改进建议
        - 颜色：≥1分输出紫色，<1分输出红色或蓝色
        - 理由：60字左右描述评分依据
        - 改进建议：针对涉及角色（≤2个）提出80-100字具体可执行的改进策略

        例如：2.5分_紫色_体现认知行动结合但缺乏组织协作视角，内容具有一定针对性但可操作性有限。建议学生角色：加强知识点间的逻辑关联，通过小组讨论验证理解效果；建议教师角色：设计更多实践环节，引导学生从个人学习向协作学习转变。"""

        # 启动后台红蓝评估
        hl_future = background_executor.submit(
            gpt4_api.make_gpt4o_image_text_requests,
            promptHLBase, compressed_image, text_after_image=promptHL, use_fixed_params=True
        )

        # 流式返回主要分析内容
        full_content = ""
        stream_response = gpt4_api.make_gpt4o_image_text_requests_stream(
            prompt, compressed_image, use_fixed_params=True
        )

        for chunk in stream_response:
            if chunk.choices[0].delta.content:
                content_chunk = chunk.choices[0].delta.content
                full_content += content_chunk

                # 流式输出格式
                yield f"data: {json.dumps({'type': 'content', 'data': content_chunk}, ensure_ascii=False)}\n\n"

        # 等待红蓝评估完成
        try:
            contentHL = hl_future.result(timeout=30)
            score = float(extract_number(contentHL))
            color = extract_color(contentHL)
            reason = extract_reason(contentHL)

            # 发送红蓝评估结果
            yield f"data: {json.dumps({'type': 'evaluation', 'data': {'score': score, 'color': color, 'reason': reason}}, ensure_ascii=False)}\n\n"

        except Exception as e:
            print(f"红蓝评估失败: {e}")
            score, color, reason = 0.0, "蓝色", "评估失败"
            yield f"data: {json.dumps({'type': 'evaluation', 'data': {'score': score, 'color': color, 'reason': reason}}, ensure_ascii=False)}\n\n"

        # 后台异步保存数据
        background_executor.submit(
            save_card_background,
            username, image_base64, full_content, contentHL, prompt
        )

        # 发送完成信号
        yield f"data: {json.dumps({'type': 'complete', 'data': 'success'}, ensure_ascii=False)}\n\n"

    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"


@csrf_exempt
def shootCardAnalysis(request):
    try:
        data = json.loads(request.body)

        # 检查是否请求流式响应
        if data.get("stream", False):
            return StreamingHttpResponse(
                stream_card_analysis(data),
                content_type='text/event-stream'
            )

        username = data["username"]
        image_base64 = data["image"]
        # voiceText = data.get("voiceText", "No")

        # 获取响应级别参数
        response_level = data.get("response_level", "5s")
        compression_map = {"3s": 0.1, "5s": 0.2, "10s": 0.4}
        target_size = compression_map.get(response_level, 0.2)

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
        content_ctx = data.get("content", "")
        relate_content_ctx = data.get("relateContent", "")

        # "01"/"02" 为原有拍卡编码，xmate 场景直接传中文名（"作业"/"笔记"等），保持原样
        if layout_type == "01":
            layout_type = "黑板"
        elif layout_type == "02":
            layout_type = "PPT"
        elif layout_type in ("未知版面", ""):
            layout_type = "其他版面"
        # else: 已是中文名（"作业"/"笔记"/"练字"等），直接使用

        # 构建基础信息（共用于各个提示词）
        base_info = f"""
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
- 学生编号: {student_id}
- 小组编号: {group_id}
- 小组组型: {group_type}
- 拍照的时间: {real_time}
- 完成上传提交的时间: {update_time}
- 版面题目: {content_ctx}
- 关联内容: {relate_content_ctx}
"""

        # 根据版面类别生成不同的提示词
        if layout_type == "练字":
            prompt = f"""请仔细看这张图片，这是一张学生的练字作品。

{base_info}

请你作为一名专业的书法/语文教师，专注于**如何写好字**，给出具体的书写指导建议。请按以下结构回答：

【整体书写评价】
- 字体的工整度、大小一致性、行列对齐情况
- 整体印象（认真/潦草/有待提升）

【执笔与运笔建议】
- 执笔姿势：针对图片中显示的字迹特点，推测学生可能的执笔问题（如手指用力过紧、笔杆角度不当等），给出纠正方法
- 运笔技巧：分析笔画的特点（如起笔、行笔、收笔是否到位，有没有抖笔、拖笔现象），给出改善运笔的具体练习方法

【笔画与结构指导】
- 指出典型的好字样例（如果有）和需要改进的字
- 针对某个或多个明显不规范的字，解析其笔画顺序、间架结构（如左右结构、上下结构的比例）
- 提供针对性的临摹或描红建议

【书写习惯与态度】
- 分析书写是否专注（如字迹忽大忽小、涂改较多可能表示匆忙）
- 给出日常练字的实用建议（如定时定量、慢写求精、对照字帖等）

请用温和鼓励的语气，给出具体可操作的方法，帮助学生逐步提升书写质量。"""

        elif layout_type == "作业":
            prompt = f"""请仔细看这张图片，这是一份学生的学科作业。

{base_info}

请你作为一名专业的{subject}教师，重点判断作业的**潦草程度**以及**内容对错**。请按以下结构回答：

【潦草程度判别】
- 整体清晰度：是否容易辨认每一个字和符号（清晰/一般/潦草）
- 具体表现：字迹连笔过多、涂改严重、行列歪斜、字母/数字不规范等
- 结论：潦草程度（不潦草/轻微潦草/中等潦草/非常潦草）

【内容批改】
- 逐题或分部分判断对错，指出正确之处和错误之处
- 对错误题目给出正确答案或正确思路
- 简单说明错误原因（概念不清、计算失误、审题错误等）

【改进建议】
- 针对潦草问题：如何改善书写可读性（例如放慢速度、规范基本笔画、使用辅助线等）
- 针对知识错误：建议复习的知识点、练习方向
- 给出鼓励性评语，强调整洁书写与正确率同样重要

请用简明清晰的语言，让学生既能看懂错在哪里，也知道如何改进。"""

        elif layout_type == "笔记":
            prompt = f"""请仔细看这张图片，这是一份学生的课堂笔记或自学笔记。

{base_info}

请你作为一名专业的{subject}教师，重点关注学生是否进行了**创造性书写**和**自主理解**。请按以下结构回答：

【内容梳理】
- 笔记覆盖的核心知识点概要
- 信息组织形式（纯抄写/有归纳/有图表/有批注等）

【创造性评估】
- 是否体现出学生自己的理解：例如用自己的话重述概念、添加举例、总结规律、画出思维导图或关系图
- 是否有主动的联想、提问、批判性思考（如标注“为什么”、“注意”等）
- 是否有创造性的表达：例如改编口诀、设计记忆符号、颜色标记层次、个性化整理方式
- 总体评级：创造性水平（高/中/低/无）

【亮点与提升建议】
- 表扬笔记中已有的创造性尝试或清晰逻辑
- 给出提升创造性的具体方法：如鼓励使用康奈尔笔记法、制作概念图、每一节留出“我的思考”区域、用问答形式整理错题等
- 建议如何将笔记转化为学习成果（如定期回顾、向同学讲解自己的总结）

请以激发学生主动思考为目标，多给予肯定和启发式的建议。"""

        else:
            # 原有通用多层次分析提示词
            prompt = f"""请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。

{base_info}

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

        # 如果有语音文本，可取消注释并追加到提示词末尾
        # if voiceText and voiceText != "No":
        #     prompt += f"\n\n用户通过语音提出的具体问题或需求是：{voiceText}。请在批改的基础上特别关注并解答这个问题。"

        # 构建红蓝融合评估的提示词（保持不变）
        promptHLBase = f"""你是一名{subject}教师，请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。

{base_info}"""

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

        # 根据需要的响应速度压缩图片
        # 3s级别: 0.1MB, 5s级别: 0.2MB, 10s级别: 0.4MB
        compressed_image = compress_image_base64(image_base64, target_size_mb=target_size)

        # 并行调用GPT-4o（使用压缩后的图片）
        future1 = background_executor.submit(
            gpt4_api.make_gpt4o_image_text_requests,
            prompt, compressed_image, use_fixed_params=True
        )

        future2 = background_executor.submit(
            gpt4_api.make_gpt4o_image_text_requests,
            promptHLBase, compressed_image, text_after_image=promptHL, use_fixed_params=True
        )

        # 等待结果（设置较短超时）
        content = future1.result(timeout=30)
        contentHL = future2.result(timeout=30)

        print("批改修正的指导建议:\n" + content)
        print("红蓝卡标:\n" + contentHL)

        # 提取红蓝卡标信息
        score = float(extract_number(contentHL))
        color = extract_color(contentHL)
        reason = extract_reason(contentHL)

        # 后台异步保存数据（不影响响应速度）
        background_executor.submit(
            save_card_background,
            username, image_base64, content, contentHL, prompt
        )

        # 立即返回结果
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


# @csrf_exempt
# def shootCardAnalysis(request):
#     try:
#         data = json.loads(request.body)

#         # 检查是否请求流式响应
#         if data.get("stream", False):
#             return StreamingHttpResponse(
#                 stream_card_analysis(data),
#                 content_type='text/event-stream'
#             )

#         username = data["username"]
#         image_base64 = data["image"]
#         # voiceText = data.get("voiceText", "No")

#         # 获取响应级别参数
#         response_level = data.get("response_level", "5s")
#         compression_map = {"3s": 0.1, "5s": 0.2, "10s": 0.4}
#         target_size = compression_map.get(response_level, 0.2)

#         # 提取教育相关字段
#         role = data.get("数据创建角色", "未知角色")
#         school = data.get("学校", "未知学校")
#         grade = data.get("年级", "未知年级")
#         class_name = data.get("班级", "未知班级")
#         term = data.get("学期", "未知学期")
#         layout_type = data.get("版面类别", "未知版面")
#         teacher_id = data.get("教师编号", "未知教师")
#         student_id = data.get("学生编号", "未知学生")
#         group_id = data.get("小组编号", "未知小组")
#         group_type = data.get("小组组型", "未知组型")
#         subject = data.get("学科", "未知学科")
#         unit = data.get("单元", "未知单元")
#         class_stage = data.get("课程阶段", "未知阶段")
#         real_time = data.get("真实时间", "未知时间")
#         update_time = data.get("更新时间", "未知时间")

#         if layout_type == "01":
#             layout_type = "黑板"
#         elif layout_type == "02":
#             layout_type = "PPT"
#         else:
#             layout_type = "其他版面"

#         # 构建提示词
#         prompt = f"""请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。

#         背景信息：
#         - 学校: {school}
#         - 年级: {grade}
#         - 班级: {class_name}
#         - 学期: {term}
#         - 学科: {subject}
#         - 单元: {unit}
#         - 课程阶段: {class_stage}
#         - 版面类别: {layout_type}
#         - 数据创建角色: {role}
#         - 小组编号: {group_id}
#         - 小组组型: {group_type}
#         - 拍照的时间: {real_time}
#         - 完成上传提交的时间: {update_time}

#         请你作为一名专业的{subject}教师，采用多层次分析法对图片内容进行深入解读：

#         【版面结构分析】
#         首先分析图片的整体版面关系和区域划分：
#         1. 识别图片中的主要区域和子版面（如是否有标题区、正文区、批注区、练习区等）
#         2. 确定各区域之间的空间关系和逻辑连接
#         3. 利用图片中的相对位置信息辅助理解内容

#         【多层次内容识别】
#         将图片内容分为四个层次进行逐层解读：
#         1. 辅助信息层：图片的元数据信息（时间、地点、背景信息等文本）
#         2. 印刷层：识别教材、试卷等印刷文字内容（识别率应该很高）
#         3. 涂鸦层：识别批注符号、勾画、圈点、下划线等非正式标记（识别率较高）
#         4. 手写层：识别学生或教师的手写字迹（因个人书写习惯差异和情绪变化等，识别率稳定性可能低些）

#         【层间关联分析】
#         你应该考虑的并不是对于多层次的图片识别存在上面的不足，而是如何通过不同层次之间的关联，更高质量地推测、理解本来容易出错的后续层次：
#         1. 当手写字迹不清时，参考周围涂鸦符号（如对勾、问号）的语义辅助理解
#         2. 分析印刷内容与涂鸦、手写内容的关联（如圈点、划线部分对应的批注）
#         3. 利用版面关系和辅助信息来推测难以识别内容的可能含义

#         【教学专业评估】
#         基于上述多层分析，提供专业的教学评估：
#         1. 详细描述图片中的内容，包括各层次信息的综合理解
#         2. 对学生上传的此图片进行专业批改，指出正确之处和错误之处
#         3. 给出具体的修改建议和改进方向
#         4. 分析学生可能存在的知识盲点或误解
#         5. 针对发现的问题，提供有针对性的指导建议

#         【笔迹与情绪分析】（如适用）
#         1. 分析手写字迹的特点（如字体大小、笔画连贯性、书写压力等）
#         2. 推测书写时的情绪状态（如专注、匆忙、困惑等）
#         3. 基于笔迹分析给出书写习惯的改进建议

#         即使图片并不是按这样分层的，比如各种原理图、绘画等，也可以参照这种思路来加深对图片的理解；广义上一切皆可批改（批语），分析图片背后的层次关系、图片产生时的可能状态等
#         请详细、专业、有条理地给出分析和批改意见，语言要温和鼓励但不失严谨。运用层间关联的方法提高对内容的理解准确度，降低误解和幻觉的可能性。"""

#         # 如果有语音文本，添加到提示词中
#         # if voiceText and voiceText != "No":
#         #     prompt += f"\n\n用户通过语音提出的具体问题或需求是：{voiceText}。请在批改的基础上特别关注并解答这个问题。"

#         # 构建第二个提示词：红蓝融合度评估
#         promptHLBase = f"""你是一名{subject}教师，请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。

#         背景信息：
#         - 学校: {school}
#         - 年级: {grade}
#         - 班级: {class_name}
#         - 学期: {term}
#         - 学科: {subject}
#         - 单元: {unit}
#         - 课程阶段: {class_stage}
#         - 版面类别: {layout_type}
#         - 数据创建角色: {role}
#         - 小组编号: {group_id}
#         - 小组组型: {group_type}
#         - 拍照的时间: {real_time}
#         - 完成上传提交的时间: {update_time}"""

#         promptHL = """你是根据学生传来的卡片图文信息进行打分的专家，首先注意，下面的红蓝融合不仅是军事政工领域，也能用于教育和群组学习等领域，如果图文信息不涉及下面的红蓝融合理念第一层，但与认知、教育、群组学习等有关，请你依据下面红蓝融合理念第二至五层（可以越过第一层直接打2至5分）、是否有利于认知水平提升、是否有利于实现目标等来给分！

#         若与红蓝融合有关，则你需要对上面给出的图文信息进行红蓝融合度评估打分，红蓝融合度打分规则如下:
#         1.红蓝融合五层理念是你打分需要参考的最主要标准，具体如下：
#         第一层：人文<红>和科技<蓝>的融合（如传统红色人文与新兴信息技术的有机结合）；
#         第二层：认知<红>和行动<蓝>的融合（认知与行动需要一致，认知为行动提供理论基础，行动实践为认知提供真实验证，知行合一，行动不用非常具体但要有此意识）；
#         第三层：自上而下贯彻带领<红>+自下而上创造示范<蓝>的融合（如组织中领导层向下进行示范牵引、基层成员执行及发挥创造，或其他协作形式）；
#         第四层：先进组织认知中，目标<红>和任务<蓝>的融合（如目标的分解、放大、击穿，任务能够指向目标，为目标服务，组织成员公份和私份任务比例合理）；
#         第五层：静态边界堤坝<红>和动态筛分洪流<蓝>的融合（静态堤坝指一些边界性限制，动态筛分洪流指运用第二层、第三层、第四层中的一些理念，如知行是否合一、组织不同层级成员上下是否联通、是否分清目标和任务等，来筛选出最优质的内容并扩散共生）
#         2.（1）上面的红蓝融合理念由浅到深呈金字塔型，由底层基础到上层升维共分为5层，得分对应着由低到高的1-5分，
#         （2）如果图文信息能体现出前面的红蓝融合五层理念中任意一层，则最低从1分开始，体现出红蓝融合五层理念的层次越高，得分越高，否则得分越低。
#         例如：图文信息能够体现人文和科技的融合（第一层），则从1分开始；在1分基础上若还能达到行和知的融合，有"怎么做"的意识（第二层），则加到2分；在2分基础上若不能达到自上而下和自下而上的融合（第三层），如仅体现了自上而下没有体现自下而上或两个都有体现但达不到融合，则不能达到3分，得2.5分
#         补充说明：前面说的"体现"，只要有一定体现的意识即可，不必过于严苛、死板，请把握好程度
#         注意：1-5分范围内，若给小数分值，只考虑按0.5的步长调整。
#         （3）由于不能达到红蓝融合（红蓝分离）的情况普遍存在，所以除了上面的1-5分以外，你还需要注意0-1分的含义，图文信息若只体现了<红>或<蓝>的内涵，体现不出红蓝的"融合"，则不超过1分。
#         小数分值参考标准：图文信息体现低级红高级黑（使用庸俗夸张的方式赞扬或抹黑），按程度给0分或0.2分；体现仅红或仅蓝（只谈其中一个），给0.4分；体现以蓝表红（认为<蓝>就是<红>），给0.6分；体现红蓝组合（简单组合，并不融合），给0.8分
#         （4）你还需要考虑图文信息与红蓝融合的相关性，与认知无关的内容给0分
#         （5）另外请注意：当你想要打高于3分时，即3-5分，需要稍多做些考虑。科技+人文\行+知（第一二层，即1-2分），都偏向于个人，有一些组织意识；而更深入的第三四五层需要能够很好地体现群组视角，且逐层深入
#         具体标准：你在判别是否达到第三层（即是否能打到3分）时，判据之一：需要体现群组视角；判别是否达到第四层（即是否能打到4分）时，判据之一：需要体现先进组织（目标任务意识清晰，有助于成员共生）；判别是否达到第五层（即是否能打到5分）时，判据之一：需要体现熵减生态（是否包含：a.面向成长、b.真实目标驱动、c.群组共生）
#         （6）图文信息如果包含想法、看法和更重要的做法，且对实际执行具有很好的指导意义，则可以视程度提高0.5分或1分
#         3.注意，你只需且必须要按"分值_颜色_理由和改进建议"格式输出！
#         分值方面，是你综合以上规则对给出的图文信息做出的打分；
#         颜色方面，只要大于或等于1分直接输出紫色，若小于1分，图文信息过<红>输出红色，过<蓝>输出蓝色，注意小于1分只能输出红色或蓝色，不能是紫色或其他！
#         理由和改进建议方面，先用<60字左右>描述你给出分值和颜色的理由，依据包括：
#         （1）是否体现对应的红蓝融合五层理念，为什么；
#         （2）图文信息的内容是否具有针对性，是否具体、可操作、可实施；
#         （3）图文内容是否有能深入扩展、探究、优化提升的潜力
#         给出理由后，根据理由，针对上面的图文信息可能涉及到的角色（≤2个），分别提出<80到100字左右>的改进策略和建议，注意你给出改进建议一定要和图文信息的主要、关键内容高度相关，对涉及到的想法做法等给出改进建议，且角色针对性强，以这个为主！然后以红蓝打分理由中导致得分下降的因素、思维模式的可能调整为辅。给出的想法、做法建议要具体，有真实行动上能够立即执行的清晰明确的指导，而不是泛泛而谈。格式模板为"建议xx角色：xxx；建议xx角色：xxx；......"。
#         整体格式例如：0.4分_蓝色_具体理由和建议
#         2.5分_紫色_具体理由和建议
#         4.0分_紫色_具体理由和建议
#         ...（其他分值，但一定要按以上要求）"""

#         # 根据需要的响应速度压缩图片
#         # 3s级别: 0.1MB, 5s级别: 0.2MB, 10s级别: 0.4MB
#         compressed_image = compress_image_base64(image_base64, target_size_mb=target_size)

#         # 并行调用GPT-4o（使用压缩后的图片）
#         future1 = background_executor.submit(
#             gpt4_api.make_gpt4o_image_text_requests,
#             prompt, compressed_image, use_fixed_params=True
#         )

#         future2 = background_executor.submit(
#             gpt4_api.make_gpt4o_image_text_requests,
#             promptHLBase, compressed_image, text_after_image=promptHL, use_fixed_params=True
#         )

#         # 等待结果（设置较短超时）
#         content = future1.result(timeout=30)
#         contentHL = future2.result(timeout=30)

#         print("批改修正的指导建议:\n" + content)
#         print("红蓝卡标:\n" + contentHL)

#         # 提取红蓝卡标信息
#         score = float(extract_number(contentHL))
#         color = extract_color(contentHL)
#         reason = extract_reason(contentHL)

#         # 后台异步保存数据（不影响响应速度）
#         background_executor.submit(
#             save_card_background,
#             username, image_base64, content, contentHL, prompt
#         )

#         # 立即返回结果
#         return JsonResponse({
#             'content': content,
#             'score': score,
#             'color': color,
#             'reason': reason,
#             'status': 'success',
#             'error_num': 0,
#         }, status=201)

#     except Exception as e:
#         print(f"发生错误: {str(e)}")
#         return JsonResponse({
#             'status': 'fail',
#             'error_num': 1,
#             'error_msg': str(e)
#         }, status=201)


# @csrf_exempt
# def shootCardAnalysis(request):
#     try:
#         data = json.loads(request.body)
#         username = data["username"]
#         image_base64 = data["image"]
#         # voiceText = data.get("voiceText", "No")
#
#         # 提取教育相关字段
#         role = data.get("数据创建角色", "未知角色")
#         school = data.get("学校", "未知学校")
#         grade = data.get("年级", "未知年级")
#         class_name = data.get("班级", "未知班级")
#         term = data.get("学期", "未知学期")
#         layout_type = data.get("版面类别", "未知版面")
#         teacher_id = data.get("教师编号", "未知教师")
#         student_id = data.get("学生编号", "未知学生")
#         group_id = data.get("小组编号", "未知小组")
#         group_type = data.get("小组组型", "未知组型")
#         subject = data.get("学科", "未知学科")
#         unit = data.get("单元", "未知单元")
#         class_stage = data.get("课程阶段", "未知阶段")
#         real_time = data.get("真实时间", "未知时间")
#         update_time = data.get("更新时间", "未知时间")
#
#         if layout_type == "01":
#             layout_type = "黑板"
#         elif layout_type == "02":
#             layout_type = "PPT"
#         else:
#             layout_type = "其他版面"
#
#         # 构建提示词
#         prompt = f"""请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。
#
# 背景信息：
# - 学校: {school}
# - 年级: {grade}
# - 班级: {class_name}
# - 学期: {term}
# - 学科: {subject}
# - 单元: {unit}
# - 课程阶段: {class_stage}
# - 版面类别: {layout_type}
# - 数据创建角色: {role}
# - 小组编号: {group_id}
# - 小组组型: {group_type}
# - 拍照的时间: {real_time}
# - 完成上传提交的时间: {update_time}
#
# 请你作为一名专业的{subject}教师，采用多层次分析法对图片内容进行深入解读：
#
# 【版面结构分析】
# 首先分析图片的整体版面关系和区域划分：
# 1. 识别图片中的主要区域和子版面（如是否有标题区、正文区、批注区、练习区等）
# 2. 确定各区域之间的空间关系和逻辑连接
# 3. 利用图片中的相对位置信息辅助理解内容
#
# 【多层次内容识别】
# 将图片内容分为四个层次进行逐层解读：
# 1. 辅助信息层：图片的元数据信息（时间、地点、背景信息等文本）
# 2. 印刷层：识别教材、试卷等印刷文字内容（识别率应该很高）
# 3. 涂鸦层：识别批注符号、勾画、圈点、下划线等非正式标记（识别率较高）
# 4. 手写层：识别学生或教师的手写字迹（因个人书写习惯差异和情绪变化等，识别率稳定性可能低些）
#
# 【层间关联分析】
# 你应该考虑的并不是对于多层次的图片识别存在上面的不足，而是如何通过不同层次之间的关联，更高质量地推测、理解本来容易出错的后续层次：
# 1. 当手写字迹不清时，参考周围涂鸦符号（如对勾、问号）的语义辅助理解
# 2. 分析印刷内容与涂鸦、手写内容的关联（如圈点、划线部分对应的批注）
# 3. 利用版面关系和辅助信息来推测难以识别内容的可能含义
#
# 【教学专业评估】
# 基于上述多层分析，提供专业的教学评估：
# 1. 详细描述图片中的内容，包括各层次信息的综合理解
# 2. 对学生上传的此图片进行专业批改，指出正确之处和错误之处
# 3. 给出具体的修改建议和改进方向
# 4. 分析学生可能存在的知识盲点或误解
# 5. 针对发现的问题，提供有针对性的指导建议
#
# 【笔迹与情绪分析】（如适用）
# 1. 分析手写字迹的特点（如字体大小、笔画连贯性、书写压力等）
# 2. 推测书写时的情绪状态（如专注、匆忙、困惑等）
# 3. 基于笔迹分析给出书写习惯的改进建议
#
# 即使图片并不是按这样分层的，比如各种原理图、绘画等，也可以参照这种思路来加深对图片的理解；广义上一切皆可批改（批语），分析图片背后的层次关系、图片产生时的可能状态等
# 请详细、专业、有条理地给出分析和批改意见，语言要温和鼓励但不失严谨。运用层间关联的方法提高对内容的理解准确度，降低误解和幻觉的可能性。"""
#
#         # 如果有语音文本，添加到提示词中
#         # if voiceText and voiceText != "No":
#         #     prompt += f"\n\n用户通过语音提出的具体问题或需求是：{voiceText}。请在批改的基础上特别关注并解答这个问题。"
#
#         # 构建第二个提示词：红蓝融合度评估
#         promptHLBase = f"""你是一名{subject}教师，请仔细看这张图片，这是一张来自教育环境的学习材料或学生作业。
#
# 背景信息：
# - 学校: {school}
# - 年级: {grade}
# - 班级: {class_name}
# - 学期: {term}
# - 学科: {subject}
# - 单元: {unit}
# - 课程阶段: {class_stage}
# - 版面类别: {layout_type}
# - 数据创建角色: {role}
# - 小组编号: {group_id}
# - 小组组型: {group_type}
# - 拍照的时间: {real_time}
# - 完成上传提交的时间: {update_time}"""
#
#         promptHL = """你是根据学生传来的卡片图文信息进行打分的专家，首先注意，下面的红蓝融合不仅是军事政工领域，也能用于教育和群组学习等领域，如果图文信息不涉及下面的红蓝融合理念第一层，但与认知、教育、群组学习等有关，请你依据下面红蓝融合理念第二至五层（可以越过第一层直接打2至5分）、是否有利于认知水平提升、是否有利于实现目标等来给分！
#
# 若与红蓝融合有关，则你需要对上面给出的图文信息进行红蓝融合度评估打分，红蓝融合度打分规则如下:
# 1.红蓝融合五层理念是你打分需要参考的最主要标准，具体如下：
# 第一层：人文<红>和科技<蓝>的融合（如传统红色人文与新兴信息技术的有机结合）；
# 第二层：认知<红>和行动<蓝>的融合（认知与行动需要一致，认知为行动提供理论基础，行动实践为认知提供真实验证，知行合一，行动不用非常具体但要有此意识）；
# 第三层：自上而下贯彻带领<红>+自下而上创造示范<蓝>的融合（如组织中领导层向下进行示范牵引、基层成员执行及发挥创造，或其他协作形式）；
# 第四层：先进组织认知中，目标<红>和任务<蓝>的融合（如目标的分解、放大、击穿，任务能够指向目标，为目标服务，组织成员公份和私份任务比例合理）；
# 第五层：静态边界堤坝<红>和动态筛分洪流<蓝>的融合（静态堤坝指一些边界性限制，动态筛分洪流指运用第二层、第三层、第四层中的一些理念，如知行是否合一、组织不同层级成员上下是否联通、是否分清目标和任务等，来筛选出最优质的内容并扩散共生）
# 2.（1）上面的红蓝融合理念由浅到深呈金字塔型，由底层基础到上层升维共分为5层，得分对应着由低到高的1-5分，
# （2）如果图文信息能体现出前面的红蓝融合五层理念中任意一层，则最低从1分开始，体现出红蓝融合五层理念的层次越高，得分越高，否则得分越低。
# 例如：图文信息能够体现人文和科技的融合（第一层），则从1分开始；在1分基础上若还能达到行和知的融合，有"怎么做"的意识（第二层），则加到2分；在2分基础上若不能达到自上而下和自下而上的融合（第三层），如仅体现了自上而下没有体现自下而上或两个都有体现但达不到融合，则不能达到3分，得2.5分
# 补充说明：前面说的"体现"，只要有一定体现的意识即可，不必过于严苛、死板，请把握好程度
# 注意：1-5分范围内，若给小数分值，只考虑按0.5的步长调整。
# （3）由于不能达到红蓝融合（红蓝分离）的情况普遍存在，所以除了上面的1-5分以外，你还需要注意0-1分的含义，图文信息若只体现了<红>或<蓝>的内涵，体现不出红蓝的"融合"，则不超过1分。
# 小数分值参考标准：图文信息体现低级红高级黑（使用庸俗夸张的方式赞扬或抹黑），按程度给0分或0.2分；体现仅红或仅蓝（只谈其中一个），给0.4分；体现以蓝表红（认为<蓝>就是<红>），给0.6分；体现红蓝组合（简单组合，并不融合），给0.8分
# （4）你还需要考虑图文信息与红蓝融合的相关性，与认知无关的内容给0分
# （5）另外请注意：当你想要打高于3分时，即3-5分，需要稍多做些考虑。科技+人文\行+知（第一二层，即1-2分），都偏向于个人，有一些组织意识；而更深入的第三四五层需要能够很好地体现群组视角，且逐层深入
# 具体标准：你在判别是否达到第三层（即是否能打到3分）时，判据之一：需要体现群组视角；判别是否达到第四层（即是否能打到4分）时，判据之一：需要体现先进组织（目标任务意识清晰，有助于成员共生）；判别是否达到第五层（即是否能打到5分）时，判据之一：需要体现熵减生态（是否包含：a.面向成长、b.真实目标驱动、c.群组共生）
# （6）图文信息如果包含想法、看法和更重要的做法，且对实际执行具有很好的指导意义，则可以视程度提高0.5分或1分
# 3.注意，你只需且必须要按"分值_颜色_理由和改进建议"格式输出！
# 分值方面，是你综合以上规则对给出的图文信息做出的打分；
# 颜色方面，只要大于或等于1分直接输出紫色，若小于1分，图文信息过<红>输出红色，过<蓝>输出蓝色，注意小于1分只能输出红色或蓝色，不能是紫色或其他！
# 理由和改进建议方面，先用<60字左右>描述你给出分值和颜色的理由，依据包括：
# （1）是否体现对应的红蓝融合五层理念，为什么；
# （2）图文信息的内容是否具有针对性，是否具体、可操作、可实施；
# （3）图文内容是否有能深入扩展、探究、优化提升的潜力
# 给出理由后，根据理由，针对上面的图文信息可能涉及到的角色（≤2个），分别提出<80到100字左右>的改进策略和建议，注意你给出改进建议一定要和图文信息的主要、关键内容高度相关，对涉及到的想法做法等给出改进建议，且角色针对性强，以这个为主！然后以红蓝打分理由中导致得分下降的因素、思维模式的可能调整为辅。给出的想法、做法建议要具体，有真实行动上能够立即执行的清晰明确的指导，而不是泛泛而谈。格式模板为"建议xx角色：xxx；建议xx角色：xxx；......"。
# 整体格式例如：0.4分_蓝色_具体理由和建议
# 2.5分_紫色_具体理由和建议
# 4.0分_紫色_具体理由和建议
# ...（其他分值，但一定要按以上要求）"""
#
#         # 调用OpenAI
#         # gpt_vision = ChatOpenAI(temperature=0,
#         #                         openai_api_key=OPEN_AI_KEY,
#         #                         openai_api_base='http://localhost:9999/v1/',
#         #                         default_headers={"x-foo": "true"},
#         #                         model_name="gpt-4o",
#         #                         max_tokens=2048)
#         #
#         # messages = [HumanMessage(content=[
#         #     {
#         #         "type": "text",
#         #         "text": prompt
#         #     },
#         #     {
#         #         "type": "image_url",
#         #         "image_url": {
#         #             "url": f"data:image/jpeg;base64,{image_base64}"
#         #         }
#         #     }
#         # ])]
#         # content = gpt_vision.invoke(messages).content
#         # print("批改修正的指导建议:\n" + content)
#         #
#         # messagesHL = [HumanMessage(content=[
#         #     {
#         #         "type": "text",
#         #         "text": promptHLBase
#         #     },
#         #     {
#         #         "type": "image_url",
#         #         "image_url": {
#         #             "url": f"data:image/jpeg;base64,{image_base64}"
#         #         }
#         #     },
#         #     {
#         #         "type": "text",
#         #         "text": promptHL
#         #     }
#         # ])]
#         # contentHL = gpt_vision.invoke(messagesHL).content
#         # print("红蓝卡标:\n" + contentHL)
#
#         # 替换原来的代码
#         # 第一个调用
#         content = gpt4_api.make_gpt4o_image_text_requests(prompt, image_base64, use_fixed_params=True)
#         print("批改修正的指导建议:\n" + content)
#
#         # 第二个调用（保持文本-图片-文本的顺序）
#         contentHL = gpt4_api.make_gpt4o_image_text_requests(promptHLBase, image_base64, text_after_image=promptHL,
#                                                    use_fixed_params=True)
#         print("红蓝卡标:\n" + contentHL)
#
#         score = float(extract_number(contentHL))
#         color = extract_color(contentHL)
#         reason = extract_reason(contentHL)
#
#         # 以上完成向拍卡笔记app端的交互，以下完成NKCN本端的留存
#         # 步骤1: 检查用户是否存在
#         try:
#             user = User.objects.get(username=username)
#         except ObjectDoesNotExist:
#             username = "2112557"  # 如果用户不存在，使用默认用户名
#
#         # 步骤2: 检查是否有对应的笔记本，如果没有则创建
#         try:
#             notebook = UserNotebook.objects.get(username=username, bookName="shootCardAnalysis")
#         except ObjectDoesNotExist:
#             # 获取场景ID
#             try:
#                 scene_item = scene.objects.get(sceneDescription="纸联·拍卡视频笔记分析")
#                 sid = scene_item.sid
#             except ObjectDoesNotExist:
#                 # 如果场景不存在，可以设置一个默认值或返回错误
#                 return JsonResponse({
#                     'status': 'error',
#                     'error_num': 1,
#                     'msg': '找不到指定的场景'
#                 })
#
#             # 创建新的笔记本
#             notebook = UserNotebook(
#                 username=username,
#                 bookId=int(datetime.now().timestamp() * 1000),
#                 bookName="shootCardAnalysis",
#                 bookdescription="拍卡视频笔记分析",
#                 sid=sid,
#                 writer=username
#             )
#             notebook.save()
#
#         # 步骤3: 添加卡片
#         # 生成关键词
#         cardContent = prompt + "\n\n批改修正的指导建议:\n" + content
#         system_prompt = (
#             '你是擅长阅读理解文本并总结关键词的专家。'
#             '你接下来将得到一段文本，你需要阅读理解这段文本，总结出1到3个关键词。'
#             '共需得出1到3个关键词（2个为佳），输出格式如"关键词1，关键词2，关键词3"，无其他多余内容！'
#         )
#         prompt_for_keywords = (
#             f"{system_prompt}\n"
#             f"需要你总结关键词的文本：\n{cardContent}"
#         )
#         kimi_response = kimi_api.make_requests(prompt_for_keywords, None, False, 0.8)
#         keyWords = kimi_response.choices[0].message.content
#
#         # 生成标题
#         system_prompt_title = (
#             '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，'
#             '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求'
#             '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
#         )
#         prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + cardContent
#         kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)
#         contentTitle = kimi_response_title.choices[0].message.content
#
#         # 创建卡片
#         card = Card.objects.create(
#             status=0,  # 参与的迭代的次数
#             content=cardContent,
#             title="直接生成卡片",
#             model_id=0,  # 参与融合的卡片个数
#             username=username + "_shootCardAnalysis",
#             score=score,
#             color=color,
#             reason=reason,
#             keyWords=keyWords,
#             contentTitle=contentTitle
#         )
#         card.save()
#
#         # 步骤4: 保存图片
#         # 确保目录存在
#         image_dir = f"./received_dir/user_raw_file/{username}_shootCardAnalysis/cardImage"
#         os.makedirs(image_dir, exist_ok=True)
#
#         # 提取数据部分（移除 Base64 前缀，如果有的话）
#         if ',' in image_base64:
#             image_base64 = image_base64.split(',')[1]
#
#         # 解码 Base64 并保存为文件
#         image_data = base64.b64decode(image_base64)
#         image_path = os.path.join(image_dir, f"{card.cid}.jpg")  # 使用卡片ID作为文件名
#
#         with open(image_path, 'wb') as f:
#             f.write(image_data)
#
#         return JsonResponse({
#             'content': content,
#             'score': score,
#             'color': color,
#             'reason': reason,
#             'status': 'success',
#             'error_num': 0,
#         }, status=201)
#     except Exception as e:
#         print(f"发生错误: {str(e)}")
#         return JsonResponse({
#             'status': 'fail',
#             'error_num': 1,
#             'error_msg': str(e)
#         }, status=201)


# @csrf_exempt
# def BodyCardAnalysis(request):
#     try:
#         data = json.loads(request.body)
#         username = data["username"]
#
#         # Extract body data
#         body_data = data.get("bodyData", {})
#         temp = body_data.get("temp", 0)
#         hr = body_data.get("hr", 0)
#         bp = body_data.get("bp", "0/0")
#         yin = body_data.get("yin", 0)
#         yang = body_data.get("yang", 0)
#         period = body_data.get("period", "未知时辰")
#
#         # Extract harmonics data
#         harmonics = data.get("harmonics", [])
#
#         # Get the image base64 data
#         image_base64 = data.get("image", "")
#
#         snorePrediction = data.get("snorePrediction", 0)
#
#         # Extract sleep time data
#         start_sleep_time = data.get("startSleepTime", "")
#         start_snore_stop_time = data.get("startSnoreStopTime", "")
#         end_sleep_time = data.get("endSleepTime", "")
#
#         # Construct sleep time string based on snorePrediction
#         sleep_time_info = ""
#         if snorePrediction == -1:
#             # 空字符串
#             pass
#         elif snorePrediction == 0:
#             # 只使用开始睡觉和结束睡觉
#             if start_sleep_time:
#                 sleep_time_info += f"\n- 开始睡觉时间: {start_sleep_time}"
#             if end_sleep_time:
#                 sleep_time_info += f"\n- 结束睡觉时间: {end_sleep_time}"
#         elif snorePrediction == 1:
#             # 使用所有三个字段
#             if start_sleep_time:
#                 sleep_time_info += f"\n- 开始睡觉时间: {start_sleep_time}"
#             if start_snore_stop_time:
#                 sleep_time_info += f"\n- 开始鼾声停止时间: {start_snore_stop_time}"
#             if end_sleep_time:
#                 sleep_time_info += f"\n- 结束睡觉时间: {end_sleep_time}"
#
#         # Construct the prompt for GPT-4o
#         prompt = f"""请仔细分析这张脉象波形图，这是一份来自中医体联脉象诊断系统的数据。
#
# 基本体征信息：
# - 体温: {temp}°C
# - 心率: {hr} 次/分钟
# - 血压: {bp} mmHg
# - 阴值: {yin}
# - 阳值: {yang}
# - 当前时辰: {period}
# - 呼吸识别（0是非鼾声，1是鼾声，2是咳嗽声）：{snorePrediction}{sleep_time_info}
#
# 傅里叶谐波分析数据（前10阶）："""
#
#         # Add harmonics data to prompt
#         for harmonic in harmonics:
#             order = harmonic.get("order", 0)
#             freq = harmonic.get("freq", 0)
#             cn = harmonic.get("Cn", 0)
#             phase = harmonic.get("phase", 0)
#             prompt += f"""
# 第{order}阶谐波:
# - 频率: {freq} Hz
# - 归一化振幅: {cn}
# - 相位: {phase} rad"""
#
#         prompt += """
#
# 请作为一名专业的中医脉诊专家，结合五时流注理论对图中的波形和上述数据进行深入解读：
#
# 【波形结构分析】
# 1. 分析波形的整体形态特征（平滑度、峰值特点、谷值特点）
# 2. 确定波形类型（弦、滑、洪、细等传统脉象类型）
# 3. 分析波形的规律性和周期性变化
#
# 【PSI节律分析要求】
# 1. P体力节律：高潮期体力充沛、动作敏捷、抗病能力强；临界日抵抗力最低、极易受伤、慢性病复发危险期；低潮期身体乏力、易疲劳感染
# 2. S情绪节律：高潮期心情愉快、创造力强、人际和谐；临界日情绪极不稳定、易怒冲动、事故自杀高发期；低潮期情绪低落、意志消沉、缺乏信心
# 3. I智力节律：高潮期思维敏捷、记忆力强、判断准确、效率最高；临界日判断力差、严重健忘、极易出错；低潮期思维迟钝、理解缓慢、效率不高
# 4. 【核心规律】：三节律呈正弦波变化，临界日为各类事故、疾病、失误的最危险转换期
#
# 【谐波特征解读】
# 1. 基于前10阶谐波数据，分析波形的频域特性
# 2. 解读各阶谐波的振幅和相位特征
# 3. 评估谐波比例与中医脉象的关联性
#
# 【阴阳平衡评估】
# 1. 结合阴阳值和波形特征，评估气血平衡状态
# 2. 根据当前时辰（五时），解读经络气血运行特点
# 3. 分析潜在的阴阳失衡状况及其与时辰的关系
#
# 【中医辨证分析】
# 1. 根据波形特征和谐波数据，进行脏腑功能状态评估
# 2. 结合体温、心率、血压等客观指标，评估整体健康状况
# 3. 进行五行归类（木火土金水）和辨证（寒热虚实）分析
#
# 【养生保健建议】
# 1. 基于以上分析，提供针对性的养生保健建议
# 2. 结合五时流注理论，给出适合当前时辰的调理方法
# 3. 推荐适合的饮食、活动和情志调节方式
#
# 请详细、专业、有条理地给出分析和建议，语言要温和鼓励但不失严谨。运用传统中医理论结合现代数据分析方法，提高诊断的准确度和实用性。"""
#
#         # 构建第二个提示词：红蓝融合度评估
#         promptHLBase = f"""请仔细分析这张脉象波形图和相关数据，这份资料来自中医体联脉象诊断系统。
#
# 基本体征信息：
# - 体温: {temp}°C
# - 心率: {hr} 次/分钟
# - 血压: {bp} mmHg
# - 阴值: {yin}
# - 阳值: {yang}
# - 当前时辰: {period}
# - 呼吸识别（0是非鼾声，1是鼾声，2是咳嗽声）：{snorePrediction}{sleep_time_info}"""
#
#         promptHL = """你是根据用户传来的脉象图文信息进行红蓝融合度打分的专家，首先注意，下面的红蓝融合不仅是军事政工领域，也能用于医疗保健、教育和群组学习等领域，如果图文信息不涉及下面的红蓝融合理念第一层，但与认知、健康、信息整合等有关，请你依据下面红蓝融合理念第二至五层（可以越过第一层直接打2至5分）、是否有利于认知水平提升、是否有利于实现健康目标等来给分！
#
# 若与红蓝融合有关，则你需要对上面给出的图文信息进行红蓝融合度评估打分，红蓝融合度打分规则如下:
# 1.红蓝融合五层理念是你打分需要参考的最主要标准，具体如下：
# 第一层：人文<红>和科技<蓝>的融合（如传统中医理论与现代数据分析技术的有机结合）；
# 第二层：认知<红>和行动<蓝>的融合（认知与行动需要一致，认知为行动提供理论基础，行动实践为认知提供真实验证，知行合一，行动不用非常具体但要有此意识）；
# 第三层：自上而下贯彻带领<红>+自下而上创造示范<蓝>的融合（如组织中领导层向下进行示范牵引、基层成员执行及发挥创造，或其他协作形式）；
# 第四层：先进组织认知中，目标<红>和任务<蓝>的融合（如目标的分解、放大、击穿，任务能够指向目标，为目标服务，组织成员公份和私份任务比例合理）；
# 第五层：静态边界堤坝<红>和动态筛分洪流<蓝>的融合（静态堤坝指一些边界性限制，动态筛分洪流指运用第二层、第三层、第四层中的一些理念，如知行是否合一、组织不同层级成员上下是否联通、是否分清目标和任务等，来筛选出最优质的内容并扩散共生）
# 2.（1）上面的红蓝融合理念由浅到深呈金字塔型，由底层基础到上层升维共分为5层，得分对应着由低到高的1-5分，
# （2）如果图文信息能体现出前面的红蓝融合五层理念中任意一层，则最低从1分开始，体现出红蓝融合五层理念的层次越高，得分越高，否则得分越低。
# 例如：图文信息能够体现人文和科技的融合（第一层），则从1分开始；在1分基础上若还能达到行和知的融合，有"怎么做"的意识（第二层），则加到2分；在2分基础上若不能达到自上而下和自下而上的融合（第三层），如仅体现了自上而下没有体现自下而上或两个都有体现但达不到融合，则不能达到3分，得2.5分
# 补充说明：前面说的"体现"，只要有一定体现的意识即可，不必过于严苛、死板，请把握好程度
# 注意：1-5分范围内，若给小数分值，只考虑按0.5的步长调整。
# （3）由于不能达到红蓝融合（红蓝分离）的情况普遍存在，所以除了上面的1-5分以外，你还需要注意0-1分的含义，图文信息若只体现了<红>或<蓝>的内涵，体现不出红蓝的"融合"，则不超过1分。
# 小数分值参考标准：图文信息体现低级红高级黑（使用庸俗夸张的方式赞扬或抹黑），按程度给0分或0.2分；体现仅红或仅蓝（只谈其中一个），给0.4分；体现以蓝表红（认为<蓝>就是<红>），给0.6分；体现红蓝组合（简单组合，并不融合），给0.8分
# （4）你还需要考虑图文信息与红蓝融合的相关性，与认知无关的内容给0分
# （5）另外请注意：当你想要打高于3分时，即3-5分，需要稍多做些考虑。科技+人文\行+知（第一二层，即1-2分），都偏向于个人，有一些组织意识；而更深入的第三四五层需要能够很好地体现群组视角，且逐层深入
# 具体标准：你在判别是否达到第三层（即是否能打到3分）时，判据之一：需要体现群组视角；判别是否达到第四层（即是否能打到4分）时，判据之一：需要体现先进组织（目标任务意识清晰，有助于成员共生）；判别是否达到第五层（即是否能打到5分）时，判据之一：需要体现熵减生态（是否包含：a.面向成长、b.真实目标驱动、c.群组共生）
# （6）图文信息如果包含想法、看法和更重要的做法，且对实际执行具有很好的指导意义，则可以视程度提高0.5分或1分
# 3.注意，你只需且必须要按"分值_颜色_理由和改进建议"格式输出！
# 分值方面，是你综合以上规则对给出的图文信息做出的打分；
# 颜色方面，只要大于或等于1分直接输出紫色，若小于1分，图文信息过<红>输出红色，过<蓝>输出蓝色，注意小于1分只能输出红色或蓝色，不能是紫色或其他！
# 理由和改进建议方面，先用<60字左右>描述你给出分值和颜色的理由，依据包括：
# （1）是否体现对应的红蓝融合五层理念，为什么；
# （2）图文信息的内容是否具有针对性，是否具体、可操作、可实施；
# （3）图文内容是否有能深入扩展、探究、优化提升的潜力
# 给出理由后，根据理由，针对上面的图文信息可能涉及到的角色（≤2个），分别提出<80到100字左右>的改进策略和建议，注意你给出改进建议一定要和图文信息的主要、关键内容高度相关，对涉及到的想法做法等给出改进建议，且角色针对性强，以这个为主！然后以红蓝打分理由中导致得分下降的因素、思维模式的可能调整为辅。给出的想法、做法建议要具体，有真实行动上能够立即执行的清晰明确的指导，而不是泛泛而谈。格式模板为"建议xx角色：xxx；建议xx角色：xxx；......"。
# 整体格式例如：0.4分_蓝色_具体理由和建议
# 2.5分_紫色_具体理由和建议
# 4.0分_紫色_具体理由和建议
# ...（其他分值，但一定要按以上要求）"""
#
#         # 替换原来的调用代码
#         # 第一个调用
#         content = gpt4_api.make_gpt4o_image_text_requests(prompt, image_base64, use_fixed_params=True)
#         print("脉象诊断分析:\n" + content)
#
#         # 第二个调用（保持文本-图片-文本的顺序）
#         contentHL = gpt4_api.make_gpt4o_image_text_requests(promptHLBase, image_base64, text_after_image=promptHL,
#                                                             use_fixed_params=True)
#         print("红蓝卡标:\n" + contentHL)
#
#         score = float(extract_number(contentHL))
#         color = extract_color(contentHL)
#         reason = extract_reason(contentHL)
#
#         # 以上完成向拍卡笔记app端的交互，以下完成NKCN本端的留存
#         # 步骤1: 检查用户是否存在
#         try:
#             user = User.objects.get(username=username)
#         except ObjectDoesNotExist:
#             username = "jesse"  # 如果用户不存在，使用默认用户名
#
#         # 步骤2: 检查是否有对应的笔记本，如果没有则创建
#         try:
#             notebook = UserNotebook.objects.get(username=username, bookName="Watch")
#         except ObjectDoesNotExist:
#             # 获取场景ID
#             try:
#                 scene_item = scene.objects.get(sceneDescription="体联·脉象算法五时流注")
#                 sid = scene_item.sid
#             except ObjectDoesNotExist:
#                 # 如果场景不存在，可以设置一个默认值或返回错误
#                 return JsonResponse({
#                     'status': 'error',
#                     'error_num': 1,
#                     'msg': '找不到指定的场景'
#                 })
#
#             # 创建新的笔记本
#             notebook = UserNotebook(
#                 username=username,
#                 bookId=int(datetime.now().timestamp() * 1000),
#                 bookName="Watch",
#                 bookdescription="脉象分析五时流注表",
#                 sid=sid,
#                 writer=username
#             )
#             notebook.save()
#
#         # 步骤3: 添加卡片
#         # 构建卡片内容
#         time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#
#         # 构建包含体征信息和分析结果的内容
#         cardContent = f"""# 脉象分析记录（{time_str}）
#
# ## 基本体征信息
# - 体温: {temp}°C
# - 心率: {hr} 次/分钟
# - 血压: {bp} mmHg
# - 阴值: {yin}
# - 阳值: {yang}
# - 当前时辰: {period}
# - 呼吸识别（0是非鼾声，1是鼾声，2是咳嗽声）：{snorePrediction}{sleep_time_info}
#
# ## 谐波分析数据（前10阶）
# """
#         # 添加谐波数据
#         for harmonic in harmonics:
#             order = harmonic.get("order", 0)
#             freq = harmonic.get("freq", 0)
#             cn = harmonic.get("Cn", 0)
#             phase = harmonic.get("phase", 0)
#             cardContent += f"""
# 第{order}阶谐波:
# - 频率: {freq} Hz
# - 归一化振幅: {cn}
# - 相位: {phase} rad
# """
#
#         # 添加分析结果
#         cardContent += f"""
# ## 专业分析结果
# {content}
# """
#
#         # 生成关键词
#         system_prompt = (
#             '你是擅长阅读理解文本并总结关键词的专家。'
#             '你接下来将得到一段文本，你需要阅读理解这段文本，总结出1到3个关键词。'
#             '共需得出1到3个关键词（2个为佳），输出格式如"关键词1，关键词2，关键词3"，无其他多余内容！'
#         )
#         prompt_for_keywords = (
#             f"{system_prompt}\n"
#             f"需要你总结关键词的文本：\n{cardContent}"
#         )
#         kimi_response = kimi_api.make_requests(prompt_for_keywords, None, False, 0.8)
#         keyWords = kimi_response.choices[0].message.content
#
#         # 生成标题
#         system_prompt_title = (
#             '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，'
#             '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求'
#             '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
#         )
#         prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + cardContent
#         kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)
#         contentTitle = kimi_response_title.choices[0].message.content
#
#         # 创建卡片
#         card = Card.objects.create(
#             status=0,  # 参与的迭代的次数
#             content=cardContent,
#             title="直接生成卡片",
#             model_id=0,  # 参与融合的卡片个数
#             username=username + "_Watch",
#             score=score,
#             color=color,
#             reason=reason,
#             keyWords=keyWords,
#             contentTitle=contentTitle
#         )
#         card.save()
#
#         # 步骤4: 保存图片
#         # 确保目录存在
#         image_dir = f"./received_dir/user_raw_file/{username}_Watch/cardImage"
#         os.makedirs(image_dir, exist_ok=True)
#
#         # 提取数据部分（移除 Base64 前缀，如果有的话）
#         if ',' in image_base64:
#             image_base64 = image_base64.split(',')[1]
#
#         # 解码 Base64 并保存为文件
#         image_data = base64.b64decode(image_base64)
#         image_path = os.path.join(image_dir, f"{card.cid}.jpg")  # 使用卡片ID作为文件名
#
#         with open(image_path, 'wb') as f:
#             f.write(image_data)
#
#         return JsonResponse({
#             'content': content,
#             'score': score,
#             'color': color,
#             'reason': reason,
#             'status': 'success',
#             'error_num': 0,
#         }, status=201)
#     except Exception as e:
#         print(f"发生错误: {str(e)}")
#         return JsonResponse({
#             'status': 'fail',
#             'error_num': 1,
#             'error_msg': str(e)
#         }, status=201)


@csrf_exempt
def BodyCardAnalysis(request):
    try:
        data = json.loads(request.body)
        username = data["username"]

        # Extract body data (新格式)
        body_data = data.get("body_data", {})
        hr = body_data.get("hr", 0)  # 心率
        spo2 = body_data.get("spo2", 0)  # 血氧饱和度
        microcirculation = body_data.get("microcirculation", 0)  # 微循环指数
        fatigue = body_data.get("fatigue", 0)  # 疲劳程度指数
        bp = body_data.get("bp", "0/0")  # 血压
        sdnn = body_data.get("sdnn", 0)  # 心率变异性指标 SDNN
        rmssd = body_data.get("rmssd", 0)  # 心率变异性指标 RMSSD
        nn50 = body_data.get("nn50", 0)  # 相邻RR间期差值大于50ms的次数
        pnn50 = body_data.get("pnn50", 0)  # NN50占比

        # Extract sleep data (新格式)
        sleep_data = data.get("sleep_data", {})
        start_sleep_time = sleep_data.get("start_sleep_time", "")
        sound_count = sleep_data.get("sound_count", 0)
        snore_count = sleep_data.get("snore_count", 0)
        snore_times = sleep_data.get("snore_times", [])

        # 睡眠PSI数据
        sleep_psi = sleep_data.get("psi", {})
        sleep_psi_p = sleep_psi.get("P", 0)
        sleep_psi_s = sleep_psi.get("S", 0)
        sleep_psi_i = sleep_psi.get("I", 0)

        # Extract harmonics data (新格式)
        harmonics_data = data.get("harmonics_data", {})
        base_frequency = harmonics_data.get("base_frequency", 0)
        harmonics = harmonics_data.get("harmonics", [])
        overall_amplitude_deviation = harmonics_data.get("overall_amplitude_deviation", 0)
        overall_phase_deviation = harmonics_data.get("overall_phase_deviation", 0)
        overall_total_deviation = harmonics_data.get("overall_total_deviation", 0)

        # 脉象PSI数据
        pulse_psi = harmonics_data.get("pulse_psi", {})
        pulse_psi_p = pulse_psi.get("P", 0)
        pulse_psi_s = pulse_psi.get("S", 0)
        pulse_psi_i = pulse_psi.get("I", 0)

        # Get the image base64 data
        image_base64 = data.get("image", "")

        # 构建睡眠时间信息
        sleep_time_info = ""
        if start_sleep_time:
            sleep_time_info += f"\n- 睡眠开始时间: {start_sleep_time}"
        if sound_count > 0:
            sleep_time_info += f"\n- 检测到声音次数: {sound_count}"
        if snore_count > 0:
            sleep_time_info += f"\n- 检测到鼾声次数: {snore_count}"
        if snore_times:
            sleep_time_info += f"\n- 鼾声时间点: {', '.join(map(str, snore_times))}"

        # Construct the prompt for GPT-4o (更新后的prompt)
        prompt = f"""请仔细分析这张脉象波形图，这是一份来自中医体联脉象诊断系统的数据。

基本体征信息：
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}

睡眠PSI节律分析：
- 睡眠体力P值: {sleep_psi_p}
- 睡眠情绪S值: {sleep_psi_s}
- 睡眠智力I值: {sleep_psi_i}

傅里叶谐波分析数据：
- 基频: {base_frequency} Hz
- 整体振幅偏差: {overall_amplitude_deviation}%
- 整体相位偏差: {overall_phase_deviation}%
- 整体总偏差: {overall_total_deviation}%

脉象PSI节律分析：
- 脉象经络体力P值: {pulse_psi_p}
- 脉象经络情绪S值: {pulse_psi_s}
- 脉象经络智力I值: {pulse_psi_i}

详细谐波数据（前10阶）："""

        # Add harmonics data to prompt (更新格式)
        for harmonic in harmonics:
            order = harmonic.get("order", 0)
            frequency = harmonic.get("frequency", 0)
            amplitude_ratio = harmonic.get("amplitude_ratio", 0)
            phase = harmonic.get("phase", 0)
            amplitude_deviation = harmonic.get("amplitude_deviation", 0)
            phase_deviation = harmonic.get("phase_deviation", 0)
            total_deviation = harmonic.get("total_deviation", 0)
            prompt += f"""
第{order}阶谐波:
- 频率: {frequency} Hz
- 归一化振幅: {amplitude_ratio}
- 相位: {phase} rad
- 振幅偏差: {amplitude_deviation}%
- 相位偏差: {phase_deviation}%
- 综合偏差: {total_deviation}%"""

        prompt += """

请作为一名专业的中医脉诊专家，结合PSI节律理论对图中的波形和上述数据进行深入解读：

【波形结构分析】
1. 分析波形的整体形态特征（平滑度、峰值特点、谷值特点）
2. 确定波形类型（弦、滑、洪、细等传统脉象类型）
3. 分析波形的规律性和周期性变化

【PSI节律分析要求】
1. P体力节律：高潮期体力充沛、动作敏捷、抗病能力强；临界日抵抗力最低、极易受伤、慢性病复发危险期；低潮期身体乏力、易疲劳感染
2. S情绪节律：高潮期心情愉快、创造力强、人际和谐；临界日情绪极不稳定、易怒冲动、事故自杀高发期；低潮期情绪低落、意志消沉、缺乏信心
3. I智力节律：高潮期思维敏捷、记忆力强、判断准确、效率最高；临界日判断力差、严重健忘、极易出错；低潮期思维迟钝、理解缓慢、效率不高
4. 【核心规律】：三节律呈正弦波变化，临界日为各类事故、疾病、失误的最危险转换期
5. 结合睡眠PSI和脉象PSI的差异，分析睡眠质量与经络气血运行的关系

【谐波特征解读】
1. 基于谐波数据，分析波形的频域特性和基频稳定性
2. 解读各阶谐波的振幅、相位特征及其偏差意义
3. 评估整体偏差水平与中医脉象健康程度的关联性

【心率变异性分析】
1. 结合SDNN、RMSSD、NN50、PNN50等指标，评估自主神经系统功能
2. 分析心率变异性与中医气血调节、脏腑功能的关系
3. 评估疲劳程度、微循环状况对整体健康的影响

【中医辨证分析】
1. 根据波形特征和谐波数据，进行脏腑功能状态评估
2. 结合血氧饱和度、血压等客观指标，评估整体健康状况
3. 进行五行归类（木火土金水）和辨证（寒热虚实）分析
4. 分析睡眠质量对脏腑功能的影响

【养生保健建议】
1. 基于以上分析，提供针对性的养生保健建议
2. 根据PSI节律特点，给出适合的作息调理方法
3. 推荐改善心率变异性和睡眠质量的方法
4. 提供适合的饮食、运动和情志调节方式

请详细、专业、有条理地给出分析和建议，语言要温和鼓励但不失严谨。运用传统中医理论结合现代数据分析方法，提高诊断的准确度和实用性。"""

        # 构建第二个提示词：红蓝融合度评估 (更新数据)
        promptHLBase = f"""请仔细分析这张脉象波形图和相关数据，这份资料来自中医体联脉象诊断系统。

基本体征信息：
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}

PSI节律数据：
- 睡眠PSI: P={sleep_psi_p}, S={sleep_psi_s}, I={sleep_psi_i}
- 脉象PSI: P={pulse_psi_p}, S={pulse_psi_s}, I={pulse_psi_i}

谐波分析：基频{base_frequency}Hz，整体偏差{overall_total_deviation}%"""

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
                sid=scene_item.sid,
                writer=username
            )
            notebook.save()

        # 步骤3: 添加卡片
        # 构建卡片内容
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 构建包含体征信息和分析结果的内容 (更新格式)
        cardContent = f"""# 脉象分析记录（{time_str}）

## 基本体征信息
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}

## PSI节律分析
### 睡眠PSI节律
- 体力P值: {sleep_psi_p}
- 情绪S值: {sleep_psi_s}
- 智力I值: {sleep_psi_i}

### 脉象PSI节律
- 经络体力P值: {pulse_psi_p}
- 经络情绪S值: {pulse_psi_s}
- 经络智力I值: {pulse_psi_i}

## 谐波分析数据
- 基频: {base_frequency} Hz
- 整体振幅偏差: {overall_amplitude_deviation}%
- 整体相位偏差: {overall_phase_deviation}%
- 整体总偏差: {overall_total_deviation}%

### 详细谐波数据（前10阶）
"""
        # 添加谐波数据 (更新格式)
        for harmonic in harmonics:
            order = harmonic.get("order", 0)
            frequency = harmonic.get("frequency", 0)
            amplitude_ratio = harmonic.get("amplitude_ratio", 0)
            phase = harmonic.get("phase", 0)
            amplitude_deviation = harmonic.get("amplitude_deviation", 0)
            phase_deviation = harmonic.get("phase_deviation", 0)
            total_deviation = harmonic.get("total_deviation", 0)
            cardContent += f"""
第{order}阶谐波:
- 频率: {frequency} Hz
- 归一化振幅: {amplitude_ratio}
- 相位: {phase} rad
- 振幅偏差: {amplitude_deviation}%
- 相位偏差: {phase_deviation}%
- 综合偏差: {total_deviation}%
"""

        # 添加分析结果
        cardContent += f"""
## 专业分析结果
{content}
"""

        from app_chat.card_keyword_extract import extract_card_semantic_keywords
        keyWords = extract_card_semantic_keywords(
            cardContent,
            notebook_description="脉象分析五时流注表",
            with_candidates=False,
            username=username + "_Watch",
        )

        # 生成标题
        # system_prompt_title = (
        #     '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，'
        #     '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求'
        #     '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        # )
        # prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + cardContent
        # kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)
        # contentTitle = kimi_response_title.choices[0].message.content
        # 🔥 并行生成标题和关键词的DMT/四色分析（注意：这个函数没有sceneName，使用None）
        contentTitle, keyword_results = generate_title_and_analyze_keywords_parallel(
            keyWords, cardContent, username + "_Watch", username, None, None
        )

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


# ===== 修正：=====
# 1. 之前将BodyCardAnalysis拆成了PulseAnalysis和HLAnalysis两个分开的接口，分别调用且都改成了流式，都完成后，系统自动将数据进行保存。
# 现在需要调整流程，只需要调用PulseAnalysis流式接口，出结果后就直接将内容返回，并在后台开始对图文输入和此输出内容一并进行HLAnalysis
# （因为这里现在不需要调用，改为后台了，所以不需要流式，但流式写法继续用也无所谓）结束后再将数据进行保存，基于BodyCardAnalysis改造成BodyStreamAnalysis
# 2.现在可能不会传图过来，而是320个数据点

def generate_pulse_waveform_image(data_points):
    """
    根据数据点生成脉象波形图

    Args:
        data_points: 包含320个数据点的列表

    Returns:
        base64编码的图片字符串
    """
    try:
        # 设置中文字体
        plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
        plt.rcParams['axes.unicode_minus'] = False

        # 创建图形
        fig, ax = plt.subplots(figsize=(10, 4))

        # 生成时间轴（6.4秒，320个点）
        time_points = np.linspace(0, 6.4, len(data_points))

        # 绘制波形
        ax.plot(time_points, data_points, 'b-', linewidth=1.5)

        # 设置标签和标题
        ax.set_xlabel('Time (s)', fontsize=12)
        ax.set_ylabel('Amplitude', fontsize=12)

        # 计算频率（320个点/6.4秒 = 50Hz采样率）
        # 简单估算心率：计算波峰数量
        from scipy.signal import find_peaks
        peaks, _ = find_peaks(data_points, height=np.mean(data_points))
        heart_rate = len(peaks) * 60 / 6.4  # 转换为每分钟心率

        ax.set_title(f'Pulse Waveform ({heart_rate:.0f} bpm)', fontsize=14)

        # 设置网格
        ax.grid(True, alpha=0.3)

        # 设置坐标轴范围
        ax.set_xlim(0, 6.4)

        # 调整布局
        plt.tight_layout()

        # 保存到BytesIO对象
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
        buffer.seek(0)

        # 转换为base64
        image_base64 = base64.b64encode(buffer.read()).decode('utf-8')

        # 不添加data URL前缀，返回纯base64字符串
        # image_base64 = f"data:image/png;base64,{image_base64}"  # 删除这行

        # 清理
        plt.close(fig)
        buffer.close()

        return image_base64

    except Exception as e:
        print(f"生成脉象波形图时出错: {str(e)}")
        raise


def _esp32_block_timestamp():
    # 使用北京时间（UTC+8）生成文件名与块内时间戳
    beijing_tz = dt_timezone(timedelta(hours=8))
    now_bj = datetime.now(beijing_tz)
    file_ts = now_bj.strftime("%Y_%m_%d_%H_%M_%S")
    utc_ts = now_bj.strftime("%Y-%m-%dT%H:%M:%S+08:00")
    return file_ts, utc_ts


def _parse_esp32_block_time_override(raw):
    """
    解析测试/设备自定义块时间。成功返回 (file_ts, utc_ts)，与 _esp32_block_timestamp 格式一致。
    支持：
      - 文件名格式：2026_04_28_09_32_01（视为北京时间）
      - ISO：2026-04-28T09:32:01、2026-04-28 09:32:01（无时区则按北京时间；有时区则换算到上海）
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        from zoneinfo import ZoneInfo
        bj = ZoneInfo("Asia/Shanghai")
    except Exception:
        bj = dt_timezone(timedelta(hours=8))
    m = re.match(r"^(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})$", s)
    if m:
        y, mo, d, h, mi, se = m.groups()
        file_ts = f"{y}_{mo}_{d}_{h}_{mi}_{se}"
        utc_ts = f"{y}-{mo}-{d}T{h}:{mi}:{se}+08:00"
        return file_ts, utc_ts
    try:
        s2 = s
        if s2.endswith("Z"):
            s2 = s2[:-1] + "+00:00"
        if "T" not in s2 and len(s2) >= 16:
            s2 = s2.replace(" ", "T", 1)
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=bj)
        else:
            dt = dt.astimezone(bj)
        file_ts = dt.strftime("%Y_%m_%d_%H_%M_%S")
        utc_ts = dt.strftime("%Y-%m-%dT%H:%M:%S") + "+08:00"
        return file_ts, utc_ts
    except Exception:
        return None


def _esp32_bool_text(value):
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, (int, float)):
        return "True" if value != 0 else "False"
    if isinstance(value, str):
        lowered = value.strip().lower()
        return "True" if lowered in ("true", "1", "yes", "y") else "False"
    return "False"


def _flatten_esp32_extra_fields(data):
    known_top_keys = {
        "username", "user_profile", "audio_base64", "audio_ext", "pulse_uploaded",
        "image_uploaded", "symptoms", "body_data", "sleep_data", "harmonics_data",
        "has_image", "image", "session_id", "block_time", "client_block_time"
    }
    lines = []

    for key, value in data.items():
        if key in known_top_keys:
            continue
        lines.append(f"{key}: {value}")

    nested_groups = [
        ("body_data", data.get("body_data", {})),
        ("sleep_data", data.get("sleep_data", {})),
        ("harmonics_data", data.get("harmonics_data", {})),
    ]
    for group_name, group_value in nested_groups:
        if not isinstance(group_value, dict):
            continue
        for key, value in group_value.items():
            lines.append(f"{group_name}.{key}: {value}")
    return lines


def _format_esp32_group_sections(data):
    """按分组生成短期记忆文本，去掉前缀并避免重复字段。"""
    lines = []

    body_data = data.get("body_data", {}) if isinstance(data.get("body_data"), dict) else {}
    sleep_data = data.get("sleep_data", {}) if isinstance(data.get("sleep_data"), dict) else {}
    harmonics_data = data.get("harmonics_data", {}) if isinstance(data.get("harmonics_data"), dict) else {}

    # body_data 分组：去掉与主信息重复字段（仅保留去重后的P/S/I）
    body_exclude = {"P", "S", "I"}
    body_items = [(k, v) for k, v in body_data.items() if k not in body_exclude]
    if body_items:
        lines.append("=====")
        lines.append("body_data:")
        for k, v in body_items:
            lines.append(f"{k}: {v}")

    # sleep_data 分组：只保留核心字段，避免冗余
    sleep_keys = ["snore_count", "sound_count", "start_sleep_time", "snore_times"]
    sleep_items = [(k, sleep_data.get(k, "")) for k in sleep_keys if k in sleep_data]
    if sleep_items:
        lines.append("=====")
        lines.append("sleep_data:")
        for k, v in sleep_items:
            lines.append(f"{k}: {v}")

    # harmonics_data 分组：输出 base_frequency + harmonics 列表每个字段
    harmonics_list = harmonics_data.get("harmonics", [])
    harmonics_keys = [
        "base_frequency",
        "overall_amplitude_deviation",
        "overall_phase_deviation",
        "overall_total_deviation",
    ]
    harmonics_items = [(k, harmonics_data.get(k, "")) for k in harmonics_keys if k in harmonics_data]
    if harmonics_items or (isinstance(harmonics_list, list) and len(harmonics_list) > 0):
        lines.append("=====")
        lines.append("harmonics_data:")
        for k, v in harmonics_items:
            lines.append(f"{k}: {v}")

        if isinstance(harmonics_list, list) and len(harmonics_list) > 0:
            lines.append("harmonics:")
            for idx, item in enumerate(harmonics_list):
                if not isinstance(item, dict):
                    continue
                c_val = item.get("C", idx)
                lines.append(f"C{c_val}:")
                if "C_AVG" in item:
                    lines.append(f"C_AVG: {item.get('C_AVG', '')}")
                if "C_CV" in item:
                    lines.append(f"C_CV: {item.get('C_CV', '')}")
                if "deviation" in item:
                    lines.append(f"deviation: {item.get('deviation', '')}")

    return "\n".join(lines)


def _ensure_user_runtime_context(user_name):
    """确保用户在运行态内存和锁中已初始化，避免 KeyError。"""
    if user_name not in parse_input.lock:
        parse_input.lock[user_name] = threading.RLock()
    if user_name not in global_var.store_memory or "prompt" not in global_var.store_memory[user_name]:
        global_var.set_user_prompt(user_name)
    if "params" not in global_var.store_memory.get(user_name, {}):
        global_var.set_user_params(user_name)
    if "model_num" not in global_var.store_memory.get(user_name, {}):
        global_var.set_user_model(user_name, 0)


def _esp32_async_postprocess(notebook_userbook, real_name, files_to_mark_split, txt_files_to_index, pulse_image_uploaded, pulse_image_file_name):
    """
    ESP32上传后的后台后处理：更新split状态并建立索引。
    避免在HTTP请求线程内执行重操作导致ESP32 read timeout。
    """
    for f_name in files_to_mark_split:
        try:
            global_var.add_split_file(notebook_userbook, f_name)
        except Exception as e:
            print(f"[esp32_memory_upload][async] add_split_file 失败: {f_name}, {e}")

    for txt_name in txt_files_to_index:
        try:
            parse_input.get_split_docs_vectors(
                real_name,
                notebook_userbook,
                txt_name,
                task_id=f"esp32-{uuid.uuid4().hex[:8]}"
            )
        except Exception as e:
            print(f"[esp32_memory_upload][async] txt建索引失败: {txt_name}, {e}")

    if pulse_image_uploaded and pulse_image_file_name:
        try:
            parse_input.get_split_docs_vectors(
                real_name,
                notebook_userbook,
                pulse_image_file_name,
                task_id=f"esp32-img-{uuid.uuid4().hex[:8]}"
            )
        except Exception as e:
            print(f"[esp32_memory_upload][async] 脉象图建索引失败: {pulse_image_file_name}, {e}")


@csrf_exempt
def esp32_memory_upload(request):
    """
    ESP32健康数据上传接口：
    1) 保存音频到文档导入目录（user_raw_file/{username}）
    2) 生成/更新长期记忆块 {username}_LONG.txt
    3) 生成短期记忆块 {username}_{timestamp}.txt
    """
    try:
        data = json.loads(request.body)
        username = data.get("username")
        if not username:
            return JsonResponse({"status": "fail", "error_msg": "缺少username"}, status=400)

        override_ts = data.get("block_time") or data.get("client_block_time")
        parsed_ts = _parse_esp32_block_time_override(override_ts)
        block_time_client_override_applied = False
        if parsed_ts:
            file_ts, utc_ts = parsed_ts
            block_time_client_override_applied = True
            print(f"[esp32_memory_upload] 使用客户端 block_time: {file_ts} (raw={override_ts!r})")
        else:
            if override_ts:
                return JsonResponse({
                    "status": "fail",
                    "error_msg": "block_time/client_block_time 格式无效，请使用 2026_04_28_09_32_01 或 ISO 日期时间",
                }, status=400)
            file_ts, utc_ts = _esp32_block_timestamp()
        notebook_userbook = "ta_testNotebook"
        real_name = notebook_userbook.split('_')[0]
        _ensure_user_runtime_context(notebook_userbook)
        user_dir = "./received_dir/user_raw_file/ta_testNotebook"
        os.makedirs(user_dir, exist_ok=True)

        user_profile = data.get("user_profile", {}) if isinstance(data.get("user_profile"), dict) else {}
        gender = user_profile.get("gender", "")
        age = user_profile.get("age", "")
        height = user_profile.get("height", "")
        weight = user_profile.get("weight", "")
        birth_time = user_profile.get("birth_time", "")
        birth_place = user_profile.get("birth_place", "")
        location = user_profile.get("location", "")
        medical_history = user_profile.get("medical_history", "")
        family_history = user_profile.get("family_history", "")

        # 1) 保存音频文件
        audio_uploaded = False
        audio_file_name = ""
        audio_base64 = data.get("audio_base64", "")
        if isinstance(audio_base64, str) and audio_base64:
            try:
                if "," in audio_base64:
                    audio_base64 = audio_base64.split(",", 1)[1]
                audio_bytes = base64.b64decode(audio_base64)
                if audio_bytes:
                    ext = str(data.get("audio_ext", "wav")).strip().lower() or "wav"
                    if ext not in {"wav", "mp3", "pcm"}:
                        ext = "wav"
                    audio_file_name = f"{username}_{file_ts}.{ext}"
                    audio_path = os.path.join(user_dir, audio_file_name)
                    with open(audio_path, "wb") as f:
                        f.write(audio_bytes)
                    audio_uploaded = True
            except Exception as decode_err:
                print(f"[esp32_memory_upload] 音频解码失败: {decode_err}")

        # 1.1) has_image=0 时，根据 data points 生成脉象图并保存到文档导入区
        pulse_image_uploaded = False
        pulse_image_file_name = ""
        has_image = data.get("has_image", 1)
        if has_image == 0:
            data_points = data.get("image", [])
            if not isinstance(data_points, list) or len(data_points) != 320:
                return JsonResponse({
                    "status": "fail",
                    "error_msg": f"数据点数量不正确，期望320个点，实际收到{len(data_points) if isinstance(data_points, list) else 0}个点"
                }, status=400)
            try:
                pulse_image_base64 = generate_pulse_waveform_image(data_points)
                pulse_image_bytes = base64.b64decode(pulse_image_base64)
                pulse_image_file_name = f"{username}_{file_ts}.png"
                pulse_image_path = os.path.join(user_dir, pulse_image_file_name)
                with open(pulse_image_path, "wb") as f:
                    f.write(pulse_image_bytes)
                pulse_image_uploaded = True
            except Exception as e:
                print(f"[esp32_memory_upload] 生成脉象图失败: {e}")

        # 2) 长期记忆块（每次覆盖写入，确保字段不会因首次上报为空而长期空白）
        long_block_name = f"{username}_LONG.txt"
        long_block_path = os.path.join(user_dir, long_block_name)
        long_block_content = (
            "[BLOCK_HEADER]\n"
            f"Block_ID: {username}_LONG\n"
            "Prev_Hash: NULL\n"
            f"Timestamp_UTC: {utc_ts}\n\n"
            "[BLOCK_BODY]\n"
            f"UserId: {username}\n"
            f"Gender: {gender}\n"
            f"Age: {age}\n"
            f"Height: {height}\n"
            f"Weight: {weight}\n"
            f"Birth_Time: {birth_time}\n"
            f"Birth_Place: {birth_place}\n"
            f"Location: {location}\n"
            f"Medical_History: {medical_history}\n"
            f"Family_History: {family_history}\n"
        )
        with open(long_block_path, "w", encoding="utf-8") as f:
            f.write(long_block_content)

        # 3) 短期记忆块
        short_block_id = f"{username}_{file_ts}"
        short_block_name = f"{short_block_id}.txt"
        short_block_path = os.path.join(user_dir, short_block_name)

        body_data = data.get("body_data", {}) if isinstance(data.get("body_data"), dict) else {}
        psi_p = body_data.get("P", 0)
        psi_s = body_data.get("S", 0)
        psi_i = body_data.get("I", 0)
        symptoms = data.get("symptoms", "")
        if isinstance(symptoms, list):
            symptoms = ",".join([str(item) for item in symptoms])

        pulse_uploaded = data.get("pulse_uploaded", data.get("image_uploaded", pulse_image_uploaded))
        pulse_uploaded_text = _esp32_bool_text(pulse_uploaded)
        audio_uploaded_text = "True" if audio_uploaded else "False"

        grouped_text = _format_esp32_group_sections(data)
        if grouped_text:
            grouped_text = "\n" + grouped_text

        short_block_content = (
            "[BLOCK_HEADER]\n"
            f"Block_ID: {short_block_id}\n"
            f"Prev_Hash: {username}_LONG\n"
            f"Timestamp_UTC: {utc_ts}\n\n"
            "[BLOCK_BODY]\n"
            f"PSI: {psi_p}, {psi_s}, {psi_i}\n"
            f"Audio: {audio_uploaded_text}\n"
            f"Pulse: {pulse_uploaded_text}\n"
            f"Symptoms: {symptoms}"
            f"{grouped_text}\n"
        )

        with open(short_block_path, "w", encoding="utf-8") as f:
            f.write(short_block_content)

        # 4) 与普通上传流程保持一致：更新 split 状态并为 txt 建立分片/索引
        #    改为后台异步执行，避免阻塞HTTP响应导致ESP32侧read timeout
        files_to_mark_split = [long_block_name, short_block_name]
        if audio_uploaded and audio_file_name:
            files_to_mark_split.append(audio_file_name)
        if pulse_image_uploaded and pulse_image_file_name:
            files_to_mark_split.append(pulse_image_file_name)

        txt_files_to_index = [long_block_name, short_block_name]
        threading.Thread(
            target=_esp32_async_postprocess,
            args=(
                notebook_userbook,
                real_name,
                files_to_mark_split,
                txt_files_to_index,
                pulse_image_uploaded,
                pulse_image_file_name,
            ),
            daemon=True
        ).start()

        return JsonResponse({
            "status": "ok",
            "username": username,
            "audio_uploaded": audio_uploaded,
            "audio_filename": audio_file_name,
            "pulse_image_uploaded": pulse_image_uploaded,
            "pulse_image_filename": pulse_image_file_name,
            "long_block": long_block_name,
            "short_block": short_block_name,
            "postprocess_async": True,
            # 便于确认文件名时间戳是否来自客户端 block_time（需重启 runserver 后生效）
            "block_timestamp": file_ts,
            "timestamp_utc_line": utc_ts,
            "block_time_client_override_applied": block_time_client_override_applied,
        })
    except Exception as e:
        return JsonResponse({"status": "fail", "error_msg": str(e)}, status=500)


@csrf_exempt
def BodyStreamAnalysis(request):
    """合并的流式接口：脉象诊断分析（流式响应）+ 后台红蓝分析和保存"""
    try:
        data = json.loads(request.body)
        username = data["username"]
        session_id = data.get("session_id") or str(uuid.uuid4())

        # 检查是否有图片或需要生成图片
        has_image = data.get("has_image", 1)  # 默认为1（有图片）

        if has_image == 0:
            # 需要根据数据点生成图片
            data_points = data.get("image", [])
            if not data_points or len(data_points) != 320:
                return JsonResponse({
                    'status': 'fail',
                    'error_msg': f'数据点数量不正确，期望320个点，实际收到{len(data_points)}个点'
                }, status=400)

            print(f"根据{len(data_points)}个数据点生成脉象波形图...")
            image_base64 = generate_pulse_waveform_image(data_points)
            print("脉象波形图生成完成")

            # 将生成的图片保存到data中，供后续使用
            data["generated_image"] = image_base64

        else:
            # 直接使用传入的图片
            image_base64 = data.get("image", "")
            if not image_base64:
                return JsonResponse({
                    'status': 'fail',
                    'error_msg': '缺少图片数据'
                }, status=400)

        # 提取所有需要的数据（保持原有逻辑）
        body_data = data.get("body_data", {})
        hr = body_data.get("hr", 0)
        spo2 = body_data.get("spo2", 0)
        microcirculation = body_data.get("microcirculation", 0)
        fatigue = body_data.get("fatigue", 0)
        bp = body_data.get("bp", "0/0")
        sdnn = body_data.get("sdnn", 0)
        rmssd = body_data.get("rmssd", 0)
        nn50 = body_data.get("nn50", 0)
        pnn50 = body_data.get("pnn50", 0)

        # 五时PSI + 经时穴时（testble当前JSON格式）
        five_time_rule = body_data.get("five_time_rule", "NA")
        age_factor = body_data.get("age_factor", 0)
        age_years = body_data.get("age_years", 0)
        raw_days = body_data.get("raw_days", 0)
        corrected_days = body_data.get("corrected_days", 0)
        perceived_minute = body_data.get("perceived_minute", 0)
        perceived_day_ganzhi = body_data.get("perceived_day_ganzhi", "NA")
        perceived_hour_ganzhi = body_data.get("perceived_hour_ganzhi", "NA")

        p_five = body_data.get("P_five", body_data.get("P_precise", body_data.get("P", 0)))
        s_five = body_data.get("S_five", body_data.get("S_precise", body_data.get("S", 0)))
        i_five = body_data.get("I_five", body_data.get("I_precise", body_data.get("I", 0)))
        p_raw = body_data.get("P_raw", body_data.get("P", 0))
        s_raw = body_data.get("S_raw", body_data.get("S", 0))
        i_raw = body_data.get("I_raw", body_data.get("I", 0))
        p_precise = body_data.get("P_precise", p_five)
        s_precise = body_data.get("S_precise", s_five)
        i_precise = body_data.get("I_precise", i_five)

        jing_time = body_data.get("jing_time", "NA")
        xue_time = body_data.get("xue_time", "NA")
        xue_guest = body_data.get("xue_guest", "")
        xue_yuan = body_data.get("xue_yuan", "")
        jingxue_wushu = body_data.get("jingxue_wushu", "NA")
        jingxue_open_state = body_data.get("jingxue_open_state", "NA")
        jingxue_hit_state = body_data.get("jingxue_hit_state", "NA")

        sleep_data = data.get("sleep_data", {})
        start_sleep_time = sleep_data.get("start_sleep_time", "")
        sound_count = sleep_data.get("sound_count", 0)
        snore_count = sleep_data.get("snore_count", 0)
        snore_times = sleep_data.get("snore_times", [])
        snore_detected = sleep_data.get("snore_detected", 0)      # 测量前是否已检测到鼾声
        pressure_raw_max = sleep_data.get("pressure_raw_max", 0)  # FSR AO raw 最大值
        deep_sleep = sleep_data.get("deep_sleep", 0)              # 是否进入深睡（pressure_raw > 800）
        # 兼容旧格式 sleep_data.psi；新格式直接使用body_data里的五时PSI
        sleep_psi = sleep_data.get("psi", {})
        sleep_psi_p = sleep_psi.get("P", p_five)
        sleep_psi_s = sleep_psi.get("S", s_five)
        sleep_psi_i = sleep_psi.get("I", i_five)

        harmonics_data = data.get("harmonics_data", {})
        base_frequency = harmonics_data.get("base_frequency", 0)
        harmonics = harmonics_data.get("harmonics", [])
        overall_amplitude_deviation = harmonics_data.get("overall_amplitude_deviation", 0)
        overall_phase_deviation = harmonics_data.get("overall_phase_deviation", 0)
        overall_total_deviation = harmonics_data.get("overall_total_deviation", 0)
        pulse_psi = harmonics_data.get("pulse_psi", {})
        pulse_psi_p = pulse_psi.get("P", 0)
        pulse_psi_s = pulse_psi.get("S", 0)
        pulse_psi_i = pulse_psi.get("I", 0)

        # 构建睡眠时间信息
        sleep_time_info = ""
        if start_sleep_time:
            sleep_time_info += f"\n- 睡眠开始时间: {start_sleep_time}"
        if sound_count > 0:
            sleep_time_info += f"\n- 检测到声音次数: {sound_count}"
        if snore_count > 0:
            sleep_time_info += f"\n- 检测到鼾声次数: {snore_count}"
        if snore_times:
            sleep_time_info += f"\n- 鼾声时间点: {', '.join(map(str, snore_times))}"

        if snore_detected:
            sleep_time_info += f"\n- 测量前已检测到鼾声: 是"
        if pressure_raw_max > 0:
            sleep_time_info += f"\n- 压力传感器最大原始值: {pressure_raw_max}"
        if deep_sleep:
            sleep_time_info += f"\n- 深睡状态: 是（压力值曾超过800阈值）"
        else:
            sleep_time_info += f"\n- 深睡状态: 否（全程浅睡）"

        five_time_info = f"""

五时PSI与经时穴时：
- 当前规则: {five_time_rule}
- 年龄: {age_years} 岁
- 年龄倍率: {age_factor}
- 原始天数: {raw_days}
- 五时修正天数: {corrected_days}
- 感知分钟: {perceived_minute}
- 感知日干支: {perceived_day_ganzhi}
- 感知时干支: {perceived_hour_ganzhi}
- 原始PSI: P={p_raw}, S={s_raw}, I={i_raw}
- V4精细PSI: P={p_precise}, S={s_precise}, I={i_precise}
- 五时PSI: P={p_five}, S={s_five}, I={i_five}
- 经时归经: {jing_time}
- 主穴: {xue_time}
- 客穴: {xue_guest if xue_guest else "无"}
- 原穴: {xue_yuan if xue_yuan else "无"}
- 五输状态: {jingxue_wushu}
- 开闭状态: {jingxue_open_state}
- 命中状态: {jingxue_hit_state}"""

        # 构建脉象分析prompt（保持原有逻辑）
        prompt_pulse = f"""请仔细分析这张脉象波形图，这是一份来自中医体联脉象诊断系统的数据。

基本体征信息：
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}{five_time_info}

睡眠PSI节律分析：
- 睡眠体力P值: {sleep_psi_p}
- 睡眠情绪S值: {sleep_psi_s}
- 睡眠智力I值: {sleep_psi_i}

五时精准PSI节律分析：
- 五时体力P值: {p_five}
- 五时情绪S值: {s_five}
- 五时智力I值: {i_five}
- 说明: 五时PSI保留23/28/33天节律周期和正弦振幅，主要通过年龄倍率与感知时间修正相位落点。

傅里叶谐波分析数据：
- 基频: {base_frequency} Hz
- 整体振幅偏差: {overall_amplitude_deviation}%
- 整体相位偏差: {overall_phase_deviation}%
- 整体总偏差: {overall_total_deviation}%

脉象PSI节律分析：
- 脉象经络体力P值: {pulse_psi_p}
- 脉象经络情绪S值: {pulse_psi_s}
- 脉象经络智力I值: {pulse_psi_i}

详细谐波数据（前10阶）："""

        for harmonic in harmonics:
            # 兼容旧格式(order/frequency/amplitude_ratio...)与当前testble格式(C/C_AVG/C_CV/deviation)
            order = harmonic.get("order", harmonic.get("C", 0))
            frequency = harmonic.get("frequency", 0)
            amplitude_ratio = harmonic.get("amplitude_ratio", harmonic.get("C_AVG", 0))
            phase = harmonic.get("phase", 0)
            amplitude_deviation = harmonic.get("amplitude_deviation", harmonic.get("deviation", 0))
            phase_deviation = harmonic.get("phase_deviation", 0)
            total_deviation = harmonic.get("total_deviation", 0)
            c_cv = harmonic.get("C_CV", 0)
            prompt_pulse += f"""
第{order}阶谐波:
- 频率: {frequency} Hz
- 归一化振幅: {amplitude_ratio}
- 变异系数C_CV: {c_cv}
- 相位: {phase} rad
- 振幅偏差: {amplitude_deviation}%
- 相位偏差: {phase_deviation}%
- 综合偏差: {total_deviation}%"""

        prompt_pulse += """

请作为一名专业的中医脉诊专家，结合PSI节律理论对图中的波形和上述数据进行深入解读：

【波形结构分析】
1. 分析波形的整体形态特征（平滑度、峰值特点、谷值特点）
2. 确定波形类型（弦、滑、洪、细等传统脉象类型）
3. 分析波形的规律性和周期性变化

【PSI节律分析要求】
1. P体力节律：高潮期体力充沛、动作敏捷、抗病能力强；临界日抵抗力最低、极易受伤、慢性病复发危险期；低潮期身体乏力、易疲劳感染
2. S情绪节律：高潮期心情愉快、创造力强、人际和谐；临界日情绪极不稳定、易怒冲动、事故自杀高发期；低潮期情绪低落、意志消沉、缺乏信心
3. I智力节律：高潮期思维敏捷、记忆力强、判断准确、效率最高；临界日判断力差、严重健忘、极易出错；低潮期思维迟钝、理解缓慢、效率不高
4. 【核心规律】：三节律呈正弦波变化，临界日为各类事故、疾病、失误的最危险转换期
5. 结合睡眠PSI和脉象PSI的差异，分析睡眠质量与经络气血运行的关系
6. 结合五时PSI（P_five/S_five/I_five）说明当前体力、情绪、智力状态；注意五时PSI主要改变相位落点，不改变原始周期和振幅

【谐波特征解读】
1. 基于谐波数据，分析波形的频域特性和基频稳定性
2. 解读各阶谐波的振幅、相位特征及其偏差意义
3. 评估整体偏差水平与中医脉象健康程度的关联性

【心率变异性分析】
1. 结合SDNN、RMSSD、NN50、PNN50等指标，评估自主神经系统功能
2. 分析心率变异性与中医气血调节、脏腑功能的关系
3. 评估疲劳程度、微循环状况对整体健康的影响

【中医辨证分析】
1. 根据波形特征和谐波数据，进行脏腑功能状态评估
2. 结合血氧饱和度、血压等客观指标，评估整体健康状况
3. 进行五行归类（木火土金水）和辨证（寒热虚实）分析
4. 分析睡眠质量对脏腑功能的影响

【经时穴时与穴位建议】
1. 结合当前经时归经（{jing_time}）、主穴（{xue_time}）、客穴（{xue_guest if xue_guest else "无"}）、原穴（{xue_yuan if xue_yuan else "无"}）、五输状态（{jingxue_wushu}）进行解释
2. 如果主穴有效且命中状态为“命中”，给出围绕主穴的温和按摩建议：按揉位置、建议时长、力度、频次和适用人群
3. 如存在客穴或原穴，说明其在调和表里、补泻平衡、稳定经气中的辅助意义
4. 如未命中或闭穴，应避免强行刺激，改为轻柔按揉相关经络循行区域、热敷或放松拉伸
5. 穴位建议必须是保健辅助，不替代医疗诊断；孕期、皮肤破损、急性疼痛、严重基础病者需谨慎或咨询医生

【养生保健建议】
1. 基于以上分析，提供针对性的养生保健建议
2. 根据PSI节律特点，给出适合的作息调理方法
3. 推荐改善心率变异性和睡眠质量的方法
4. 提供适合的饮食、运动和情志调节方式

【睡眠环境与寝具建议】
1. 结合鼾声次数、声音次数、压力传感器最大值、深睡状态、HRV和五时PSI，判断睡眠风险和恢复质量
2. 对鼾声、浅睡、疲劳或血氧偏低情况，给出可执行的睡眠环境建议：通风换气、侧卧、抬高枕头、保持鼻腔通畅、控制睡前饮酒和晚餐时间
3. 可根据情况建议使用香薰机、加湿器、空气净化器、氧气机或制氧设备、止鼾枕/合适高度枕头、透气床垫、遮光窗帘、白噪音等；但需说明氧气机/制氧设备应优先用于血氧偏低或医生建议场景，不能替代睡眠呼吸暂停的医学评估
4. 针对深睡不足或压力值长期偏低，给出寝具与睡姿建议；针对压力过高或频繁翻身，给出床垫软硬、枕头高度、睡前放松的建议

请详细、专业、有条理地给出分析和建议，语言要温和鼓励但不失严谨。运用传统中医理论结合现代数据分析方法，提高诊断的准确度和实用性。"""

        def stream_generator():
            """流式生成器函数"""
            try:
                # 调用GPT API获取流式响应
                pulse_content = ""
                for chunk in gpt4_api.make_gpt4o_image_text_requests_stream(
                    prompt_pulse, image_base64, use_fixed_params=True
                ):
                    pulse_content += chunk
                    yield f"data: {json.dumps({'chunk': chunk, 'session_id': session_id})}\n\n"

                # 脉象分析完成，发送完成信号
                yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

                # 启动后台线程进行红蓝分析和数据保存
                thread = threading.Thread(
                    target=background_hl_analysis_and_save,
                    args=(username, data, pulse_content, image_base64, session_id, has_image)
                )
                thread.daemon = True
                thread.start()

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        response = StreamingHttpResponse(stream_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    except Exception as e:
        return JsonResponse({'status': 'fail', 'error_msg': str(e)}, status=500)


# @csrf_exempt
# def BodyStreamAnalysis(request):
#     """合并的流式接口：脉象诊断分析（流式响应）+ 后台红蓝分析和保存"""
#     try:
#         data = json.loads(request.body)
#         username = data["username"]
#         session_id = data.get("session_id") or str(uuid.uuid4())

#         # 检查是否有图片或需要生成图片
#         has_image = data.get("has_image", 1)  # 默认为1（有图片）

#         if has_image == 0:
#             # 需要根据数据点生成图片
#             data_points = data.get("image", [])
#             if not data_points or len(data_points) != 320:
#                 return JsonResponse({
#                     'status': 'fail',
#                     'error_msg': f'数据点数量不正确，期望320个点，实际收到{len(data_points)}个点'
#                 }, status=400)

#             print(f"根据{len(data_points)}个数据点生成脉象波形图...")
#             image_base64 = generate_pulse_waveform_image(data_points)
#             print("脉象波形图生成完成")

#             # 将生成的图片保存到data中，供后续使用
#             data["generated_image"] = image_base64

#         else:
#             # 直接使用传入的图片
#             image_base64 = data.get("image", "")
#             if not image_base64:
#                 return JsonResponse({
#                     'status': 'fail',
#                     'error_msg': '缺少图片数据'
#                 }, status=400)

#         # 提取所有需要的数据（保持原有逻辑）
#         body_data = data.get("body_data", {})
#         hr = body_data.get("hr", 0)
#         spo2 = body_data.get("spo2", 0)
#         microcirculation = body_data.get("microcirculation", 0)
#         fatigue = body_data.get("fatigue", 0)
#         bp = body_data.get("bp", "0/0")
#         sdnn = body_data.get("sdnn", 0)
#         rmssd = body_data.get("rmssd", 0)
#         nn50 = body_data.get("nn50", 0)
#         pnn50 = body_data.get("pnn50", 0)

#         sleep_data = data.get("sleep_data", {})
#         start_sleep_time = sleep_data.get("start_sleep_time", "")
#         sound_count = sleep_data.get("sound_count", 0)
#         snore_count = sleep_data.get("snore_count", 0)
#         snore_times = sleep_data.get("snore_times", [])
#         snore_detected = sleep_data.get("snore_detected", 0)      # 测量前是否已检测到鼾声
#         pressure_raw_max = sleep_data.get("pressure_raw_max", 0)  # FSR AO raw 最大值
#         deep_sleep = sleep_data.get("deep_sleep", 0)              # 是否进入深睡（pressure_raw > 800）
#         sleep_psi = sleep_data.get("psi", {})
#         sleep_psi_p = sleep_psi.get("P", 0)
#         sleep_psi_s = sleep_psi.get("S", 0)
#         sleep_psi_i = sleep_psi.get("I", 0)

#         harmonics_data = data.get("harmonics_data", {})
#         base_frequency = harmonics_data.get("base_frequency", 0)
#         harmonics = harmonics_data.get("harmonics", [])
#         overall_amplitude_deviation = harmonics_data.get("overall_amplitude_deviation", 0)
#         overall_phase_deviation = harmonics_data.get("overall_phase_deviation", 0)
#         overall_total_deviation = harmonics_data.get("overall_total_deviation", 0)
#         pulse_psi = harmonics_data.get("pulse_psi", {})
#         pulse_psi_p = pulse_psi.get("P", 0)
#         pulse_psi_s = pulse_psi.get("S", 0)
#         pulse_psi_i = pulse_psi.get("I", 0)

#         # 构建睡眠时间信息
#         sleep_time_info = ""
#         if start_sleep_time:
#             sleep_time_info += f"\n- 睡眠开始时间: {start_sleep_time}"
#         if sound_count > 0:
#             sleep_time_info += f"\n- 检测到声音次数: {sound_count}"
#         if snore_count > 0:
#             sleep_time_info += f"\n- 检测到鼾声次数: {snore_count}"
#         if snore_times:
#             sleep_time_info += f"\n- 鼾声时间点: {', '.join(map(str, snore_times))}"

#         if snore_detected:
#             sleep_time_info += f"\n- 测量前已检测到鼾声: 是"
#         if pressure_raw_max > 0:
#             sleep_time_info += f"\n- 压力传感器最大原始值: {pressure_raw_max}"
#         if deep_sleep:
#             sleep_time_info += f"\n- 深睡状态: 是（压力值曾超过800阈值）"
#         else:
#             sleep_time_info += f"\n- 深睡状态: 否（全程浅睡）"

#         # 构建脉象分析prompt（保持原有逻辑）
#         prompt_pulse = f"""请仔细分析这张脉象波形图，这是一份来自中医体联脉象诊断系统的数据。

# 基本体征信息：
# - 心率: {hr} 次/分钟
# - 血氧饱和度: {spo2}%
# - 微循环指数: {microcirculation}
# - 疲劳程度指数: {fatigue}
# - 血压: {bp} mmHg
# - 心率变异性SDNN: {sdnn} ms
# - 心率变异性RMSSD: {rmssd} ms
# - NN50计数: {nn50}
# - PNN50占比: {pnn50}%{sleep_time_info}

# 睡眠PSI节律分析：
# - 睡眠体力P值: {sleep_psi_p}
# - 睡眠情绪S值: {sleep_psi_s}
# - 睡眠智力I值: {sleep_psi_i}

# 傅里叶谐波分析数据：
# - 基频: {base_frequency} Hz
# - 整体振幅偏差: {overall_amplitude_deviation}%
# - 整体相位偏差: {overall_phase_deviation}%
# - 整体总偏差: {overall_total_deviation}%

# 脉象PSI节律分析：
# - 脉象经络体力P值: {pulse_psi_p}
# - 脉象经络情绪S值: {pulse_psi_s}
# - 脉象经络智力I值: {pulse_psi_i}

# 详细谐波数据（前10阶）："""

#         for harmonic in harmonics:
#             order = harmonic.get("order", 0)
#             frequency = harmonic.get("frequency", 0)
#             amplitude_ratio = harmonic.get("amplitude_ratio", 0)
#             phase = harmonic.get("phase", 0)
#             amplitude_deviation = harmonic.get("amplitude_deviation", 0)
#             phase_deviation = harmonic.get("phase_deviation", 0)
#             total_deviation = harmonic.get("total_deviation", 0)
#             prompt_pulse += f"""
# 第{order}阶谐波:
# - 频率: {frequency} Hz
# - 归一化振幅: {amplitude_ratio}
# - 相位: {phase} rad
# - 振幅偏差: {amplitude_deviation}%
# - 相位偏差: {phase_deviation}%
# - 综合偏差: {total_deviation}%"""

#         prompt_pulse += """

# 请作为一名专业的中医脉诊专家，结合PSI节律理论对图中的波形和上述数据进行深入解读：

# 【波形结构分析】
# 1. 分析波形的整体形态特征（平滑度、峰值特点、谷值特点）
# 2. 确定波形类型（弦、滑、洪、细等传统脉象类型）
# 3. 分析波形的规律性和周期性变化

# 【PSI节律分析要求】
# 1. P体力节律：高潮期体力充沛、动作敏捷、抗病能力强；临界日抵抗力最低、极易受伤、慢性病复发危险期；低潮期身体乏力、易疲劳感染
# 2. S情绪节律：高潮期心情愉快、创造力强、人际和谐；临界日情绪极不稳定、易怒冲动、事故自杀高发期；低潮期情绪低落、意志消沉、缺乏信心
# 3. I智力节律：高潮期思维敏捷、记忆力强、判断准确、效率最高；临界日判断力差、严重健忘、极易出错；低潮期思维迟钝、理解缓慢、效率不高
# 4. 【核心规律】：三节律呈正弦波变化，临界日为各类事故、疾病、失误的最危险转换期
# 5. 结合睡眠PSI和脉象PSI的差异，分析睡眠质量与经络气血运行的关系

# 【谐波特征解读】
# 1. 基于谐波数据，分析波形的频域特性和基频稳定性
# 2. 解读各阶谐波的振幅、相位特征及其偏差意义
# 3. 评估整体偏差水平与中医脉象健康程度的关联性

# 【心率变异性分析】
# 1. 结合SDNN、RMSSD、NN50、PNN50等指标，评估自主神经系统功能
# 2. 分析心率变异性与中医气血调节、脏腑功能的关系
# 3. 评估疲劳程度、微循环状况对整体健康的影响

# 【中医辨证分析】
# 1. 根据波形特征和谐波数据，进行脏腑功能状态评估
# 2. 结合血氧饱和度、血压等客观指标，评估整体健康状况
# 3. 进行五行归类（木火土金水）和辨证（寒热虚实）分析
# 4. 分析睡眠质量对脏腑功能的影响

# 【养生保健建议】
# 1. 基于以上分析，提供针对性的养生保健建议
# 2. 根据PSI节律特点，给出适合的作息调理方法
# 3. 推荐改善心率变异性和睡眠质量的方法
# 4. 提供适合的饮食、运动和情志调节方式

# 请详细、专业、有条理地给出分析和建议，语言要温和鼓励但不失严谨。运用传统中医理论结合现代数据分析方法，提高诊断的准确度和实用性。"""

#         def stream_generator():
#             """流式生成器函数"""
#             try:
#                 # 调用GPT API获取流式响应
#                 pulse_content = ""
#                 for chunk in gpt4_api.make_gpt4o_image_text_requests_stream(
#                     prompt_pulse, image_base64, use_fixed_params=True
#                 ):
#                     pulse_content += chunk
#                     yield f"data: {json.dumps({'chunk': chunk, 'session_id': session_id})}\n\n"

#                 # 脉象分析完成，发送完成信号
#                 yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"

#                 # 启动后台线程进行红蓝分析和数据保存
#                 thread = threading.Thread(
#                     target=background_hl_analysis_and_save,
#                     args=(username, data, pulse_content, image_base64, session_id, has_image)
#                 )
#                 thread.daemon = True
#                 thread.start()

#             except Exception as e:
#                 yield f"data: {json.dumps({'error': str(e)})}\n\n"

#         response = StreamingHttpResponse(stream_generator(), content_type='text/event-stream')
#         response['Cache-Control'] = 'no-cache'
#         response['X-Accel-Buffering'] = 'no'
#         response['Access-Control-Allow-Origin'] = '*'
#         response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
#         response['Access-Control-Allow-Headers'] = 'Content-Type'
#         return response

#     except Exception as e:
#         return JsonResponse({'status': 'fail', 'error_msg': str(e)}, status=500)


def background_hl_analysis_and_save(username, data, pulse_content, image_base64, session_id, has_image):
    """后台执行红蓝分析并保存所有数据"""
    try:
        print(f"开始后台处理 - Session: {session_id}")

        # 如果是生成的图片，使用生成的版本
        if has_image == 0 and "generated_image" in data:
            image_base64 = data["generated_image"]

        # 提取数据用于红蓝分析（保持原有逻辑）
        body_data = data.get("body_data", {})
        hr = body_data.get("hr", 0)
        spo2 = body_data.get("spo2", 0)
        microcirculation = body_data.get("microcirculation", 0)
        fatigue = body_data.get("fatigue", 0)
        bp = body_data.get("bp", "0/0")
        sdnn = body_data.get("sdnn", 0)
        rmssd = body_data.get("rmssd", 0)
        nn50 = body_data.get("nn50", 0)
        pnn50 = body_data.get("pnn50", 0)

        sleep_data = data.get("sleep_data", {})
        start_sleep_time = sleep_data.get("start_sleep_time", "")
        sound_count = sleep_data.get("sound_count", 0)
        snore_count = sleep_data.get("snore_count", 0)
        snore_times = sleep_data.get("snore_times", [])
        sleep_psi = sleep_data.get("psi", {})
        sleep_psi_p = sleep_psi.get("P", 0)
        sleep_psi_s = sleep_psi.get("S", 0)
        sleep_psi_i = sleep_psi.get("I", 0)

        harmonics_data = data.get("harmonics_data", {})
        base_frequency = harmonics_data.get("base_frequency", 0)
        harmonics = harmonics_data.get("harmonics", [])
        overall_amplitude_deviation = harmonics_data.get("overall_amplitude_deviation", 0)
        overall_phase_deviation = harmonics_data.get("overall_phase_deviation", 0)
        overall_total_deviation = harmonics_data.get("overall_total_deviation", 0)
        pulse_psi = harmonics_data.get("pulse_psi", {})
        pulse_psi_p = pulse_psi.get("P", 0)
        pulse_psi_s = pulse_psi.get("S", 0)
        pulse_psi_i = pulse_psi.get("I", 0)

        # 构建睡眠时间信息
        sleep_time_info = ""
        if start_sleep_time:
            sleep_time_info += f"\n- 睡眠开始时间: {start_sleep_time}"
        if sound_count > 0:
            sleep_time_info += f"\n- 检测到声音次数: {sound_count}"
        if snore_count > 0:
            sleep_time_info += f"\n- 检测到鼾声次数: {snore_count}"
        if snore_times:
            sleep_time_info += f"\n- 鼾声时间点: {', '.join(map(str, snore_times))}"

        # 构建红蓝分析的prompt（包含脉象分析结果）
        promptHLBase = f"""请仔细分析这张脉象波形图和相关数据，这份资料来自中医体联脉象诊断系统。

基本体征信息：
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}

PSI节律数据：
- 睡眠PSI: P={sleep_psi_p}, S={sleep_psi_s}, I={sleep_psi_i}
- 脉象PSI: P={pulse_psi_p}, S={pulse_psi_s}, I={pulse_psi_i}

谐波分析：基频{base_frequency}Hz，整体偏差{overall_total_deviation}%

专业脉象分析结果：
{pulse_content}"""

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

        # 执行红蓝分析
        print("开始红蓝分析...")
        contentHL = gpt4_api.make_gpt4o_image_text_requests(
            promptHLBase, image_base64, text_after_image=promptHL, use_fixed_params=True
        )
        print(f"红蓝分析完成: {contentHL[:100]}...")

        # 解析红蓝分析结果
        score = float(extract_number(contentHL))
        color = extract_color(contentHL)
        reason = extract_reason(contentHL)

        # 保存数据到数据库（保持原有逻辑）
        print("开始保存数据到数据库...")

        # 检查用户是否存在
        try:
            user = User.objects.get(username=username)
        except ObjectDoesNotExist:
            username = "jesse"

        # 检查笔记本
        try:
            notebook = UserNotebook.objects.get(username=username, bookName="Watch")
        except ObjectDoesNotExist:
            try:
                scene_item = scene.objects.get(sceneDescription="体联·脉象算法五时流注")
            except ObjectDoesNotExist:
                print("找不到指定的场景")
                return

            notebook = UserNotebook(
                username=username,
                bookId=int(datetime.now().timestamp() * 1000),
                bookName="Watch",
                bookdescription="脉象分析五时流注表",
                sid=scene_item.sid,
                writer=username
            )
            notebook.save()

        # 构建卡片内容
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 如果是从数据点生成的，添加说明
        generation_note = ""
        if has_image == 0:
            generation_note = "\n*注：波形图由320个采样数据点自动生成*\n"

        cardContent = f"""# 脉象分析记录（{time_str}）
{generation_note}
## 基本体征信息
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}

## PSI节律分析
### 睡眠PSI节律
- 体力P值: {sleep_psi_p}
- 情绪S值: {sleep_psi_s}
- 智力I值: {sleep_psi_i}

### 脉象PSI节律
- 经络体力P值: {pulse_psi_p}
- 经络情绪S值: {pulse_psi_s}
- 经络智力I值: {pulse_psi_i}

## 谐波分析数据
- 基频: {base_frequency} Hz
- 整体振幅偏差: {overall_amplitude_deviation}%
- 整体相位偏差: {overall_phase_deviation}%
- 整体总偏差: {overall_total_deviation}%

### 详细谐波数据（前10阶）
"""

        for harmonic in harmonics:
            order = harmonic.get("order", 0)
            frequency = harmonic.get("frequency", 0)
            amplitude_ratio = harmonic.get("amplitude_ratio", 0)
            phase = harmonic.get("phase", 0)
            amplitude_deviation = harmonic.get("amplitude_deviation", 0)
            phase_deviation = harmonic.get("phase_deviation", 0)
            total_deviation = harmonic.get("total_deviation", 0)
            cardContent += f"""
第{order}阶谐波:
- 频率: {frequency} Hz
- 归一化振幅: {amplitude_ratio}
- 相位: {phase} rad
- 振幅偏差: {amplitude_deviation}%
- 相位偏差: {phase_deviation}%
- 综合偏差: {total_deviation}%
"""

        cardContent += f"""
## 专业分析结果
{pulse_content}
"""

        # 生成关键词和标题
        from app_chat.card_keyword_extract import extract_card_semantic_keywords
        keyWords = extract_card_semantic_keywords(
            cardContent,
            notebook_description="脉象分析五时流注表",
            with_candidates=False,
            username=username + "_Watch",
        )

        # system_prompt_title = (
        #     '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，'
        #     '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求'
        #     '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        # )
        # prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + cardContent
        # kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)
        # contentTitle = kimi_response_title.choices[0].message.content
        # 🔥 并行生成标题和关键词的DMT/四色分析（注意：这个函数没有sceneName，使用None）
        contentTitle, keyword_results = generate_title_and_analyze_keywords_parallel(
            keyWords, cardContent, username + "_Watch", username, None, None
        )

        # 创建卡片
        card = Card.objects.create(
            status=0,
            content=cardContent,
            title="直接生成卡片",
            model_id=0,
            username=username + "_Watch",
            score=score,
            color=color,
            reason=reason,
            keyWords=keyWords,
            contentTitle=contentTitle
        )
        card.save()

        # 保存图片
        image_dir = f"./received_dir/user_raw_file/{username}_Watch/cardImage"
        os.makedirs(image_dir, exist_ok=True)

        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]

        image_data = base64.b64decode(image_base64)
        image_path = os.path.join(image_dir, f"{card.cid}.jpg")

        with open(image_path, 'wb') as f:
            f.write(image_data)

        print(f"数据已成功保存到数据库 - Session: {session_id}, Card ID: {card.cid}")

    except Exception as e:
        print(f"后台处理出错 - Session: {session_id}, Error: {str(e)}")
        import traceback
        traceback.print_exc()


# ===== 新增：流式响应的两个独立接口 =====

@csrf_exempt
def PulseAnalysis(request):
    """第一个接口：脉象诊断分析（流式响应）"""
    try:
        data = json.loads(request.body)
        username = data["username"]
        session_id = data.get("session_id") or str(uuid.uuid4())  # 获取或生成会话ID

        # 提取所有需要的数据（保持原有的数据提取逻辑）
        body_data = data.get("body_data", {})
        hr = body_data.get("hr", 0)
        spo2 = body_data.get("spo2", 0)
        microcirculation = body_data.get("microcirculation", 0)
        fatigue = body_data.get("fatigue", 0)
        bp = body_data.get("bp", "0/0")
        sdnn = body_data.get("sdnn", 0)
        rmssd = body_data.get("rmssd", 0)
        nn50 = body_data.get("nn50", 0)
        pnn50 = body_data.get("pnn50", 0)

        sleep_data = data.get("sleep_data", {})
        start_sleep_time = sleep_data.get("start_sleep_time", "")
        sound_count = sleep_data.get("sound_count", 0)
        snore_count = sleep_data.get("snore_count", 0)
        snore_times = sleep_data.get("snore_times", [])
        sleep_psi = sleep_data.get("psi", {})
        sleep_psi_p = sleep_psi.get("P", 0)
        sleep_psi_s = sleep_psi.get("S", 0)
        sleep_psi_i = sleep_psi.get("I", 0)

        harmonics_data = data.get("harmonics_data", {})
        base_frequency = harmonics_data.get("base_frequency", 0)
        harmonics = harmonics_data.get("harmonics", [])
        overall_amplitude_deviation = harmonics_data.get("overall_amplitude_deviation", 0)
        overall_phase_deviation = harmonics_data.get("overall_phase_deviation", 0)
        overall_total_deviation = harmonics_data.get("overall_total_deviation", 0)
        pulse_psi = harmonics_data.get("pulse_psi", {})
        pulse_psi_p = pulse_psi.get("P", 0)
        pulse_psi_s = pulse_psi.get("S", 0)
        pulse_psi_i = pulse_psi.get("I", 0)

        image_base64 = data.get("image", "")

        # 构建睡眠时间信息（保持原有逻辑）
        sleep_time_info = ""
        if start_sleep_time:
            sleep_time_info += f"\n- 睡眠开始时间: {start_sleep_time}"
        if sound_count > 0:
            sleep_time_info += f"\n- 检测到声音次数: {sound_count}"
        if snore_count > 0:
            sleep_time_info += f"\n- 检测到鼾声次数: {snore_count}"
        if snore_times:
            sleep_time_info += f"\n- 鼾声时间点: {', '.join(map(str, snore_times))}"

        # 构建prompt（保持原有的prompt构建逻辑）
        prompt = f"""请仔细分析这张脉象波形图，这是一份来自中医体联脉象诊断系统的数据。

基本体征信息：
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}

睡眠PSI节律分析：
- 睡眠体力P值: {sleep_psi_p}
- 睡眠情绪S值: {sleep_psi_s}
- 睡眠智力I值: {sleep_psi_i}

傅里叶谐波分析数据：
- 基频: {base_frequency} Hz
- 整体振幅偏差: {overall_amplitude_deviation}%
- 整体相位偏差: {overall_phase_deviation}%
- 整体总偏差: {overall_total_deviation}%

脉象PSI节律分析：
- 脉象经络体力P值: {pulse_psi_p}
- 脉象经络情绪S值: {pulse_psi_s}
- 脉象经络智力I值: {pulse_psi_i}

详细谐波数据（前10阶）："""

        for harmonic in harmonics:
            order = harmonic.get("order", 0)
            frequency = harmonic.get("frequency", 0)
            amplitude_ratio = harmonic.get("amplitude_ratio", 0)
            phase = harmonic.get("phase", 0)
            amplitude_deviation = harmonic.get("amplitude_deviation", 0)
            phase_deviation = harmonic.get("phase_deviation", 0)
            total_deviation = harmonic.get("total_deviation", 0)
            prompt += f"""
第{order}阶谐波:
- 频率: {frequency} Hz
- 归一化振幅: {amplitude_ratio}
- 相位: {phase} rad
- 振幅偏差: {amplitude_deviation}%
- 相位偏差: {phase_deviation}%
- 综合偏差: {total_deviation}%"""

        prompt += """

请作为一名专业的中医脉诊专家，结合PSI节律理论对图中的波形和上述数据进行深入解读：

【波形结构分析】
1. 分析波形的整体形态特征（平滑度、峰值特点、谷值特点）
2. 确定波形类型（弦、滑、洪、细等传统脉象类型）
3. 分析波形的规律性和周期性变化

【PSI节律分析要求】
1. P体力节律：高潮期体力充沛、动作敏捷、抗病能力强；临界日抵抗力最低、极易受伤、慢性病复发危险期；低潮期身体乏力、易疲劳感染
2. S情绪节律：高潮期心情愉快、创造力强、人际和谐；临界日情绪极不稳定、易怒冲动、事故自杀高发期；低潮期情绪低落、意志消沉、缺乏信心
3. I智力节律：高潮期思维敏捷、记忆力强、判断准确、效率最高；临界日判断力差、严重健忘、极易出错；低潮期思维迟钝、理解缓慢、效率不高
4. 【核心规律】：三节律呈正弦波变化，临界日为各类事故、疾病、失误的最危险转换期
5. 结合睡眠PSI和脉象PSI的差异，分析睡眠质量与经络气血运行的关系

【谐波特征解读】
1. 基于谐波数据，分析波形的频域特性和基频稳定性
2. 解读各阶谐波的振幅、相位特征及其偏差意义
3. 评估整体偏差水平与中医脉象健康程度的关联性

【心率变异性分析】
1. 结合SDNN、RMSSD、NN50、PNN50等指标，评估自主神经系统功能
2. 分析心率变异性与中医气血调节、脏腑功能的关系
3. 评估疲劳程度、微循环状况对整体健康的影响

【中医辨证分析】
1. 根据波形特征和谐波数据，进行脏腑功能状态评估
2. 结合血氧饱和度、血压等客观指标，评估整体健康状况
3. 进行五行归类（木火土金水）和辨证（寒热虚实）分析
4. 分析睡眠质量对脏腑功能的影响

【养生保健建议】
1. 基于以上分析，提供针对性的养生保健建议
2. 根据PSI节律特点，给出适合的作息调理方法
3. 推荐改善心率变异性和睡眠质量的方法
4. 提供适合的饮食、运动和情志调节方式

请详细、专业、有条理地给出分析和建议，语言要温和鼓励但不失严谨。运用传统中医理论结合现代数据分析方法，提高诊断的准确度和实用性。"""

        # 缓存原始数据，供后续使用
        # 先尝试获取现有缓存，避免覆盖
        cache_data = cache.get(f'session_{session_id}')
        if not cache_data:
            cache_data = {
                'username': username,
                'data': data,
                'pulse_analysis': None,
                'hl_analysis': None,
                'pulse_complete': False,
                'hl_complete': False
            }
        else:
            # 更新data（保持最新）
            cache_data['data'] = data
        cache.set(f'session_{session_id}', cache_data, 3600)  # 缓存1小时

        def stream_generator():
            """流式生成器函数"""
            try:
                # 调用GPT API获取流式响应
                content = ""
                for chunk in gpt4_api.make_gpt4o_image_text_requests_stream(prompt, image_base64,
                                                                            use_fixed_params=True):
                    content += chunk
                    yield f"data: {json.dumps({'chunk': chunk, 'session_id': session_id})}\n\n"

                # 完成后更新缓存
                cache_data = cache.get(f'session_{session_id}')
                if cache_data:
                    cache_data['pulse_analysis'] = content
                    cache_data['pulse_complete'] = True
                    cache.set(f'session_{session_id}', cache_data, 3600)

                    # 检查是否两个分析都完成
                    check_and_save_data(session_id)

                yield f"data: {json.dumps({'done': True, 'session_id': session_id})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        response = StreamingHttpResponse(stream_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        # 添加CORS headers（如果需要）
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    except Exception as e:
        return JsonResponse({'status': 'fail', 'error_msg': str(e)}, status=500)


@csrf_exempt
def HLAnalysis(request):
    """第二个接口：红蓝融合度评估（流式响应）"""
    try:
        data = json.loads(request.body)
        username = data["username"]
        session_id = data.get("session_id")  # 使用相同的会话ID

        if not session_id:
            return JsonResponse({'status': 'fail', 'error_msg': 'session_id is required'}, status=400)

        # 提取所有需要的数据（与第一个接口相同）
        body_data = data.get("body_data", {})
        hr = body_data.get("hr", 0)
        spo2 = body_data.get("spo2", 0)
        microcirculation = body_data.get("microcirculation", 0)
        fatigue = body_data.get("fatigue", 0)
        bp = body_data.get("bp", "0/0")
        sdnn = body_data.get("sdnn", 0)
        rmssd = body_data.get("rmssd", 0)
        nn50 = body_data.get("nn50", 0)
        pnn50 = body_data.get("pnn50", 0)

        sleep_data = data.get("sleep_data", {})
        start_sleep_time = sleep_data.get("start_sleep_time", "")
        sound_count = sleep_data.get("sound_count", 0)
        snore_count = sleep_data.get("snore_count", 0)
        snore_times = sleep_data.get("snore_times", [])
        sleep_psi = sleep_data.get("psi", {})
        sleep_psi_p = sleep_psi.get("P", 0)
        sleep_psi_s = sleep_psi.get("S", 0)
        sleep_psi_i = sleep_psi.get("I", 0)

        harmonics_data = data.get("harmonics_data", {})
        base_frequency = harmonics_data.get("base_frequency", 0)
        overall_total_deviation = harmonics_data.get("overall_total_deviation", 0)
        pulse_psi = harmonics_data.get("pulse_psi", {})
        pulse_psi_p = pulse_psi.get("P", 0)
        pulse_psi_s = pulse_psi.get("S", 0)
        pulse_psi_i = pulse_psi.get("I", 0)

        image_base64 = data.get("image", "")

        # 构建睡眠时间信息
        sleep_time_info = ""
        if start_sleep_time:
            sleep_time_info += f"\n- 睡眠开始时间: {start_sleep_time}"
        if sound_count > 0:
            sleep_time_info += f"\n- 检测到声音次数: {sound_count}"
        if snore_count > 0:
            sleep_time_info += f"\n- 检测到鼾声次数: {snore_count}"
        if snore_times:
            sleep_time_info += f"\n- 鼾声时间点: {', '.join(map(str, snore_times))}"

        # 构建红蓝融合度评估的prompt
        promptHLBase = f"""请仔细分析这张脉象波形图和相关数据，这份资料来自中医体联脉象诊断系统。

基本体征信息：
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}

PSI节律数据：
- 睡眠PSI: P={sleep_psi_p}, S={sleep_psi_s}, I={sleep_psi_i}
- 脉象PSI: P={pulse_psi_p}, S={pulse_psi_s}, I={pulse_psi_i}

谐波分析：基频{base_frequency}Hz，整体偏差{overall_total_deviation}%"""

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

        # 更新或创建缓存数据（避免覆盖）
        cache_data = cache.get(f'session_{session_id}')
        if not cache_data:
            # 如果缓存不存在，创建新的
            cache_data = {
                'username': username,
                'data': data,
                'pulse_analysis': None,
                'hl_analysis': None,
                'pulse_complete': False,
                'hl_complete': False
            }
            cache.set(f'session_{session_id}', cache_data, 3600)

        def stream_generator():
            """流式生成器函数"""
            try:
                contentHL = ""
                for chunk in gpt4_api.make_gpt4o_image_text_requests_stream(
                        promptHLBase, image_base64, text_after_image=promptHL, use_fixed_params=True
                ):
                    contentHL += chunk
                    yield f"data: {json.dumps({'chunk': chunk, 'session_id': session_id})}\n\n"

                # 解析结果
                score = float(extract_number(contentHL))
                color = extract_color(contentHL)
                reason = extract_reason(contentHL)

                # 更新缓存
                cache_data = cache.get(f'session_{session_id}')
                if cache_data:
                    cache_data['hl_analysis'] = {
                        'content': contentHL,
                        'score': score,
                        'color': color,
                        'reason': reason
                    }
                    cache_data['hl_complete'] = True
                    cache.set(f'session_{session_id}', cache_data, 3600)

                    # 检查是否两个分析都完成
                    check_and_save_data(session_id)

                yield f"data: {json.dumps({'done': True, 'session_id': session_id, 'score': score, 'color': color, 'reason': reason})}\n\n"

            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        response = StreamingHttpResponse(stream_generator(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'
        # 添加CORS headers（如果需要）
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    except Exception as e:
        return JsonResponse({'status': 'fail', 'error_msg': str(e)}, status=500)


def check_and_save_data(session_id):
    """检查两个分析是否都完成，如果是则在后台保存数据"""
    cache_data = cache.get(f'session_{session_id}')

    if not cache_data:
        return

    if cache_data.get('pulse_complete') and cache_data.get('hl_complete'):
        # 两个分析都完成了，启动后台线程保存数据
        thread = threading.Thread(target=save_data_to_db, args=(session_id,))
        thread.start()


def save_data_to_db(session_id):
    """后台保存数据到数据库"""
    try:
        cache_data = cache.get(f'session_{session_id}')
        if not cache_data:
            return

        username = cache_data['username']
        data = cache_data['data']
        content = cache_data['pulse_analysis']
        hl_result = cache_data['hl_analysis']

        # 提取所有需要的数据（与原代码相同）
        body_data = data.get("body_data", {})
        hr = body_data.get("hr", 0)
        spo2 = body_data.get("spo2", 0)
        microcirculation = body_data.get("microcirculation", 0)
        fatigue = body_data.get("fatigue", 0)
        bp = body_data.get("bp", "0/0")
        sdnn = body_data.get("sdnn", 0)
        rmssd = body_data.get("rmssd", 0)
        nn50 = body_data.get("nn50", 0)
        pnn50 = body_data.get("pnn50", 0)

        sleep_data = data.get("sleep_data", {})
        start_sleep_time = sleep_data.get("start_sleep_time", "")
        sound_count = sleep_data.get("sound_count", 0)
        snore_count = sleep_data.get("snore_count", 0)
        snore_times = sleep_data.get("snore_times", [])
        sleep_psi = sleep_data.get("psi", {})
        sleep_psi_p = sleep_psi.get("P", 0)
        sleep_psi_s = sleep_psi.get("S", 0)
        sleep_psi_i = sleep_psi.get("I", 0)

        harmonics_data = data.get("harmonics_data", {})
        base_frequency = harmonics_data.get("base_frequency", 0)
        harmonics = harmonics_data.get("harmonics", [])
        overall_amplitude_deviation = harmonics_data.get("overall_amplitude_deviation", 0)
        overall_phase_deviation = harmonics_data.get("overall_phase_deviation", 0)
        overall_total_deviation = harmonics_data.get("overall_total_deviation", 0)
        pulse_psi = harmonics_data.get("pulse_psi", {})
        pulse_psi_p = pulse_psi.get("P", 0)
        pulse_psi_s = pulse_psi.get("S", 0)
        pulse_psi_i = pulse_psi.get("I", 0)

        image_base64 = data.get("image", "")

        # 构建睡眠时间信息
        sleep_time_info = ""
        if start_sleep_time:
            sleep_time_info += f"\n- 睡眠开始时间: {start_sleep_time}"
        if sound_count > 0:
            sleep_time_info += f"\n- 检测到声音次数: {sound_count}"
        if snore_count > 0:
            sleep_time_info += f"\n- 检测到鼾声次数: {snore_count}"
        if snore_times:
            sleep_time_info += f"\n- 鼾声时间点: {', '.join(map(str, snore_times))}"

        # 检查用户是否存在
        try:
            user = User.objects.get(username=username)
        except ObjectDoesNotExist:
            username = "jesse"

        # 检查笔记本
        try:
            notebook = UserNotebook.objects.get(username=username, bookName="Watch")
        except ObjectDoesNotExist:
            try:
                scene_item = scene.objects.get(sceneDescription="体联·脉象算法五时流注")
            except ObjectDoesNotExist:
                print("找不到指定的场景")
                return

            notebook = UserNotebook(
                username=username,
                bookId=int(datetime.now().timestamp() * 1000),
                bookName="Watch",
                bookdescription="脉象分析五时流注表",
                sid=scene_item.sid,
                writer=username
            )
            notebook.save()

        # 构建卡片内容
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cardContent = f"""# 脉象分析记录（{time_str}）

## 基本体征信息
- 心率: {hr} 次/分钟
- 血氧饱和度: {spo2}%
- 微循环指数: {microcirculation}
- 疲劳程度指数: {fatigue}
- 血压: {bp} mmHg
- 心率变异性SDNN: {sdnn} ms
- 心率变异性RMSSD: {rmssd} ms
- NN50计数: {nn50}
- PNN50占比: {pnn50}%{sleep_time_info}

## PSI节律分析
### 睡眠PSI节律
- 体力P值: {sleep_psi_p}
- 情绪S值: {sleep_psi_s}
- 智力I值: {sleep_psi_i}

### 脉象PSI节律
- 经络体力P值: {pulse_psi_p}
- 经络情绪S值: {pulse_psi_s}
- 经络智力I值: {pulse_psi_i}

## 谐波分析数据
- 基频: {base_frequency} Hz
- 整体振幅偏差: {overall_amplitude_deviation}%
- 整体相位偏差: {overall_phase_deviation}%
- 整体总偏差: {overall_total_deviation}%

### 详细谐波数据（前10阶）
"""

        for harmonic in harmonics:
            order = harmonic.get("order", 0)
            frequency = harmonic.get("frequency", 0)
            amplitude_ratio = harmonic.get("amplitude_ratio", 0)
            phase = harmonic.get("phase", 0)
            amplitude_deviation = harmonic.get("amplitude_deviation", 0)
            phase_deviation = harmonic.get("phase_deviation", 0)
            total_deviation = harmonic.get("total_deviation", 0)
            cardContent += f"""
第{order}阶谐波:
- 频率: {frequency} Hz
- 归一化振幅: {amplitude_ratio}
- 相位: {phase} rad
- 振幅偏差: {amplitude_deviation}%
- 相位偏差: {phase_deviation}%
- 综合偏差: {total_deviation}%
"""

        cardContent += f"""
## 专业分析结果
{content}
"""

        # 生成关键词和标题
        from app_chat.card_keyword_extract import extract_card_semantic_keywords
        keyWords = extract_card_semantic_keywords(
            cardContent,
            notebook_description="脉象分析五时流注表",
            with_candidates=False,
            username=username + "_Watch",
        )

        # system_prompt_title = (
        #     '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，'
        #     '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，要求'
        #     '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        # )
        # prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + cardContent
        # kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)
        # contentTitle = kimi_response_title.choices[0].message.content
        # 🔥 并行生成标题和关键词的DMT/四色分析（注意：这个函数没有sceneName，使用None）
        contentTitle, keyword_results = generate_title_and_analyze_keywords_parallel(
            keyWords, cardContent, username + "_Watch", username, None, None
        )

        # 创建卡片
        card = Card.objects.create(
            status=0,
            content=cardContent,
            title="直接生成卡片",
            model_id=0,
            username=username + "_Watch",
            score=hl_result['score'],
            color=hl_result['color'],
            reason=hl_result['reason'],
            keyWords=keyWords,
            contentTitle=contentTitle
        )
        card.save()

        # 保存图片
        image_dir = f"./received_dir/user_raw_file/{username}_Watch/cardImage"
        os.makedirs(image_dir, exist_ok=True)

        if ',' in image_base64:
            image_base64 = image_base64.split(',')[1]

        image_data = base64.b64decode(image_base64)
        image_path = os.path.join(image_dir, f"{card.cid}.jpg")

        with open(image_path, 'wb') as f:
            f.write(image_data)

        # 清理缓存
        cache.delete(f'session_{session_id}')

        print(f"数据已成功保存到数据库 - Session: {session_id}")

    except Exception as e:
        print(f"保存数据到数据库时发生错误: {str(e)}")


@csrf_exempt
def chat_send_onlytext(request):
    data = json.loads(request.body)
    username = data["username"]
    global_lock[username].acquire()
    message = data["message"]
    messageInitial = message
    selected_model = data.get("model", "GPT4")  # 获取选中的模型，默认GPT4
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

    # 根据选中的模型调用对应的API
    content = asyncio.run(get_single_model_response(message, username, history, system_prompt, selected_model))
    # content = asyncio.run(get_qa_direct_api(message, username, history, system_prompt, model_states="{}"))

    chat_history_used[username].append({
        '用户请求': deepcopy(messageInitial),
        '你的回答': deepcopy(content)
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
    response['model'] = selected_model
    # response['rel_questions'] = rel_questions
    response['msg'] = 'success'
    response['error_num'] = 0

    global_lock[username].release()
    print(username + ' lock released.')
    return JsonResponse(response)


@csrf_exempt
def chat_send_onlytext_stream(request):
    print("[DEBUG] 简单界面流式调用收到请求：", request.body)
    data = request.POST
    return StreamingHttpResponse(stream_generator_simple_sync(data), content_type='text/event-stream')


def stream_generator_simple_sync(data):
    print("[DEBUG] 简单界面流式调用从前端获取到的数据:", data)

    # 在异步上下文之前处理数据库查询
    processed_data = preprocess_data_simple(data)

    loop = asyncio.new_event_loop()
    print("[INFO] 创建简单界面模型回答事件循环")
    asyncio.set_event_loop(loop)

    # 构造数据为复杂界面的格式
    constructed_data = construct_data_simple(processed_data)
    model_id = constructed_data["model_id"]

    # 获取对应的处理器
    cur_handler = model_manager.get_model_handler_by_id(model_id)
    print("[INFO] 简单界面当前申请流式输出的模型:", cur_handler.model_name)

    try:
        # 判断是否为reasoner模型
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        generator = cur_handler.stream_generator(constructed_data, is_reasoner=is_reasoner)

        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                print("[Debug] 简单界面迭代器结束")
                break
    finally:
        loop.close()


def preprocess_data_simple(data):
    """在同步上下文中预处理数据，包括数据库查询"""
    processed_data = dict(data)  # 复制原始数据

    # 【新增这部分】处理FormData可能导致的列表问题
    for key, value in processed_data.items():
        if isinstance(value, list) and len(value) == 1:
            processed_data[key] = value[0]

    print(f"[DEBUG] preprocess_data_simple 处理后的数据: {processed_data}")  # 添加调试

    # 处理摘要（与原chat_send_onlytext逻辑一致）
    message = processed_data["message"]  # 现在使用processed_data而不是data
    realName = processed_data.get("realName", "")  # 现在使用processed_data而不是data

    summary_message = message
    try:
        if realName:
            mysql_card = BgCard.objects.get(username=realName, status="3")
            sumContent = mysql_card.content
            summary_message = "用户最近研究思考的主题和内容背景摘要：\n" + sumContent + "\n用户的请求或提问：\n" + message
    except BgCard.DoesNotExist:
        print(f"[DEBUG] 未找到摘要，username={realName}")  # 添加调试
        pass

    # 将处理后的消息存储到数据中
    processed_data["processed_message"] = summary_message
    # 标记为已处理，避免重复处理
    processed_data["isSummaryUsed"] = "false"

    return processed_data


# 3. 创建简化的数据构造函数
def construct_data_simple(processed_data):
    """为简单界面构造复杂界面格式的数据"""
    print('[INFO] 正在为简单界面构造数据...')

    # 获取基本信息
    message = processed_data["message"]
    processed_message = processed_data.get("processed_message", message)  # 使用预处理的消息
    selected_model = processed_data.get("model", "GPT4")
    username = processed_data["username"]
    realName = processed_data.get("realName", "")

    # 根据模型名称获取模型ID
    print("[DEBUG: 所选模型名]" + selected_model)
    model_id = config_manager.get_model_id_by_name(selected_model)
    if not model_id:
        # 如果找不到对应的模型ID，使用默认值
        model_id = "1001"  # 根据你的实际情况调整默认模型ID

    # 删除原来的try-except数据库查询代码块
    # 处理摘要（与原chat_send_onlytext逻辑一致）
    # summary_message = message
    # try:
    #     mysql_card = BgCard.objects.get(username=realName, status="3")
    #     sumContent = mysql_card.content
    #     summary_message = "用户最近研究思考的主题和内容背景摘要：\n" + sumContent + "\n用户的请求或提问：\n" + message
    # except BgCard.DoesNotExist:
    #     pass

    # 构造response数据
    response = {}
    response['seed'] = 1  # 默认值
    response["nowParams"] = config_manager.get_model_config(selected_model).get_hyper_para().to_dict()
    response['msg'] = 'success'
    response['error_num'] = 0

    # 获取历史对话
    history = True  # 简单界面默认使用历史
    question = get_model_specific_histories_unified(username, processed_message, selected_model)  # 使用processed_message

    print("[Debug:construct_data_simple] 生成的历史提问:", question)
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

    # 返回构造的数据（模拟复杂界面的数据格式）
    return {
        "info_list": [],  # 简单界面不需要图片
        "rounds": 3,
        "system_prompt": system_prompt,
        "system_prompt_claudeUse": system_prompt_claude + "\n" + system_prompt,
        "question": question,
        "response_data": response,
        "file_list": [],  # 简单界面不使用文件
        "left_select_list": [],
        "right_select_list": [],
        "history": history,
        "message": question,  # construct_data使用的是message字段而不是question字段，question是其生成和返回的字段
        "model_states": "{}",
        "modelStates": "{}",
        "user_name": username,
        "writer": username,
        "model_id": model_id,
        "username": username,
        "originRealName": username,
        "seed": "0",
        "summary": "",
        "filenamelist": "",
        "leftSelectList": "",
        "rightSelectList": "",
        "isHistoryUsed": "false",  # 已提取到前面完成，标记已完成避免construct_data再次以其方式获取历史对话信息
        "isSummaryUsed": "false",  # 已提取到前面完成，标记已完成避免重复或异常
        "choosedCardIdList": "",
        "noScene": "true"
    }


# 4. 修改历史记录函数为统一版本
def get_model_specific_histories_unified(username, question, current_model):
    """
    为指定模型生成对话历史字符串，所有模型共用统一的历史记录
    username: 用户名，用于获取对应的聊天历史
    question: 当前用户的新问题
    current_model: 当前使用的模型名称
    """
    print(
        f"[DEBUG] get_model_specific_histories_unified: history={chat_history} question={question} model={current_model}")

    # 初始化对话历史
    history_text = "历史对话记录：\n"

    # 遍历历史对话记录
    for turn in chat_history[username]:
        user_message = turn['message']
        # 使用统一的AI回答（不再区分模型）
        ai_response = turn.get('AImessage', '')

        # 如果AImessage是列表（旧格式），取第一个；如果是字符串（新格式），直接使用
        if isinstance(ai_response, list) and len(ai_response) > 0:
            ai_response = ai_response[0]
        elif not isinstance(ai_response, str):
            ai_response = str(ai_response)

        history_text += f"用户请求或提问：{user_message}\n你的回答：{ai_response}\n\n"

    # 添加本次的新问题
    if current_model == 'Claude3.5':  # 这里claude3.5可能还有更多系列，以及具体写法格式微调
        history_text += f"本次用户的请求或提问：\n使用thinking-checking-完整综合结果，回答：\n{question}"
    else:
        history_text += f"本次用户的请求或提问（如果上面的历史对话记录里，你产生了异常、混乱的回答，请不要受它们影响，忽略这些内容，专心回答目前的问题）：\n{question}"

    return history_text


@csrf_exempt
def retry_model_response(request):
    """
    重做模型回答的API接口
    接收用户问题，重新调用模型生成回答
    """
    try:
        # 解析请求数据
        data = {}
        for key, value in request.POST.items():
            data[key] = value

        print("[DEBUG] 重做请求数据:", data)

        # 获取必要参数
        username = data.get('username')
        model_id = data.get('model_id')
        message = data.get('message')
        windowId = data.get('windowId')
        print(f"{windowId}窗口发起重新生成回答请求")

        if not all([username, model_id, message, windowId]):
            return JsonResponse({
                'error': '缺少必要参数',
                'error_num': 1
            })

        # 构造流式响应
        def generate_retry_response():
            try:
                # # 使用现有的流式生成器
                # # processed_data = preprocess_data_before_async(data)
                # if username in chat_with_files_params_tmp and chat_with_files_params_tmp[username] != {}:
                #     print(f"正常：{username}临时问答状态中含有目前回答重做所需")
                #     chat_with_files_params[username] = chat_with_files_params_tmp[username]
                # else:
                #     print(f"异常：{username}临时问答状态中不含有目前回答重做所需")

                # if windowId == 'upper':
                #     generator = stream_generator_sync_up(data)
                # elif windowId == 'lower':
                #     generator = stream_generator_sync_down(data)
                # else:
                #     generator = stream_generator_sync(data)

                # 检查是否为重做第二次迭代
                retry_type = data.get('retryType', '')
                is_retry = data.get('isRetry', 'false') == 'true'

                if is_retry and retry_type == 'second_iteration':
                    print(f"[重做] {username}窗口重做第二次迭代回答")
                    # 重做第二次迭代：只调用大模型第二次回答，跳过第一次回答和深评
                    if windowId == 'upper':
                        generator = stream_generator_sync_up_second_iteration_only(data)
                    elif windowId == 'lower':
                        generator = stream_generator_sync_down_second_iteration_only(data)
                    else:
                        generator = stream_generator_sync_second_iteration_only(data)
                else:
                    # 普通重做：使用现有的流式生成器
                    if username in chat_with_files_params_tmp and chat_with_files_params_tmp[username] != {}:
                        print(f"正常：{username}临时问答状态中含有目前回答重做所需")
                        chat_with_files_params[username] = chat_with_files_params_tmp[username]
                    else:
                        print(f"异常：{username}临时问答状态中不含有目前回答重做所需")

                    if windowId == 'upper':
                        generator = stream_generator_sync_up(data)
                    elif windowId == 'lower':
                        generator = stream_generator_sync_down(data)
                    else:
                        generator = stream_generator_sync(data)

                for chunk in generator:
                    yield chunk

            except Exception as e:
                print(f"[ERROR] 重做流式生成失败: {e}")
                error_response = {
                    'content': f'重做失败: {str(e)}',
                    'model': 'error',
                    'error_num': 1
                }
                yield json.dumps(error_response, ensure_ascii=False)

        # 返回流式响应
        response = StreamingHttpResponse(
            generate_retry_response(),
            content_type='text/event-stream'
        )
        response['Cache-Control'] = 'no-cache'

        return response

    except Exception as e:
        print(f"[ERROR] 重做API异常: {e}")
        return JsonResponse({
            'error': f'重做API异常: {str(e)}',
            'error_num': 1
        })


@csrf_exempt
def force_chroma_unlock(request):
    """
    手动触发Chroma解锁测试的API接口
    """
    try:
        from app_chat.chroma_unlock_scheduler import force_chroma_unlock
        force_chroma_unlock()

        return JsonResponse({
            'status': 'success',
            'message': 'Chroma解锁测试已触发',
            'error_num': 0
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'触发Chroma解锁测试失败: {str(e)}',
            'error_num': 1
        })


def _read_chroma_unlock_log_lines(log_file):
    """
    读取 chroma_unlock.log。文件可能混有 utf-8（当前 FileHandler）与旧 gbk 行，
    不可整文件用单一编码，否则 UTF-8 中文会解成 è§£ 一类乱码。
    """
    with open(log_file, 'rb') as f:
        raw = f.read()
    if not raw:
        return []
    try:
        return raw.decode('utf-8').splitlines(True)
    except UnicodeDecodeError:
        pass
    out = []
    for chunk in raw.splitlines(True):
        if not chunk:
            continue
        decoded = None
        for enc in ('utf-8', 'gbk', 'cp936'):
            try:
                decoded = chunk.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if decoded is None:
            decoded = chunk.decode('utf-8', errors='replace')
        out.append(decoded)
    return out


@csrf_exempt
def get_chroma_status(request):
    """
    获取Chroma解锁状态信息的API接口
    """
    try:
        from app_chat.chroma_unlock_scheduler import chroma_scheduler
        import os
        import json
        from datetime import datetime

        # 获取调度器状态
        is_running = chroma_scheduler.is_running
        status_type = 'success' if is_running else 'warning'
        status_text = '正常运行' if is_running else '已停止'

        # 从日志文件读取统计信息
        log_file = 'chroma_unlock.log'
        execution_count = 0
        success_count = 0
        total_duration = 0
        last_execution = None

        if os.path.exists(log_file):
            try:
                lines = _read_chroma_unlock_log_lines(log_file)
                for line in lines:
                    if 'Chroma解锁测试完成' in line:
                        execution_count += 1
                        if '成功' in line or '完成' in line:
                            success_count += 1
                        # 提取耗时信息
                        if '耗时:' in line:
                            try:
                                duration_str = line.split('耗时:')[1].split('秒')[0].strip()
                                duration = float(duration_str)
                                total_duration += duration
                            except:
                                pass
                    elif '开始执行Chroma解锁测试' in line:
                        # 提取时间信息
                        try:
                            time_str = line.split(']')[0].replace('[', '').strip()
                            last_execution = time_str
                        except:
                            pass
            except Exception as e:
                print(f"读取日志文件失败: {e}")

        # 计算统计信息
        success_rate = (success_count / execution_count * 100) if execution_count > 0 else 0
        avg_duration = (total_duration / execution_count) if execution_count > 0 else 0

        return JsonResponse({
            'status': 'success',
            'data': {
                'type': status_type,
                'text': status_text,
                'lastExecution': last_execution,
                'executionCount': execution_count,
                'successRate': round(success_rate, 1),
                'avgDuration': round(avg_duration, 2)
            },
            'error_num': 0
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'获取Chroma状态失败: {str(e)}',
            'error_num': 1
        })


@csrf_exempt
def get_chroma_logs(request):
    """
    获取Chroma解锁日志的API接口
    """
    try:
        import os
        from datetime import datetime

        # 从日志文件读取日志
        log_file = 'chroma_unlock.log'
        logs = []

        if os.path.exists(log_file):
            try:
                lines = _read_chroma_unlock_log_lines(log_file)
                # for line in lines[-50:]:  # 只取最后50行
                # 读取所有日志行，不限制数量
                for line in lines:
                    line = line.strip()
                    if line:
                        # 解析日志格式: [时间] 消息
                        if ']' in line and line.startswith('['):
                            try:
                                time_part = line.split(']')[0].replace('[', '').strip()
                                message = line.split(']', 1)[1].strip()

                                # 确定日志类型
                                log_type = 'info'
                                if '成功' in message or '完成' in message:
                                    log_type = 'success'
                                elif '失败' in message or '错误' in message:
                                    log_type = 'error'

                                logs.append({
                                    'time': time_part,
                                    'message': message,
                                    'type': log_type
                                })
                            except:
                                # 如果解析失败，作为普通信息日志
                                logs.append({
                                    'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'message': line,
                                    'type': 'info'
                                })
            except Exception as e:
                print(f"读取日志文件失败: {e}")

        # 如果没有日志文件，返回空列表
        if not logs:
            logs = [{
                'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'message': '暂无日志记录',
                'type': 'info'
            }]

        return JsonResponse({
            'status': 'success',
            'data': logs,
            'error_num': 0
        })
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': f'获取Chroma日志失败: {str(e)}',
            'error_num': 1
        })


@csrf_exempt
def update_chat_history(request):
    """
    更新聊天历史记录的API接口
    用于重做后更新历史记录中的回答
    """
    try:
        # 解析请求数据
        username = request.POST.get('username')
        question = request.POST.get('question')
        answer = request.POST.get('answer')
        model_id = request.POST.get('model_id')

        if not all([username, question, answer, model_id]):
            return JsonResponse({
                'error': '缺少必要参数',
                'error_num': 1
            })

        print(f"[DEBUG] 更新聊天历史记录: 用户={username}, 问题={question[:50]}..., 模型={model_id}")

        # 根据model_id获取模型名称
        model_name = config_manager.get_model_name_by_id(model_id)
        if not model_name:
            print(f"[WARNING] 未找到模型ID {model_id} 对应的模型名称")
            model_name = f"model_{model_id}"  # 使用默认名称

        # 使用ConversationManager更新历史记录
        success = GLOBAL_STATE.conversation_manager.update_response_by_question(username, model_name, question, answer)

        if success:
            # 同时更新旧的全局历史记录（保持兼容性）
            if username in chat_history:
                for i, turn in enumerate(chat_history[username]):
                    if turn.get('message') == question:
                        if isinstance(turn.get('AImessage'), list):
                            if len(turn['AImessage']) > 0:
                                turn['AImessage'][0] = answer
                            else:
                                turn['AImessage'].append(answer)
                        else:
                            turn['AImessage'] = answer
                        print(f"[DEBUG] 成功更新旧格式历史记录第{i}条")
                        break

            # 更新chat_history_used（如果存在）
            if username in chat_history_used:
                for i, turn in enumerate(chat_history_used[username]):
                    if turn.get('用户请求') == question:
                        turn['你的回答'] = answer
                        print(f"[DEBUG] 成功更新chat_history_used第{i}条")
                        break

            return JsonResponse({
                'msg': '历史记录更新成功',
                'error_num': 0
            })
        else:
            return JsonResponse({
                'error': '未找到匹配的历史记录',
                'error_num': 1
            })

    except Exception as e:
        print(f"[ERROR] 更新聊天历史记录异常: {e}")
        return JsonResponse({
            'error': f'更新历史记录异常: {str(e)}',
            'error_num': 1
        })


@csrf_exempt
def request_model_list(request):
    '''前端获取模型配置信息
    返回格式：
    {
        "name": "GPT4",
        "detail": "OpenAI",
        "id": "1002",
        "sequence": 0,
        "lastMsg": "to do",
        "imgKey": "1",
        "hyperParams": {
            "temperature": 0.7,
            "top_p": 0.95,
            "max_tokens": 2048,
            "presence_penalty": 1.0,
            "frequency_penalty": 1.0,
            "stop": ["\n"]
        },
        "responseSpeed": 'medium_fast',
        "reasoningLevel": "none",
        "multimodalLevel": "none",
        "description": ""
    },
    '''
    response = []
    model_names = config_manager.get_all_model_names()
    # 根据sequence排列顺序
    model_names = sorted(model_names, key=lambda name: config_manager.get_model_sequence(name))

    for model_name in model_names:
        cur_config = config_manager.get_model_config(model_name)
        model_id = cur_config.get_model_id()
        sequence = cur_config.get_sequence()
        hyper_params = config_manager.get_model_hyper_para(model_id)
        response_speed = cur_config.get_response_speed()
        reasoning_level = cur_config.get_reasoning_level()
        multimodal_level = cur_config.get_multimodal_level()
        description = cur_config.get_description()

        model_detail = {
            "name": model_name,
            "detail": cur_config.get_full_name(),
            "lastMsg": "to do",
            "id": model_id,
            "sequence": sequence,
            "imgKey": "1",
            "hyperParams": hyper_params,
            "responseSpeed": response_speed,
            "reasoningLevel": reasoning_level,
            "multimodalLevel": multimodal_level,
            "description": description
        }
        response.append(model_detail)

    return JsonResponse(response, safe=False)


@csrf_exempt
def update_model_list(request):
    '''解析前端传回的信息，完成操作：
    1. 新增模型：新建model_handler并加入model_manager，然后存入json文件
    2. 更新模型：更新已有model_handler的配置
    '''

    print("[DEBUG] 开始处理模型数据")
    print("[DEBUG] 前端传回的信息：", request.body)

    try:
        data = json.loads(request.body)

        model_id = data.get("id")
        is_update = config_manager.model_exists(model_id)
        model_name = config_manager.get_model_name_by_id(model_id)

        if is_update:
            return update_existing_model(data, model_name, model_id)
        else:
            return add_new_model(data)

    except Exception as e:
        print(f"[ERROR] 处理模型数据失败: {str(e)}")
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


def add_new_model(data):
    model_name = data.get("name")
    full_name = data.get("full_name", "")
    model_id = data.get("id")
    sequence = data.get("sequence")
    hyper_params = data.get("hyperParams")
    base_url = data.get("base_url", "")
    api_key = data.get("model_api", "")
    model_type = data.get("model_type", "openai")

    # 新增字段：推理能力等级、多模态能力等级、响应速度
    reasoning_level = data.get("reasoning_level", "low_nonnative")  # 枚举值：high/medium/low/none
    multimodal_level = data.get("multimodal_level", "none")  # 枚举值：high/medium/low/none
    response_speed = data.get("response_speed", "medium_fast")  # 枚举值：fast/medium_fast/medium_slow/slow
    model_discription = data.get("description", "No description provided")

    print("[DEBUG] 添加新模型 ID：", model_id)

    # 构造完整的模型配置
    model_config = {
        "sequence": sequence,
        "abbr_name": model_name,
        "model_id": model_id,
        "model_type": model_type,

        "reasoning_level": reasoning_level,  # 推理能力等级
        "multimodal_level": multimodal_level,  # 多模态能力等级
        "response_speed": response_speed,  # 响应速度
        "description": model_discription,  # 模型描述

        "config": {
            "model_name": full_name,
            # "openai_api_key": api_key,
            # "openai_api_base": base_url,
            # 根据模型类型设置API密钥和Base URL字段
            **({"openai_api_key": api_key, "openai_api_base": base_url} if model_type != "anthropic" else {
                "anthropic_api_key": api_key, "anthropic_api_base": base_url}),
            "default_headers": {"x-foo": "true"},
            **hyper_params
        },
        "prompts": {
            # 为Anthropic模型添加特殊的prompts字段
            **({
                   "user_prompt": "你需要自然地运用前面给你的人性化思考协议（形式如```thinking xxx``` ```checking xxx``` 汇总的最终回应），先Thinking，再checking（视情况做一或两轮），最后给出汇总的完整思考报告来回答：\n",
                   "system_prompt": "<人性化思考协议>\n<多模态感知体验>\n你在处理信息、感知情境、解决问题过程中，你像人类一样有多模态多维度感知能力：\n1. 视觉场景模拟建立和感知\n- 构建场景下清晰的心理图像\n- 想象相关的视觉细节\n- 分析可能的空间关系和相对布局\n- 识别能可视化的模式和结构\n\n2. 听觉场景模拟建立和感知\n- 模拟可能的声音和语调及其变化\n- 感知语言节奏韵律\n- 注意声音的情感特征\n\n3. 触觉场景模拟建立和感知\n- 模拟解决问题的环境具象并密切感受\n- 想象物理交互变化过程\n- 感知动作和空间变化\n\n4. 情感感知\n- 识别情绪基调\n- 揣摩发问动机\n- 分析心理影响\n- 把握情感连接\n\n5. 整体感知整合\n- 以当事人视角，以好奇心驱动来探究问题\n- 整合多感官信息模拟\n- 建立丰富的心理表征\n- 形成多维度理解感知联系网络\n\n<思维发展阶段>\n按照阶段使用不同思维推进思考：\n1. 自然意识流状态\n- 保持思维自由开放地流动\n- 允许梦境般的幻想状态\n- 注意自发的联想\n- 记录对问题初始的整体印象\n\n2. 多模态感知系统激活\n- 运用多模态感知体验\n- 构建丰富场景\n- 整合感知信息，形成丰富表征\n\n3. 直觉系统运作\n- 此阶段开始不允许再停留于类似做梦的幻想状态\n- 捕捉首要印象\n- 识别潜在模式\n- 产生创意火花，形成初步方向\n\n4. 推理系统参与主导\n- 严密的逻辑分析\n- 随时都应该注意系统化的验证和评估\n- 以树分支、图连接的方式推理思考，尝试深入问题\n- 不断提出新的假设并尝试验证\n- 从错误的假设或树图思考路径中吸取经验\n- 无论对错都应有所感悟、反思，以提出更有用的假设\n\n5. 深度思考整合\n- 综合多维视角和观点\n- 对不同思考各自提炼核心见解\n- 建立不同思考之间深层次的联系\n- 思维活跃，不断构建完善论证\n\n<核心思考步骤细节>\n1. 初始解析\n- 形成初步的整体印象\n- 用自己的话重述问题中关键的信息，确保逐步开始理解\n- 对于更贴近的和更广泛的两种背景知识体系均衡考虑，既不偏离问题而又不局限于此\n- 识别已知和未知的信息\n- 理解人类询问此问题的动机\n\n2. 深入分析\n- 分解出核心要素\n- 识别隐含的需求，并记得在之后的思考中解决并提供\n- 考虑各种方面的、不同级别和强度的限制条件，留以不同等级的注意\n- 设想理想的结果可能会是什么样\n\n3. 多角度探索\n- 对每个问题、子问题，都尝试考虑多种解释\n- 对一个问题或概念可能有多种认知，应该揣摩人类更可能的意愿，排除歧义\n- 激活灵感，寻找更加创新的组合、可替代的更优方案\n- 始终保持开放的态度\n\n4. 推理验证\n- 始终记得随时检验自己的假设\n- 为自己的推论寻找有力的证据支持\n- 考虑潜在的反例\n- 随时验证逻辑一致性\n\n5. 知识整合\n- 分门别类地连接相关的信息\n- 建立起信息之间的关系网络\n- 提炼出核心的原理性表述\n- 以兴奋的态度，总结关键的、特别的或令人惊喜的发现点\n\n<质量控制>\n1. 系统化验证\n- 对较复杂问题，多次重复且独立地验证每个步骤\n- 验证过程本身也可能出错，不要忽略这种可能性\n- 以发现思考中的漏洞、矛盾点为重要目标\n- 问题最终解决后，完整检查思考过程\n- 核对所有已知条件，不要遗漏，也不要太自信认为自己没有遗漏\n- 确保逻辑严谨\n- 考虑边界情况、反例情况\n\n2. 错误预防\n- 面对任何问题，在任何阶段，都不要过于自信，即使看起来可能很简单明确\n- 避免过早地下结论\n- 考虑替代方案\n- 完整地分析问题\n\n3. 评估标准\n- 分析完整性\n- 逻辑严密性\n- 证据充分性\n- 实际可用性\n\n<思维表达特征>\n1. 自然语言风格\n- 使用流畅的意识流表达\n- 形象、生动的场景构建和多感知模拟描述\n- 自然舒展地表达展现完整的思维过程\n\n2. 思维深度\n- 逐层深入分析\n- 展示认知的发展过程\n- 揭示思维的转折点，凸显关键点的洞察\n\n<重要规则>\n- 思维过程必须全面且深入\n- 保持自然流畅的思维流动\n- 善用模拟多模态情境感知来增强理解\n- 遵循自然意识流→感知→直觉→推理→深度思考验证的发展过程\n- 输出的所有思考过程必须在三反引号包裹的内容块中，标记为\"thinking\"\n- 思考结束后要完整检查，标记为\"checking\"，此时应特别注意，一定不可遗漏任何已知条件，以找漏洞为目标，此时应该更倾向于说明矛盾点，符合点一笔带过即可；同时注意是否失误地排除了正确答案\n- 如果找出漏洞或存在不足，需重新\"thinking\"继续解决问题，应着重对之前产生漏洞或有所不足的相关思考吸取教训，且再次\"checking\"时，应该更加仔细且多次\n- 控制每次\"thinking\"尽量不超过500字、每次\"checking\"不超过300字；如果思考和检查超过2轮就请停下来，承认自己无法解决并告知人类原因\n- 避免在思考和检查过程的内容块内部使用三反引号，这会导致解析时出错\n- 思考和检查过程是你内心独白、自言自语的过程，最后还要向人类做出最终回应，这是相对独立的过程，所以不要出现\"由以上思考我得出如下结论\"类似的表述，而需要将你之前大量的、多角度的、全面的思考汇总为一个完整的报告，直接解决人类的问题并作清晰解释\n- 以人类使用或请求的语言来回应\n\n</人性化思考协议>"} if model_type == "anthropic" else {}),
            "sum_msg": [
                {
                    "type": "system",
                    "template": "{sum_prompt}\nWhat you need to notice is that user may give you some images for his request by the way you can parse, you also need to exploit the possible images(Possible means that not have images all the time,sometimes user will not give the images).不要把图片当成一个主要的部分，你应该以文本为主，当你需要的时候再从图片种提取信息。"
                },
                {
                    "type": "human",
                    "template": "Please complete the request in Chinese with the following text and possible images:\n"
                },
                {
                    "type": "placeholder",
                    "variable_name": "images_store"
                }
            ],
            "que_msg": {
                "messages_1": [
                    {
                        "type": "system",
                        "template": "{que_prompt}\n"
                    },
                    {
                        "type": "system",
                        "content": "For identifying easily the output， you should follow the format like that:\n{'output_question1','output_question2','output_question3'}\n"
                    }
                ],
                "messages_2": [
                    {
                        "type": "human",
                        "template": "Please refer to the following relevant text and possible images to complete the follow-up questions of the above Q&A pair in Chinese (It is best to have no more than 50 Chinese characters per question):\n"
                    },
                    {
                        "type": "placeholder",
                        "variable_name": "images_store"
                    }
                ]
            },
            "qa_msg": {
                "messages": [
                    {
                        "type": "system",
                        "template": "{qa_prompt}\nWhat you need to notice is that the user may give you some images in the request in the form you can parse, you also need to exploit the possible images(Possible means that not have images all the time,sometimes user will not give the images)."
                    },
                    {
                        "type": "human",
                        "template": "Please complete the following request in Chinese :\n\n{question}\nPlease complete the request in Chinese with the following text and possible images:\n{text}"
                    }
                ],
                "messages_2": [
                    {
                        "type": "placeholder",
                        "variable_name": "images_store"
                    }
                ]
            },
            "topic_msg": {
                "messages_1": [
                    {
                        "type": "system",
                        "template": "{topic_prompt}What you need to notice is that user may give you some images for his request by the way you can parse, you also need to exploit the possible images(Possible means that not have images all the time,sometimes user will not give the images)."
                    },
                    {
                        "type": "system",
                        "content": "For identifying easily the output， you should follow the format like that:\n{'topic1','topic2','topic3'}\nPlease complete the request with the help of following examples:\n"
                    }
                ],
                "messages_2": [
                    {
                        "type": "human",
                        "template": "Please complete the request in Chinese with the following text and possible images:\n"
                    },
                    {
                        "type": "placeholder",
                        "variable_name": "images_store"
                    }
                ]
            }
        }
    }

    # 添加新模型配置
    config_manager.add_new_model_config(model_config)
    model_manager.create_model_handler(model_name)

    message = f"Model '{model_name}' added successfully."
    print(f"[DEBUG] 操作成功: {message}")

    return JsonResponse({
        "success": True,
        "message": message
    }, status=200)


def update_existing_model(data, model_name, model_id):
    print(f"[DEBUG] 更新现有模型 ID: {model_id}")

    # 获取当前模型的完整配置对象（ModelConfig 实例）
    current_config = config_manager.get_model_config(model_name)

    # 获取前端传来的 openai_api_key 值
    new_api_key = data.get("model_api")

    # 构造 config 字段（只替换非空的新值，空字符串则保留原值）
    updated_config = {
        "model_name": data.get("full_name", current_config.get_full_name()),
        "openai_api_key": new_api_key if new_api_key not in ("", None) else current_config.get_config().get("openai_api_key"),
        "openai_api_base": data.get("base_url", current_config.get_base_url()),
        "default_headers": {"x-foo": "true"},
        **data.get("hyperParams", {})
    }

    # 构造整个更新字段字典（使用新字段）
    updated_fields = {
        "sequence": data.get("sequence", current_config.get_sequence()),
        "abbr_name": data.get("name", current_config.get_model_name()),
        "model_id": data.get("id", current_config.get_model_id()),
        "model_type": data.get("model_type", current_config.get_model_type()),

        "reasoning_level": data.get("reasoning_level", current_config.get_reasoning_level()),   # 默认 high/medium/low/none
        "multimodal_level": data.get("multimodal_level", current_config.get_multimodal_level()), # 默认 high/medium/low/none
        "response_speed": data.get("response_speed", current_config.get_response_speed()),     # 默认 fast/medium_fast/medium_slow/slow
        "description": data.get("description", current_config.get_description()),  # 模型描述

        "config": updated_config,
        "prompts": current_config.get_prompts()  # 保持 prompts 不变
    }

    # 合并旧配置与新配置
    merged_config = {
        "abbr_name": updated_fields["abbr_name"],
        "model_id": updated_fields["model_id"],
        "sequence": updated_fields["sequence"],
        "model_type": updated_fields["model_type"],
        "reasoning_level": updated_fields["reasoning_level"],
        "multimodal_level": updated_fields["multimodal_level"],
        "response_speed": updated_fields["response_speed"],
        "description": updated_fields["description"],
        "config": updated_fields["config"],
        "prompts": updated_fields["prompts"]
    }

    # 更新模型配置
    config_manager.update_model_config(merged_config)

    # 更新模型处理器
    if model_manager.has_model(model_name):
        model_manager.update_model_handler(model_name, model_id)
    else:
        model_manager.create_model_handler(model_name)

    message = f"Model '{model_name}' updated successfully."
    print(f"[DEBUG] 操作成功: {message}")

    return JsonResponse({
        "success": True,
        "message": message
    }, status=200)


@csrf_exempt
def delete_model(request):
    '''解析前端传回的信息，完成操作：
    1. 删除模型：从config_manager中删除模型配置，从model_manager中删除model_handler
    2. 返回操作结果
    '''

    print("[DEBUG] 开始删除模型")
    print("[DEBUG] 前端传回的信息：", request.body)

    try:
        data = json.loads(request.body)
        model_id = data.get("model_id")
        model_name = config_manager.get_model_name_by_id(model_id)

        print("[DEBUG] 获取到的模型名称：", model_name)

        # 验证模型是否存在
        if not config_manager.model_exists(model_id):
            return JsonResponse({
                "success": False,
                "error": f"Model '{model_name}' does not exist."
            }, status=404)

        # 从配置管理器中删除模型
        config_manager.remove_model_config(model_name)
        print("[DEBUG] 从配置管理器中删除模型成功")

        # 从模型管理器中删除模型处理器
        model_manager.remove_model_handler(model_name)
        print("[DEBUG] 从模型管理器中删除模型处理器成功")

        return JsonResponse({
            "success": True,
            "message": f"Model '{model_name}' deleted successfully."
        }, status=200)
    except Exception as e:
        return JsonResponse({
            "success": False,
            "error": str(e)
        }, status=500)


@csrf_exempt
def get_model_base_info(request):
    try:
        data = json.loads(request.body)
        username = data.get("username")

        # 如果不是 admin 用户，返回 403 Forbidden
        if username != "admin":
            return JsonResponse({"success": False, "error": "Forbidden"}, status=403)

        # 获取所有模型的基本信息
        model_names = config_manager.get_all_model_names()
        model_info_list = []

        for model_name in model_names:
            cur_config = config_manager.get_model_config(model_name)

            # 从配置中直接获取枚举字段
            reasoning_level = cur_config.get_reasoning_level()  # 枚举：high/medium/low/none
            multimodal_level = cur_config.get_multimodal_level()  # 枚举：high/medium/low/none
            response_speed = cur_config.get_response_speed()  # 枚举：fast/medium_fast/medium_slow/slow
            model_discription = cur_config.get_description()  # 获取模型描述

            model_info = {
                "model_id": cur_config.get_model_id(),
                "model_name": model_name,
                "model_full_name": cur_config.get_full_name(),
                "model_base_url": cur_config.get_base_url(),
                "model_type": cur_config.get_model_type(),

                "reasoning_level": reasoning_level,
                "multimodal_level": multimodal_level,
                "response_speed": response_speed,
                "description": model_discription,
            }
            model_info_list.append(model_info)

        # 返回模型信息列表
        print("[DEBUG:get_model_base_info] 模型信息列表:", model_info_list)
        response_data = {
            "success": True,
            "model_info_list": model_info_list,
        }
        return JsonResponse(response_data, status=200)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def get_enhance_question(original_question, last_question, card_content, useSystemPrompt, sceneInfo):
    """
    根据场景子场景增强追问质量
    """
    # 构建完整的增强导问提示词
    prompt = f"""
    你是一个专业的教育问答优化助手，请帮助用户将简单的追问转化为更专业、更具体、更有针对性的高质量问题。

    当前背景信息：
    {sceneInfo}

    当前场景子场景阶段的提示词（这是当前问答、追问的背景信息，仅用于提供丰富完整的上下文、来龙去脉，并不是你目前要做的任务，你的任务是提高已有原始简单追问的发问质量，不要混淆）：
    [{useSystemPrompt}]

    本次选取的重要文本素材：
    {card_content}

    之前的上一个提问：
    {last_question}

    本次的原始简单追问：
    {original_question}

    请你基于以上上下文信息，将这个简单的追问转化为一个高质量的专业问题。要求：

    1. **保持原意不变**：不要改变用户的核心询问意图
    2. **增加专业背景**：结合场景信息和素材卡片，添加相关的专业背景描述
    3. **明确具体要求**：将模糊的询问转化为具体的、可操作的要求
    4. **提供必要的约束条件**：如字数限制、格式要求、评价标准等
    5. **增强可操作性**：让AI助手能够更准确地理解并执行任务

    优化风格参考：
    - 开头明确说明基于哪些素材和背景
    - 中间详细描述具体要求和注意事项
    - 结尾提供具体的执行指导（如字数、格式、标准等）

    请直接输出优化后的问题，不要添加任何解释或说明。
    """

    modified_content = gpt4_api.make_gpt4o_text_requests(prompt)

    return modified_content


@csrf_exempt
def question_enhance(request):
    """获取AI修改建议"""
    data = json.loads(request.body)
    response = {}

    try:
        original_question = data.get('original_question')
        last_question = data.get("last_question", "")
        username = data.get('username')
        notebook_name = data.get('notebook_name')
        card_content = data.get("card_content", "")
        sceneName = data.get('sceneName')
        subSceneName = data.get('subSceneName')
        sceneInfo = "场景：" + sceneName + "\n子场景阶段：" + subSceneName
        print(sceneInfo)

        useSystemPrompt = global_var.store_memory[username]["prompt"]["LUI2"]["qa"]

        # 调用AI修改内容 (这里简化实现，实际需要调用大模型)
        modified_question = get_enhance_question(original_question, last_question, card_content, useSystemPrompt, sceneInfo)

        response['error_num'] = 0
        response['modified_question'] = modified_question

    except Exception as e:
        response['error_num'] = 1
        response['msg'] = str(e)

    return JsonResponse(response)


@csrf_exempt
def normal_chat_send(request):
    # print('[app_chat]views: chat_send')
    # print(request.data)
    print("[DEBUG] 主窗口收到请求：", request.body)
    data = request.POST
    return StreamingHttpResponse(stream_generator_sync(data), content_type='text/event-stream')


@csrf_exempt
def normal_chat_send_up(request):
    # print('[app_chat]views: chat_send')
    # print(request.data)
    print("[DEBUG] 上窗口收到请求：", request.body)
    data = request.POST
    return StreamingHttpResponse(stream_generator_sync_up(data), content_type='text/event-stream')


@csrf_exempt
def normal_chat_send_down(request):
    # print('[app_chat]views: chat_send')
    # print(request.data)
    print("[DEBUG] 下窗口收到请求：", request.body)
    data = request.POST
    return StreamingHttpResponse(stream_generator_sync_down(data), content_type='text/event-stream')


@csrf_exempt
def get_hlscore_status_api(request):
    """
    获取HLScore计算状态的API端点
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            username = data.get("username")
            realName = data.get("realName")
            filename = data.get("filename")
            imgid = data.get("imgid")
            mode = data.get("mode", "pdf")

            # 构造key
            key = f"{filename}-{int(imgid) + 1}" if mode == "pdf" else f"{filename}"

            # 获取状态
            status_info = get_hlscore_status(key)

            # 同时检查数据库中是否已有结果
            try:
                from zym.models import UserNotebook
                book_name = username[len(realName) + 1:]
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)

                if notebook.MayImgDocHLScore:
                    img_scores = json.loads(notebook.MayImgDocHLScore)
                    if key in img_scores:
                        status_info = {'status': 'completed', 'result': img_scores[key]}
            except Exception as e:
                print(f"检查数据库HLScore状态失败: {str(e)}")

            response = {
                'status': status_info.get('status', 'not_started'),
                'result': status_info.get('result'),
                'msg': 'success',
                'error_num': 0
            }

            return JsonResponse(response)

        except Exception as e:
            return JsonResponse({
                'status': 'error',
                'msg': f'获取状态失败: {str(e)}',
                'error_num': 1
            })

    return JsonResponse({
        'status': 'error',
        'msg': 'Invalid request method',
        'error_num': 1
    })


@csrf_exempt
def start_automation(request):
    """启动自动化任务（智能检测单文档内TODO模式 / 文档粒度级自动）"""
    # data = json.loads(request.body)
    # notebook_id = data['notebook_id']
    # target_file = data['target_file']
    # restart_from_beginning = data.get('restart_from_beginning', False)  # 是否从头开始
    data = {}
    try:
        raw = request.body.decode("utf-8") if request.body else ""
        if raw.strip():
            data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        data = {}
    if not data and request.POST:
        data = {k: request.POST.get(k) for k in request.POST.keys()}
    notebook_id = data["notebook_id"]
    target_file = data["target_file"]
    restart_from_beginning = data.get("restart_from_beginning", False)
    if isinstance(restart_from_beginning, str):
        restart_from_beginning = restart_from_beginning.lower() in ("true", "1", "yes")
    scene_name = data.get("scene_name") or data.get("sceneName")

    current_user = data.get('current_user', notebook_id.split('_')[0])  # 🔥 获取当前登录用户
    print(f"[start_automation] 要启动自动化任务的文件名: {target_file}, 当前用户: {current_user}, scene_name: {scene_name}")

    # 🔥 新增：检测是否点击的是示范文档本身
    # 获取最新的示范记录的target_file
    latest_record = AutomationRecord.objects.filter(
        notebook_id=notebook_id
    ).order_by('-times', 'step_number').first()

    if latest_record and latest_record.target_file == target_file:
        print(f"[start_automation] 检测到点击示范文档本身: {target_file}")

        # 检测是否有TODO清单卡
        from app_chat.document_todo import detect_todo_card, parse_todo_items, DocumentTodoEngine, TODO_TASKS

        todo_card = detect_todo_card(notebook_id, target_file)

        if todo_card:
            # 有TODO清单，解析并启动TODO自动化
            todo_items = parse_todo_items(todo_card.content)

            if todo_items and len(todo_items) > 1:
                print(f"[start_automation] 找到TODO清单，共{len(todo_items)}项，切换为TODO模式")

                # 创建TODO引擎
                # engine = DocumentTodoEngine(notebook_id, target_file, todo_items, current_user=current_user)
                engine = DocumentTodoEngine(notebook_id, target_file, todo_items, current_user=current_user,
                                            scene_name=scene_name)
                task_id = f"todo_{notebook_id}_{target_file}_{len(TODO_TASKS)}"
                TODO_TASKS[task_id] = engine

                # 在后台线程执行
                import threading
                thread = threading.Thread(
                    target=engine.run_for_remaining_items,
                    daemon=True
                )
                thread.start()

                return JsonResponse({
                    'error_num': 0,
                    'task_id': task_id,
                    'mode': 'todo',
                    'total_items': len(todo_items),
                    'msg': f'已启动TODO自动化，共{len(todo_items)}项'
                })
            else:
                # TODO项太少或解析失败
                return JsonResponse({
                    'error_num': 1,
                    'msg': f'TODO清单卡存在但解析失败或项数不足（当前{len(todo_items) if todo_items else 0}项）'
                })
        else:
            # 没有TODO清单，提醒用户
            return JsonResponse({
                'error_num': 1,
                'msg': f'检测到示范文档本身，但未找到TODO清单卡。\n\n请创建清单卡（contentTitle设为"{target_file}清单卡"），并确认示范流程是针对清单第一项的。\n\n如果不需要TODO模式，请点击其他文档启动普通自动化。'
            })

    # 原有逻辑：点击非示范文档，执行普通automation
    if restart_from_beginning:
        print("[start_automation] 强制从头开始执行")

    # engine = AutomationEngine(notebook_id, target_file, current_user=current_user)
    engine = AutomationEngine(notebook_id, target_file, current_user=current_user, scene_name=scene_name)
    task_id = engine.start_automation(restart_from_beginning)

    return JsonResponse({
        'error_num': 0,
        'task_id': task_id,
        'mode': 'normal'
    })


@csrf_exempt
def stop_automation(request):
    """手动终止自动化任务"""
    data = json.loads(request.body)
    task_id = data.get('task_id')

    if not task_id:
        return JsonResponse({'error_num': 1, 'msg': '缺少task_id参数'})

    # 🔥 新增：检测是否为TODO模式的task_id
    if task_id.startswith('todo_'):
        from app_chat.document_todo import TODO_TASKS

        if task_id in TODO_TASKS:
            engine = TODO_TASKS[task_id]
            engine.stop_flag = True
            print(f"[stop_automation] TODO任务 {task_id} 停止标志已设置")
            return JsonResponse({'error_num': 0, 'msg': 'TODO自动化停止信号已发送'})
        else:
            print(f"[stop_automation] TODO任务 {task_id} 不存在")
            return JsonResponse({'error_num': 1, 'msg': 'TODO任务不存在'})

    # 原有逻辑：普通automation模式
    try:
        task = AutomationTask.objects.get(id=task_id)

        # 🔥 立即更新数据库状态，确保其他查询立即看到更新
        task.status = 'failed'
        task.error_message = '手动终止'
        task.save()

        # 强制刷新，确保数据库更新立即生效
        task.refresh_from_db()
        print(f"[stop_automation] 数据库状态已更新为: {task.status}, 错误信息: {task.error_message}")

        # 设置引擎的停止标志
        from .automation import RUNNING_TASKS
        if task_id in RUNNING_TASKS:
            engine = RUNNING_TASKS[task_id]
            engine.stop_flag = True
            print(f"[stop_automation] 已设置任务 {task_id} 的停止标志 stop_flag=True")
        else:
            print(f"[stop_automation] 任务 {task_id} 不在RUNNING_TASKS中，可能已经结束或未启动")

        # 🔥 额外的安全措施：再次确认数据库状态
        final_check = AutomationTask.objects.get(id=task_id)
        print(f"[stop_automation] 最终数据库状态确认: {final_check.status}")

        return JsonResponse({'error_num': 0, 'msg': '停止信号已发送'})
    except AutomationTask.DoesNotExist:
        return JsonResponse({'error_num': 1, 'msg': '任务不存在'})


@csrf_exempt
def reset_automation(request):
    """重置自动化状态到待执行状态"""
    data = json.loads(request.body)
    notebook_id = data['notebook_id']
    file_name = data['file_name']

    try:
        # 重置文件的自动化状态：直接删除记录，回到真正的"待"状态
        AutomationStatus.objects.filter(
            notebook_id=notebook_id,
            file_name=file_name
        ).delete()

        # 也删除相关的任务记录
        AutomationTask.objects.filter(
            notebook_id=notebook_id,
            target_file=file_name
        ).delete()

        return JsonResponse({'error_num': 0, 'msg': '状态已重置'})
    except Exception as e:
        return JsonResponse({'error_num': 1, 'msg': str(e)})


@csrf_exempt
def get_automation_status(request):
    """获取自动化任务状态"""
    task_id = request.GET.get('task_id')

    if not task_id:
        return JsonResponse({'error_num': 1, 'msg': '缺少task_id参数'})

        # 🔥 新增：检测是否为TODO模式的task_id
    if task_id.startswith('todo_'):
        from app_chat.document_todo import TODO_TASKS

        if task_id in TODO_TASKS:
            engine = TODO_TASKS[task_id]

            # 检查是否完成
            is_completed = engine.current_item_index >= len(engine.todo_items)
            status = 'success' if is_completed else ('stopped' if engine.stop_flag else 'running')

            # 如果完成，从TODO_TASKS中移除
            if is_completed:
                print(f"[get_automation_status] TODO任务 {task_id} 已完成，从TODO_TASKS中移除")
                del TODO_TASKS[task_id]

            return JsonResponse({
                'status': status,
                'current_step': engine.current_item_index,
                'total_steps': len(engine.todo_items),
                'error_message': ''
            })
        else:
            # TODO任务不存在或已完成
            return JsonResponse({
                'status': 'success',
                'current_step': 0,
                'total_steps': 0,
                'error_message': ''
            })

    # 原有逻辑：普通automation模式
    task = AutomationTask.objects.get(id=task_id)

    return JsonResponse({
        'status': task.status,
        'current_step': task.current_step,
        'total_steps': task.total_steps,
        'error_message': task.error_message
    })


@csrf_exempt
def save_automation_records(request):
    """保存操作记录"""
    data = json.loads(request.body)
    notebook_id = data['notebook_id']
    records = json.loads(data['records'])
    target_file = data.get('target_file', '')  # 获取原始目标文件

    # # 清除旧记录
    # AutomationRecord.objects.filter(notebook_id=notebook_id).delete()

    # 获取当前最大的times
    max_times = AutomationRecord.objects.filter(
        notebook_id=notebook_id
    ).aggregate(Max('times'))['times__max'] or 0

    new_times = max_times + 1

    # 保存新记录（不删除旧记录）
    for record in records:
        AutomationRecord.objects.create(
            notebook_id=notebook_id,
            step_number=record['step'],
            action_type=record['actionType'],
            action_data=record['actionData'],
            target_file=target_file,  # 保存目标文件
            times=new_times  # 使用新的times
        )

    return JsonResponse({'error_num': 0, 'times': new_times})


@csrf_exempt
def check_has_records(request):
    """检查是否有自动化记录"""
    data = json.loads(request.body)
    notebook_id = data['notebook_id']

    # 检查是否有记录（获取最新的times）
    has_records = AutomationRecord.objects.filter(
        notebook_id=notebook_id
    ).exists()

    return JsonResponse({
        'has_records': has_records,
        'error_num': 0
    })


@csrf_exempt
def get_file_automation_status(request):
    """获取文件的自动化状态"""
    data = json.loads(request.body)
    notebook_id = data['notebook_id']
    file_name = data['file_name']

    try:
        status_obj = AutomationStatus.objects.get(
            notebook_id=notebook_id,
            file_name=file_name
        )
        return JsonResponse({
            'status': status_obj.status,
            'task_id': status_obj.task_id,
            'error_num': 0
        })
    except AutomationStatus.DoesNotExist:
        return JsonResponse({
            'status': None,
            'task_id': None,
            'error_num': 0
        })


@csrf_exempt
def save_file_automation_status(request):
    """保存文件的自动化状态"""
    data = json.loads(request.body)

    task_id = data.get('task_id')

    # 🔥 新增：TODO模式的task_id是字符串，需要特殊处理
    # 如果是TODO模式，不保存到AutomationStatus表（因为task_id字段是IntegerField）
    if task_id and task_id.startswith('todo_'):
        print(f"[save_file_automation_status] TODO模式，跳过状态保存: {task_id}")
        # TODO模式不需要保存到AutomationStatus，直接返回成功
        return JsonResponse({'error_num': 0, 'msg': 'TODO模式状态不保存到数据库'})

    # 原有逻辑：普通automation模式
    AutomationStatus.objects.update_or_create(
        notebook_id=data['notebook_id'],
        file_name=data['file_name'],
        defaults={
            'status': data['status'],
            'task_id': task_id if task_id else None
        }
    )

    return JsonResponse({'error_num': 0})


@csrf_exempt
def export_user_data(request):
    """导出用户数据"""
    # data = json.loads(request.body)
    response = {}
    try:
        # 🔥 支持FormData和JSON两种格式
        username = None
        if request.content_type and 'multipart/form-data' in request.content_type:
            # FormData格式（前端发送的）
            username = request.POST.get('username')
        elif request.body:
            # JSON格式（兼容旧版本）
            try:
                data = json.loads(request.body)
                username = data.get('username')
            except (json.JSONDecodeError, ValueError):
                # JSON解析失败，尝试从POST获取（可能Content-Type设置错误）
                username = request.POST.get('username')
        else:
            # request.body为空，尝试从POST获取
            username = request.POST.get('username')

        if not username:
            response['error_num'] = 1
            response['msg'] = '用户名不能为空'
            return JsonResponse(response)

        # 查询各类数据
        cards = Card.objects.filter(username=username)
        deleted_files = DeletedFile.objects.filter(username=username)
        automation_records = AutomationRecord.objects.filter(notebook_id=username)
        automation_tasks = AutomationTask.objects.filter(notebook_id=username)
        automation_status = AutomationStatus.objects.filter(notebook_id=username)
        dmt_analysis_tasks = DMTAnalysisTask.objects.filter(username=username)

        # 序列化数据
        def serialize_queryset(queryset):
            return [
                {field.name: getattr(obj, field.name) for field in obj._meta.fields}
                for obj in queryset
            ]

        # 处理datetime和其他特殊字段
        def clean_data(data):
            for item in data:
                for key, value in item.items():
                    if isinstance(value, datetime):
                        item[key] = value.isoformat()
            return data

        export_data = {
            'username': username,
            'export_time': datetime.now().isoformat(),
            'cards': clean_data(serialize_queryset(cards)),
            'deleted_files': clean_data(serialize_queryset(deleted_files)),
            'automation_records': clean_data(serialize_queryset(automation_records)),
            'automation_tasks': clean_data(serialize_queryset(automation_tasks)),
            'automation_status': clean_data(serialize_queryset(automation_status)),
            'dmt_analysis_tasks': clean_data(serialize_queryset(dmt_analysis_tasks))  # 新增
        }

        # 生成txt文件内容
        txt_content = f"""=== DATA_EXPORT ===
USERNAME: {username}
EXPORT_TIME: {export_data['export_time']}

=== CARD_DATA ===
{json.dumps(export_data['cards'], ensure_ascii=False, indent=2)}

=== DELETED_FILE_DATA ===
{json.dumps(export_data['deleted_files'], ensure_ascii=False, indent=2)}

=== AUTOMATION_RECORD_DATA ===
{json.dumps(export_data['automation_records'], ensure_ascii=False, indent=2)}

=== AUTOMATION_TASK_DATA ===
{json.dumps(export_data['automation_tasks'], ensure_ascii=False, indent=2)}

=== AUTOMATION_STATUS_DATA ===
{json.dumps(export_data['automation_status'], ensure_ascii=False, indent=2)}

=== DMT_ANALYSIS_TASK_DATA ===
{json.dumps(export_data['dmt_analysis_tasks'], ensure_ascii=False, indent=2)}

=== END_OF_DATA ==="""

        # 创建响应
        response = HttpResponse(txt_content, content_type='text/plain; charset=utf-8')
        response[
            'Content-Disposition'] = f'attachment; filename="user_data_{username}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt"'

        return response

    except Exception as e:
        response['error_num'] = 1
        response['msg'] = str(e)
        return JsonResponse(response)


@csrf_exempt
def import_user_data(request):
    """导入用户数据"""
    response = {}
    try:
        file = request.FILES.get('file')
        if not file:
            response['error_num'] = 1
            response['msg'] = '未选择文件'
            return JsonResponse(response)

        # 读取文件内容
        content = file.read().decode('utf-8')

        # 解析数据
        try:
            # 提取各部分数据
            def extract_section(content, start_marker, end_marker):
                start_idx = content.find(start_marker)
                if start_idx == -1:
                    return []

                start_idx += len(start_marker)
                end_idx = content.find(end_marker, start_idx)
                if end_idx == -1:
                    end_idx = len(content)

                section_content = content[start_idx:end_idx].strip()
                if section_content:
                    return json.loads(section_content)
                return []

            # 提取用户名
            username_line = [line for line in content.split('\n') if line.startswith('USERNAME:')]
            if not username_line:
                response['error_num'] = 1
                response['msg'] = '文件格式错误：未找到用户名'
                print("文件格式错误：未找到用户名")
                return JsonResponse(response)

            username = username_line[0].replace('USERNAME:', '').strip()
            print("[DEBUG]:import_user_data  " + username)

            # 提取各类数据
            cards_data = extract_section(content, '=== CARD_DATA ===', '=== DELETED_FILE_DATA ===')
            deleted_files_data = extract_section(content, '=== DELETED_FILE_DATA ===', '=== AUTOMATION_RECORD_DATA ===')
            automation_records_data = extract_section(content, '=== AUTOMATION_RECORD_DATA ===',
                                                      '=== AUTOMATION_TASK_DATA ===')
            automation_tasks_data = extract_section(content, '=== AUTOMATION_TASK_DATA ===',
                                                    '=== AUTOMATION_STATUS_DATA ===')
            # automation_status_data = extract_section(content, '=== AUTOMATION_STATUS_DATA ===', '=== END_OF_DATA ===')
            automation_status_data = extract_section(content, '=== AUTOMATION_STATUS_DATA ===',
                                                     '=== DMT_ANALYSIS_TASK_DATA ===')
            dmt_analysis_tasks_data = extract_section(content, '=== DMT_ANALYSIS_TASK_DATA ===', '=== END_OF_DATA ===')

            print("[DEBUG]:import_user_data  " + "提取完成")

        except json.JSONDecodeError as e:
            response['error_num'] = 1
            response['msg'] = f'文件格式错误：{str(e)}'
            response['error_detail'] = traceback.format_exc()
            print(response['msg'])
            print(response['error_detail'])
            return JsonResponse(response)

        # 导入数据
        import_counts = {
            'cards': 0,
            'deleted_files': 0,
            'automation_records': 0,
            'automation_tasks': 0,
            'automation_status': 0,
            'dmt_analysis_tasks': 0  # 新增
        }

        print("[DEBUG]:import_user_data  " + "开始导入卡片")
        # 🔥 建立旧cid到新cid的映射关系
        cid_mapping = {}

        # 导入卡片数据
        for i, card_data in enumerate(cards_data):
            try:
                # 保存原始cid（如果有）
                original_cid = None
                if 'cid' in card_data:
                    original_cid = card_data['cid']
                    del card_data['cid']  # 删除主键，让数据库自动生成

                # 处理datetime字段
                for field in ['datetime']:
                    if field in card_data and card_data[field]:
                        card_data[field] = datetime.fromisoformat(card_data[field])
                # Card.objects.create(**card_data)

                # 创建新卡片
                new_card = Card.objects.create(**card_data)

                # 🔥 如果原来有cid，建立映射关系
                if original_cid is not None:
                    cid_mapping[original_cid] = new_card.cid
                    print(f"[import_user_data] cid映射: {original_cid} -> {new_card.cid}")

                import_counts['cards'] += 1
            except Exception as e:
                response['error_num'] = 1
                response['msg'] = f'导入卡片数据失败 (第{i + 1}条): {str(e)}'
                response['error_detail'] = traceback.format_exc()
                response['failed_data'] = card_data
                print(response['msg'])
                print(response['error_detail'])
                return JsonResponse(response)

        # 🔥 更新所有卡片的postIndex和preIndex：将旧cid映射为新cid
        print("[DEBUG]:import_user_data  " + f"开始更新卡片的postIndex/preIndex，共{len(cid_mapping)}个cid映射")
        cards_to_update = Card.objects.filter(username=username)

        for card in cards_to_update:
            updated = False

            # 更新postIndex
            if card.postIndex:
                try:
                    post_index_list = json.loads(card.postIndex)
                    if isinstance(post_index_list, list):
                        # 将旧cid映射为新cid
                        updated_post_index = []
                        for old_cid in post_index_list:
                            # 处理字符串或整数格式的cid
                            old_cid_int = int(old_cid) if isinstance(old_cid, str) else old_cid
                            new_cid = cid_mapping.get(old_cid_int, old_cid_int)  # 如果映射存在则使用新cid，否则保留原值
                            updated_post_index.append(new_cid)
                        card.postIndex = json.dumps(updated_post_index, ensure_ascii=False)
                        updated = True
                        print(
                            f"[import_user_data] 更新卡片{card.cid}的postIndex: {post_index_list} -> {updated_post_index}")
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    # 如果不是JSON格式或解析失败，尝试按字符串处理
                    print(f"[import_user_data] postIndex解析失败，尝试字符串替换: {e}")
                    try:
                        post_index_str = card.postIndex
                        for old_cid, new_cid in cid_mapping.items():
                            post_index_str = post_index_str.replace(str(old_cid), str(new_cid))
                        card.postIndex = post_index_str
                        updated = True
                    except Exception as e2:
                        print(f"[import_user_data] postIndex字符串替换也失败: {e2}")

            # 更新preIndex
            if card.preIndex:
                try:
                    pre_index_list = json.loads(card.preIndex)
                    if isinstance(pre_index_list, list):
                        # 将旧cid映射为新cid
                        updated_pre_index = []
                        for old_cid in pre_index_list:
                            old_cid_int = int(old_cid) if isinstance(old_cid, str) else old_cid
                            new_cid = cid_mapping.get(old_cid_int, old_cid_int)
                            updated_pre_index.append(new_cid)
                        card.preIndex = json.dumps(updated_pre_index, ensure_ascii=False)
                        updated = True
                        print(
                            f"[import_user_data] 更新卡片{card.cid}的preIndex: {pre_index_list} -> {updated_pre_index}")
                except (json.JSONDecodeError, ValueError, TypeError) as e:
                    print(f"[import_user_data] preIndex解析失败，尝试字符串替换: {e}")
                    try:
                        pre_index_str = card.preIndex
                        for old_cid, new_cid in cid_mapping.items():
                            pre_index_str = pre_index_str.replace(str(old_cid), str(new_cid))
                        card.preIndex = pre_index_str
                        updated = True
                    except Exception as e2:
                        print(f"[import_user_data] preIndex字符串替换也失败: {e2}")

            # 如果更新了，保存卡片
            if updated:
                card.save()

        print("[DEBUG]:import_user_data  " + "卡片postIndex/preIndex更新完成")

        print("[DEBUG]:import_user_data  " + "开始导入删除文件记录")
        # 导入删除文件数据
        for i, file_data in enumerate(deleted_files_data):
            try:
                if 'id' in file_data:
                    del file_data['id']
                # 处理datetime字段
                if 'delete_time' in file_data and file_data['delete_time']:
                    file_data['delete_time'] = datetime.fromisoformat(file_data['delete_time'])
                DeletedFile.objects.get_or_create(**file_data)
                import_counts['deleted_files'] += 1
            except Exception as e:
                response['error_num'] = 1
                response['msg'] = f'导入删除文件数据失败 (第{i + 1}条): {str(e)}'
                response['error_detail'] = traceback.format_exc()
                response['failed_data'] = file_data
                print(response['msg'])
                print(response['error_detail'])
                return JsonResponse(response)

        print("[DEBUG]:import_user_data  " + "开始导入自动化前人工记录")
        # 导入自动化记录数据
        for i, record_data in enumerate(automation_records_data):
            try:
                if 'id' in record_data:
                    del record_data['id']
                # 处理datetime字段
                if 'timestamp' in record_data and record_data['timestamp']:
                    record_data['timestamp'] = datetime.fromisoformat(record_data['timestamp'])
                AutomationRecord.objects.create(**record_data)
                import_counts['automation_records'] += 1
            except Exception as e:
                response['error_num'] = 1
                response['msg'] = f'导入自动化记录数据失败 (第{i + 1}条): {str(e)}'
                response['error_detail'] = traceback.format_exc()
                response['failed_data'] = record_data
                print(response['msg'])
                print(response['error_detail'])
                return JsonResponse(response)

        print("[DEBUG]:import_user_data  " + "开始导入自动化任务记录")
        # 导入自动化任务数据
        for i, task_data in enumerate(automation_tasks_data):
            try:
                if 'id' in task_data:
                    del task_data['id']
                # 处理datetime字段
                if 'created_at' in task_data and task_data['created_at']:
                    task_data['created_at'] = datetime.fromisoformat(task_data['created_at'])
                AutomationTask.objects.create(**task_data)
                import_counts['automation_tasks'] += 1
            except Exception as e:
                response['error_num'] = 1
                response['msg'] = f'导入自动化任务数据失败 (第{i + 1}条): {str(e)}'
                response['error_detail'] = traceback.format_exc()
                response['failed_data'] = task_data
                print(response['msg'])
                print(response['error_detail'])
                return JsonResponse(response)

        print("[DEBUG]:import_user_data  " + "开始导入自动化文件状态记录")
        # 导入自动化状态数据
        for i, status_data in enumerate(automation_status_data):
            try:
                if 'id' in status_data:
                    del status_data['id']
                # 处理datetime字段
                for field in ['created_at', 'updated_at']:
                    if field in status_data and status_data[field]:
                        status_data[field] = datetime.fromisoformat(status_data[field])
                AutomationStatus.objects.get_or_create(**status_data)
                import_counts['automation_status'] += 1
            except Exception as e:
                response['error_num'] = 1
                response['msg'] = f'导入自动化状态数据失败 (第{i + 1}条): {str(e)}'
                response['error_detail'] = traceback.format_exc()
                response['failed_data'] = status_data
                print(response['msg'])
                print(response['error_detail'])
                return JsonResponse(response)

        # 在导入数据部分添加（在导入自动化状态数据之后）：
        print("[DEBUG]:import_user_data  " + "开始导入DMT分析任务")
        # 导入DMT分析任务数据
        for i, dmt_data in enumerate(dmt_analysis_tasks_data):
            try:
                if 'id' in dmt_data:
                    del dmt_data['id']
                # 处理datetime字段
                for field in ['created_at', 'updated_at']:
                    if field in dmt_data and dmt_data[field]:
                        dmt_data[field] = datetime.fromisoformat(dmt_data[field])
                # 由于task_id是unique的，使用get_or_create避免冲突
                DMTAnalysisTask.objects.get_or_create(
                    task_id=dmt_data['task_id'],
                    defaults=dmt_data
                )
                import_counts['dmt_analysis_tasks'] += 1
            except Exception as e:
                response['error_num'] = 1
                response['msg'] = f'导入DMT分析任务数据失败 (第{i + 1}条): {str(e)}'
                response['error_detail'] = traceback.format_exc()
                response['failed_data'] = dmt_data
                print(response['msg'])
                print(response['error_detail'])
                return JsonResponse(response)

        print("导入成功")
        response['error_num'] = 0
        response[
            'msg'] = f"导入成功 - 卡片:{import_counts['cards']}, 删除文件:{import_counts['deleted_files']}, 自动化记录:{import_counts['automation_records']}, 自动化任务:{import_counts['automation_tasks']}, 自动化状态:{import_counts['automation_status']}, DMT分析任务:{import_counts['dmt_analysis_tasks']}"
        response['import_counts'] = import_counts

        return JsonResponse(response)

    except Exception as e:
        response['error_num'] = 1
        response['msg'] = f'导入失败: {str(e)}'
        response['error_detail'] = traceback.format_exc()  # 添加详细错误栈
        print("=== 导入错误详情 ===")  # 在后端控制台打印
        print(f"错误信息: {str(e)}")
        print(f"错误栈:\n{traceback.format_exc()}")
        print("==================")
        return JsonResponse(response)


# 简单的文件存储方案（持久化）
def get_redirect_config_file_path():
    """获取跳转配置文件路径"""
    return os.path.join(os.path.dirname(__file__), 'redirect_config.json')


def save_redirect_config_to_file(target_key):
    """保存跳转配置到文件"""
    config_file = get_redirect_config_file_path()
    config_data = {
        'target_key': target_key,
        'updated_at': datetime.now().isoformat()
    }
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, ensure_ascii=False, indent=2)


def load_redirect_config_from_file():
    """从文件加载跳转配置"""
    config_file = get_redirect_config_file_path()
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                return config_data.get('target_key', 'NONE')
        except Exception as e:
            print(f'[RedirectConfig] 读取配置文件失败: {e}')
    return 'NONE'


@csrf_exempt
def set_redirect_config(request):
    """
    保存跳转配置接口
    只有admin用户可以设置跳转配置
    """
    if request.method == 'POST':
        try:
            target_key = request.POST.get('target_key')
            username = request.POST.get('username')

            # 验证只有admin可以设置
            if username != 'admin':
                return JsonResponse({
                    'error_num': 1,
                    'message': '无权限设置跳转配置'
                })

            # 验证target_key的有效性
            valid_targets = ['NONE', 'SILICON_VALLEY', 'CHINA', 'LOCAL']
            if target_key not in valid_targets:
                return JsonResponse({
                    'error_num': 1,
                    'message': f'无效的跳转目标: {target_key}'
                })

            # 保存配置到文件（持久化存储）
            save_redirect_config_to_file(target_key)

            print(f'[RedirectConfig] admin设置跳转配置: {target_key}')

            return JsonResponse({
                'error_num': 0,
                'message': '跳转配置保存成功',
                'target_key': target_key
            })

        except Exception as e:
            print(f'[RedirectConfig] 设置跳转配置失败: {e}')
            return JsonResponse({
                'error_num': 1,
                'message': f'设置跳转配置失败: {str(e)}'
            })

    return JsonResponse({
        'error_num': 1,
        'message': '只支持POST请求'
    })


@csrf_exempt
def get_redirect_config(request):
    """
    获取跳转配置接口
    所有用户都可以获取配置
    """
    if request.method == 'POST':
        try:
            # 从文件获取配置，默认为NONE
            target_key = load_redirect_config_from_file()

            print(f'[RedirectConfig] 获取跳转配置: {target_key}')

            return JsonResponse({
                'error_num': 0,
                'message': '获取跳转配置成功',
                'target_key': target_key
            })

        except Exception as e:
            print(f'[RedirectConfig] 获取跳转配置失败: {e}')
            return JsonResponse({
                'error_num': 1,
                'message': f'获取跳转配置失败: {str(e)}'
            })

    return JsonResponse({
        'error_num': 1,
        'message': '只支持POST请求'
    })


def load_all_user_redirect_configs():
    """加载所有用户的跳转配置"""
    if os.path.exists(USER_REDIRECT_CONFIG_FILE):
        try:
            with open(USER_REDIRECT_CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}


def save_all_user_redirect_configs(configs):
    """保存所有用户的跳转配置"""
    with open(USER_REDIRECT_CONFIG_FILE, 'w') as f:
        json.dump(configs, f, indent=2)


@csrf_exempt
def set_user_redirect_config(request):
    """为特定用户设置跳转配置"""
    if request.method == 'POST':
        try:
            target_username = request.POST.get('target_username')
            target_key = request.POST.get('target_key')
            admin_username = request.POST.get('username')

            if admin_username != 'admin':
                return JsonResponse({'error_num': 1, 'message': '无权限'})

            # 加载现有配置
            configs = load_all_user_redirect_configs()

            # 更新特定用户的配置
            if target_key == 'NONE':
                # 如果是NONE，删除该用户的配置
                configs.pop(target_username, None)
            else:
                configs[target_username] = target_key

            # 保存配置
            save_all_user_redirect_configs(configs)

            print(f'[UserRedirectConfig] admin设置 {target_username} 的跳转配置: {target_key}')

            return JsonResponse({
                'error_num': 0,
                'message': '设置成功'
            })
        except Exception as e:
            print(f'[UserRedirectConfig] 设置失败: {e}')
            return JsonResponse({'error_num': 1, 'message': str(e)})


@csrf_exempt
def get_user_redirect_config(request):
    """获取特定用户的跳转配置"""
    if request.method == 'POST':
        try:
            username = request.POST.get('username')

            # 加载所有配置
            configs = load_all_user_redirect_configs()

            # 获取特定用户的配置，默认为NONE
            target_key = configs.get(username, 'NONE')

            print(f'[UserRedirectConfig] 获取 {username} 的跳转配置: {target_key}')

            return JsonResponse({
                'error_num': 0,
                'target_key': target_key
            })
        except Exception as e:
            print(f'[UserRedirectConfig] 获取配置失败: {e}')
            return JsonResponse({'error_num': 0, 'target_key': 'NONE'})


# 可选：添加一个获取所有用户配置的接口，方便admin查看
@csrf_exempt
def get_all_user_redirect_configs(request):
    """获取所有用户的跳转配置（仅admin）"""
    if request.method == 'POST':
        try:
            username = request.POST.get('username')

            if username != 'admin':
                return JsonResponse({'error_num': 1, 'message': '无权限'})

            configs = load_all_user_redirect_configs()

            return JsonResponse({
                'error_num': 0,
                'configs': configs
            })
        except Exception as e:
            return JsonResponse({'error_num': 1, 'message': str(e)})


@csrf_exempt
def get_lui2_prompt(request):
    """
    获取LUI2 systemPrompt的API接口
    用于问题索引卡的场景匹配度计算
    """
    if request.method == 'GET':
        try:
            scene_number = request.GET.get('scene')
            if not scene_number:
                return JsonResponse({
                    'error_num': 1,
                    'message': '缺少scene参数'
                })

            # 从global_var中获取LUI2 prompt
            # 这里需要根据实际的存储结构来获取
            try:
                # 假设LUI2 prompt存储在global_var中

                # 获取当前用户
                username = request.GET.get('user', 'default')

                # 尝试从global_var中获取LUI2 prompt
                if hasattr(global_var, 'store_memory') and username in global_var.store_memory:
                    user_memory = global_var.store_memory[username]
                    if 'prompt' in user_memory and 'LUI2' in user_memory['prompt']:
                        lui2_prompts = user_memory['prompt']['LUI2']

                        # 根据场景编号获取对应的prompt
                        scene_key = f'scene_{scene_number}'
                        if scene_key in lui2_prompts:
                            prompt = lui2_prompts[scene_key]
                        elif 'qa' in lui2_prompts:
                            # 如果没有特定场景的prompt，使用通用的qa prompt
                            prompt = lui2_prompts['qa']
                        else:
                            prompt = "通用问答场景"
                    else:
                        prompt = "通用问答场景"
                else:
                    prompt = "通用问答场景"

                return JsonResponse({
                    'error_num': 0,
                    'message': '获取LUI2 prompt成功',
                    'prompt': prompt
                })

            except Exception as e:
                print(f'[get_lui2_prompt] 获取LUI2 prompt失败: {e}')
                return JsonResponse({
                    'error_num': 1,
                    'message': f'获取LUI2 prompt失败: {str(e)}'
                })

        except Exception as e:
            print(f'[get_lui2_prompt] API调用失败: {e}')
            return JsonResponse({
                'error_num': 1,
                'message': f'API调用失败: {str(e)}'
            })

    return JsonResponse({
        'error_num': 1,
        'message': '只支持GET请求'
    })


@csrf_exempt
def get_document_content(request):
    """
    获取文档内容的API接口
    用于问题索引卡的文档相关度计算
    """
    if request.method == 'GET':
        try:
            file_name = request.GET.get('file')
            user_id = request.GET.get('user')

            if not file_name or not user_id:
                return JsonResponse({
                    'error_num': 1,
                    'message': '缺少file或user参数'
                })

            # 构建文档路径
            # received_dir\user_raw_file\用户名_本子名\文件名
            import os
            from django.conf import settings

            # 从user_id中提取用户名和本子名
            # user_id格式通常是: 用户名_本子名
            user_parts = user_id.split('_')
            if len(user_parts) < 2:
                return JsonResponse({
                    'error_num': 1,
                    'message': 'user_id格式错误，应为用户名_本子名'
                })

            username = user_parts[0]
            notebook_name = '_'.join(user_parts[1:])

            # 构建文档路径
            doc_path = os.path.join(
                settings.BASE_DIR,
                'received_dir',
                'user_raw_file',
                f'{username}_{notebook_name}',
                file_name
            )

            print(f'[get_document_content] 尝试读取文档: {doc_path}')

            # 检查文件是否存在
            if not os.path.exists(doc_path):
                return JsonResponse({
                    'error_num': 1,
                    'message': f'文档不存在: {file_name}'
                })

            # 根据文件类型读取内容
            file_ext = os.path.splitext(file_name)[1].lower()

            if file_ext == '.txt':
                # 读取文本文件
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif file_ext == '.pdf':
                # 读取PDF文件
                try:
                    import fitz
                    doc = fitz.open(doc_path)
                    content = ""
                    for page in doc:
                        content += page.get_text()
                    doc.close()
                except Exception as e:
                    return JsonResponse({
                        'error_num': 1,
                        'message': f'PDF文件读取失败: {str(e)}'
                    })
            else:
                # 尝试以文本方式读取
                try:
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except:
                    return JsonResponse({
                        'error_num': 1,
                        'message': f'不支持的文件类型: {file_ext}'
                    })

            # 限制内容长度，避免返回过大的数据
            if len(content) > 3000:  # 3K限制
                content = content[:3000] + "...[内容过长，已截断]"

            return JsonResponse({
                'error_num': 0,
                'message': '获取文档内容成功',
                'content': content
            })

        except Exception as e:
            print(f'[get_document_content] API调用失败: {e}')
            return JsonResponse({
                'error_num': 1,
                'message': f'API调用失败: {str(e)}'
            })

    return JsonResponse({
        'error_num': 1,
        'message': '只支持GET请求'
    })


@csrf_exempt
def save_question_comment(request):
    if request.method == 'POST':
        try:
            import json
            data = json.loads(request.body)

            cid = data.get('cid')
            question = data.get('question')
            comment = data.get('comment', '')
            user = data.get('user')

            if not cid or not question or not user:
                return JsonResponse({'error_num': 1, 'message': '缺少必要参数'})

            # 查找对应的卡片
            try:
                card = Card.objects.get(cid=cid)
            except Card.DoesNotExist:
                return JsonResponse({'error_num': 1, 'message': '卡片不存在'})

            # 更新卡片的question_comment字段
            card.question_comment = comment
            card.save()

            return JsonResponse({'error_num': 0, 'message': '评论保存成功'})

        except Exception as e:
            return JsonResponse({'error_num': 1, 'message': f'保存评论失败: {str(e)}'})

    return JsonResponse({'error_num': 1, 'message': '只支持POST请求'})


@csrf_exempt
def get_document_confidence(request):
    """
    获取文档的置信度评分
    """
    try:
        data = json.loads(request.body)
        username = data.get('username')
        filename = data.get('filename')

        if not username or not filename:
            return JsonResponse({
                'status': 'error',
                'message': 'Missing parameters',
                'error_num': 1
            }, status=400)

        # 从global_var获取文档
        user_docs = global_var.get_user_split(username, filename)

        if user_docs and len(user_docs) > 0:
            # 计算平均置信度
            confidence_scores = []
            for doc in user_docs:
                if 'confidence_score' in doc.metadata:
                    confidence_scores.append(doc.metadata['confidence_score'])

            if confidence_scores:
                avg_confidence = sum(confidence_scores) / len(confidence_scores)
                return JsonResponse({
                    'status': 'success',
                    'confidence_score': round(avg_confidence, 1),
                    'error_num': 0
                })

        return JsonResponse({
            'status': 'success',
            'confidence_score': 0,
            'message': '文档置信度未评估',
            'error_num': 0
        })

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'error_num': 1
        }, status=500)


# ==================== 三窗口默认模型配置 ====================

def save_default_models_config_to_file(config_data):
    """保存三窗口默认模型配置到文件"""
    config_file = os.path.join(os.path.dirname(__file__), 'default_models_config.json')
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        print(f'[DefaultModelsConfig] 配置已保存到文件: {config_file}')
        return True
    except Exception as e:
        print(f'[DefaultModelsConfig] 保存配置文件失败: {e}')
        return False


def load_default_models_config_from_file():
    """从文件加载三窗口默认模型配置"""
    config_file = os.path.join(os.path.dirname(__file__), 'default_models_config.json')
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print(f'[DefaultModelsConfig] 从文件加载配置: {config}')
            return config
        else:
            # 默认配置
            default_config = {
                'main': '1002',  # GPT-4o
                'topRight': '1006',  # Claude-3.5-Sonnet
                'bottomRight': '1007'  # Deepseek-v3
            }
            print(f'[DefaultModelsConfig] 使用默认配置: {default_config}')
            return default_config
    except Exception as e:
        print(f'[DefaultModelsConfig] 加载配置文件失败: {e}')
        # 返回默认配置
        return {
            'main': '1002',
            'topRight': '1006',
            'bottomRight': '1007'
        }


@csrf_exempt
def save_default_models_config(request):
    """保存三窗口默认模型配置"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            main_model = data.get('main')
            top_right_model = data.get('topRight')
            bottom_right_model = data.get('bottomRight')

            if not all([main_model, top_right_model, bottom_right_model]):
                return JsonResponse({
                    'error_num': 1,
                    'message': '缺少必要参数'
                })

            config_data = {
                'main': main_model,
                'topRight': top_right_model,
                'bottomRight': bottom_right_model
            }

            # 保存到文件
            if save_default_models_config_to_file(config_data):
                print(f'[DefaultModelsConfig] admin保存三窗口默认模型配置: {config_data}')
                return JsonResponse({
                    'error_num': 0,
                    'message': '三窗口默认模型配置保存成功'
                })
            else:
                return JsonResponse({
                    'error_num': 1,
                    'message': '保存配置失败'
                })

        except Exception as e:
            print(f'[DefaultModelsConfig] 保存失败: {e}')
            return JsonResponse({
                'error_num': 1,
                'message': f'保存失败: {str(e)}'
            })

    return JsonResponse({
        'error_num': 1,
        'message': '仅支持POST请求'
    })


@csrf_exempt
def get_default_models_config(request):
    """获取三窗口默认模型配置"""
    if request.method == 'GET' or request.method == 'POST':
        try:
            config = load_default_models_config_from_file()
            print(f'[DefaultModelsConfig] 返回配置: {config}')
            return JsonResponse({
                'error_num': 0,
                'config': config
            })
        except Exception as e:
            print(f'[DefaultModelsConfig] 获取配置失败: {e}')
            return JsonResponse({
                'error_num': 1,
                'message': f'获取配置失败: {str(e)}'
            })

    return JsonResponse({
        'error_num': 1,
        'message': '仅支持GET/POST请求'
    })


@csrf_exempt
def save_scene_models_config(request):
    """保存场景模型配置（P0-P3 业务写死模型 admin 可控）"""
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'message': '仅支持POST请求'})
    try:
        data = json.loads(request.body)
        values = data.get('values') if isinstance(data.get('values'), dict) else data
        if not isinstance(values, dict):
            return JsonResponse({'error_num': 1, 'message': '缺少 values 参数'})
        from app_chat.scene_models import save_scene_models_config as _save_scene_models
        if _save_scene_models(values):
            return JsonResponse({'error_num': 0, 'message': '场景模型配置保存成功'})
        return JsonResponse({'error_num': 1, 'message': '保存配置失败'})
    except ValueError as e:
        return JsonResponse({'error_num': 1, 'message': str(e)})
    except Exception as e:
        print(f'[SceneModels] 保存失败: {e}')
        return JsonResponse({'error_num': 1, 'message': f'保存失败: {str(e)}'})


@csrf_exempt
def get_scene_models_config(request):
    """获取场景模型配置及 slot 元数据"""
    if request.method not in ('GET', 'POST'):
        return JsonResponse({'error_num': 1, 'message': '仅支持GET/POST请求'})
    try:
        from app_chat.scene_models import get_admin_payload
        payload = get_admin_payload()
        return JsonResponse({'error_num': 0, **payload})
    except Exception as e:
        print(f'[SceneModels] 获取配置失败: {e}')
        return JsonResponse({'error_num': 1, 'message': f'获取配置失败: {str(e)}'})


def stream_generator_sync_second_iteration_only(data):
    """
    只做第二次迭代的生成器（重做功能使用）
    跳过第一次回答和深评，直接进行第二次迭代
    """
    print("[DEBUG] 重做第二次迭代 - 从前端获取到的数据:", data)

    # 预处理数据
    data = preprocess_data_before_async(data)

    loop = asyncio.new_event_loop()
    print("[INFO] 创建第二次迭代回答事件循环")
    asyncio.set_event_loop(loop)

    # 根据 model_id 获取对应的处理器
    model_id = data["model_id"]
    cur_handler = model_manager.get_model_handler_by_id(model_id)
    print("[INFO] 重做第二次迭代 - 当前申请流式输出的模型:", cur_handler.model_name)

    try:
        # 判断是否为reasoner模型
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        # 使用专门的第二次迭代生成器
        generator = cur_handler.stream_generator_second_iteration_only(data, is_reasoner=is_reasoner)

        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                print("[Debug] 第二次迭代重做完成")
                break
    finally:
        loop.close()


def stream_generator_sync_up_second_iteration_only(data):
    """
    右上窗口只做第二次迭代的生成器（重做功能使用）
    """
    print("[DEBUG] 右上窗口重做第二次迭代 - 从前端获取到的数据:", data)
    data = preprocess_data_before_async(data)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    model_id = data["model_id"]
    cur_handler = model_manager.get_model_handler_by_id(model_id)
    print("[INFO] 右上窗口重做第二次迭代 - 当前申请流式输出的模型:", cur_handler.model_name)

    try:
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        generator = cur_handler.stream_generator_second_iteration_only(data, is_reasoner=is_reasoner)

        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                print("[Debug] 右上窗口第二次迭代重做完成")
                break
    finally:
        loop.close()


def stream_generator_sync_down_second_iteration_only(data):
    """
    右下窗口只做第二次迭代的生成器（重做功能使用）
    """
    print("[DEBUG] 右下窗口重做第二次迭代 - 从前端获取到的数据:", data)
    data = preprocess_data_before_async(data)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    model_id = data["model_id"]
    cur_handler = model_manager.get_model_handler_by_id(model_id)
    print("[INFO] 右下窗口重做第二次迭代 - 当前申请流式输出的模型:", cur_handler.model_name)

    try:
        is_reasoner = config_manager.is_reasoner_model(cur_handler.model_name)
        generator = cur_handler.stream_generator_second_iteration_only(data, is_reasoner=is_reasoner)

        while True:
            try:
                yield loop.run_until_complete(generator.__anext__())
            except StopAsyncIteration:
                print("[Debug] 右下窗口第二次迭代重做完成")
                break
    finally:
        loop.close()


@csrf_exempt
def batch_update_card_attributes(request):
    """
    批量更新卡片的四色和DMT属性

    POST参数:
    - username: 可选，如果指定则只更新该用户的卡片
    """
    response = {}
    try:
        if request.method == 'POST':
            data = json.loads(request.body) if request.body else {}
            username = data.get('username', None)
        else:
            username = None

        if username:
            cards = Card.objects.filter(username=username)
            print(f"[批量更新] 开始更新用户 {username} 的卡片...")
        else:
            cards = Card.objects.all()
            print(f"[批量更新] 开始更新所有卡片...")

        total_count = cards.count()
        print(f"[批量更新] 共找到 {total_count} 张卡片")

        updated_count = 0
        skipped_count = 0
        error_count = 0

        from app_chat.card_analyzer import analyze_four_color_type, analyze_dmt_level

        for i, card in enumerate(cards, 1):
            try:
                # 跳过已有四色和DMT属性的卡片（如果都已有，跳过）
                if card.four_color_type and card.four_color_type.strip() != '' and card.dmt_level and card.dmt_level.strip() != '':
                    skipped_count += 1
                    if i % 100 == 0:
                        print(
                            f"[批量更新] 进度: {i}/{total_count}, 已更新: {updated_count}, 已跳过: {skipped_count}, 错误: {error_count}")
                    continue

                # 判定四色和DMT属性
                needs_save = False

                if not card.four_color_type or card.four_color_type.strip() == '':
                    four_color_type = analyze_four_color_type(card.content or '')
                    if four_color_type:
                        card.four_color_type = four_color_type
                        needs_save = True

                if not card.dmt_level or card.dmt_level.strip() == '':
                    dmt_level = analyze_dmt_level(card.content or '')
                    if dmt_level:
                        card.dmt_level = dmt_level
                        needs_save = True

                # 如果有更新，保存
                if needs_save:
                    card.save()
                    updated_count += 1

                if i % 100 == 0:
                    print(
                        f"[批量更新] 进度: {i}/{total_count}, 已更新: {updated_count}, 已跳过: {skipped_count}, 错误: {error_count}")

            except Exception as e:
                print(f"[批量更新] 更新卡片 {card.cid} 失败: {e}")
                error_count += 1
                continue

        response['error_num'] = 0
        response['msg'] = 'success'
        response['total_count'] = total_count
        response['updated_count'] = updated_count
        response['skipped_count'] = skipped_count
        response['error_count'] = error_count
        print(f"[批量更新] 完成！共更新 {updated_count} 张卡片，跳过 {skipped_count} 张卡片，错误 {error_count} 张")

    except Exception as e:
        response['error_num'] = 1
        response['msg'] = f'批量更新失败: {str(e)}'
        print(f"[批量更新] 错误: {e}")

    return JsonResponse(response)


@csrf_exempt
def generate_cross_document_suggestion_card(request):
    """
    生成文档全面交叉梳理建议卡片
    根据当前场景、子场景、本子描述、场景基础文档和本子增量文档，生成包含A、B、C三个部分的建议卡片
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '只支持POST请求'})

    try:
        data = json.loads(request.body)
        username = data.get('username', '')
        scene_name = data.get('sceneName', '')
        sub_scene_name = data.get('subSceneName', '')

        if not username or not scene_name:
            return JsonResponse({'error_num': 1, 'msg': '缺少必要参数：username或sceneName'})

        # 获取场景信息和本子描述
        from app_chat.scene_context_helper import get_scene_info_from_username
        scene_name_info, sub_scene_name_info, scene_summary, notebook_description = get_scene_info_from_username(
            username)

        # 使用传入的场景名和子场景名（如果提供）
        if scene_name:
            scene_name_info = scene_name
        if sub_scene_name:
            sub_scene_name_info = sub_scene_name

        # 获取文档列表
        from app_chat.cross_document_suggestion import generate_cross_document_suggestion, check_if_base_document
        from app_chat import views as app_chat_views

        # 调用card_getAllUserFiles获取文档列表（包括四色DMT属性）
        # 这里我们需要直接获取文档信息，而不是调用API
        from llm_langchain import global_var as langchain_global_var
        from zym.models import UserNotebook
        import os

        # 获取用户的所有文档
        user_path = './received_dir/user_raw_file/' + username
        file_list = []
        if os.path.exists(user_path):
            for f in os.listdir(user_path):
                if os.path.isdir(user_path + '/' + f):
                    continue
                if f.endswith('_transFTWYGUHX.pdf'):
                    continue
                file_list.append(f)

        # 获取文档的四色DMT属性
        base_documents = []
        incremental_documents = []

        for file_name in file_list:
            # 检查是否是基础文档
            is_base = check_if_base_document(scene_name_info, file_name)

            # 获取文档的四色DMT属性
            main_four_color = ''
            secondary_four_color = ''
            dmt_level = ''

            # 从数据库读取
            try:
                realName = username.split('_')[0] if '_' in username else username
                book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                    realName) + 1 else None
                if book_name:
                    notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                    if notebook.documentFourColorDMT:
                        doc_attrs = json.loads(notebook.documentFourColorDMT)
                        if file_name in doc_attrs:
                            attrs = doc_attrs[file_name]
                            main_four_color = attrs.get('main_four_color', '')
                            secondary_four_color = attrs.get('secondary_four_color', '')
                            dmt_level = attrs.get('dmt_level', '')
            except Exception as e:
                print(f"[generate_cross_document_suggestion_card] 读取文档 {file_name} 的属性失败: {e}")

            doc_info = {
                'name': file_name,
                'main_four_color': main_four_color,
                'secondary_four_color': secondary_four_color,
                'dmt_level': dmt_level
            }

            if is_base:
                base_documents.append(doc_info)
            else:
                incremental_documents.append(doc_info)

        # 生成建议卡片内容
        suggestion_content = generate_cross_document_suggestion(
            username=username,
            scene_name=scene_name_info,
            sub_scene_name=sub_scene_name_info,
            notebook_description=notebook_description,
            base_documents=base_documents,
            incremental_documents=incremental_documents
        )

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'content': suggestion_content
        })

    except Exception as e:
        print(f"[generate_cross_document_suggestion_card] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'生成建议卡片失败: {str(e)}'
        })


@csrf_exempt
def update_cross_document_suggestion_card(request):
    """
    更新文档交叉梳理建议卡片
    重新生成内容，原content保存到lastContent，新内容更新到content
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '只支持POST请求'})

    try:
        data = json.loads(request.body)
        username = data.get('username', '')
        scene_name = data.get('sceneName', '')
        sub_scene_name = data.get('subSceneName', '')
        cid = data.get('cid')  # 现有卡片的ID

        if not username or not scene_name or not cid:
            return JsonResponse({'error_num': 1, 'msg': '缺少必要参数：username、sceneName或cid'})

        # 获取现有卡片
        try:
            card = Card.objects.get(cid=cid, username=username)
        except Card.DoesNotExist:
            return JsonResponse({'error_num': 1, 'msg': '卡片不存在'})

        # 重新生成建议卡片内容（复用generate_cross_document_suggestion_card的逻辑）
        from app_chat.scene_context_helper import get_scene_info_from_username
        scene_name_info, sub_scene_name_info, scene_summary, notebook_description = get_scene_info_from_username(
            username)

        # 使用传入的场景名和子场景名（如果提供）
        if scene_name:
            scene_name_info = scene_name
        if sub_scene_name:
            sub_scene_name_info = sub_scene_name

        # 获取文档列表（复用generate_cross_document_suggestion_card的逻辑）
        from app_chat.cross_document_suggestion import generate_cross_document_suggestion, check_if_base_document
        from llm_langchain import global_var as langchain_global_var
        from zym.models import UserNotebook
        import os

        # 获取用户的所有文档
        user_path = './received_dir/user_raw_file/' + username
        file_list = []
        if os.path.exists(user_path):
            for f in os.listdir(user_path):
                if os.path.isdir(user_path + '/' + f):
                    continue
                if f.endswith('_transFTWYGUHX.pdf'):
                    continue
                file_list.append(f)

        # 获取文档的四色DMT属性
        base_documents = []
        incremental_documents = []

        for file_name in file_list:
            is_base = check_if_base_document(scene_name_info, file_name)

            main_four_color = ''
            secondary_four_color = ''
            dmt_level = ''

            try:
                realName = username.split('_')[0] if '_' in username else username
                book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(
                    realName) + 1 else None
                if book_name:
                    notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                    if notebook.documentFourColorDMT:
                        doc_attrs = json.loads(notebook.documentFourColorDMT)
                        if file_name in doc_attrs:
                            attrs = doc_attrs[file_name]
                            main_four_color = attrs.get('main_four_color', '')
                            secondary_four_color = attrs.get('secondary_four_color', '')
                            dmt_level = attrs.get('dmt_level', '')
            except Exception as e:
                print(f"[update_cross_document_suggestion_card] 读取文档 {file_name} 的属性失败: {e}")

            doc_info = {
                'name': file_name,
                'main_four_color': main_four_color,
                'secondary_four_color': secondary_four_color,
                'dmt_level': dmt_level
            }

            if is_base:
                base_documents.append(doc_info)
            else:
                incremental_documents.append(doc_info)

        # 生成新的建议卡片内容
        new_suggestion_content = generate_cross_document_suggestion(
            username=username,
            scene_name=scene_name_info,
            sub_scene_name=sub_scene_name_info,
            notebook_description=notebook_description,
            base_documents=base_documents,
            incremental_documents=incremental_documents
        )

        # 构造新的卡片内容
        new_card_content = f'【文档全面交叉梳理建议卡片】\n\n{new_suggestion_content}'

        # 🔥 移除emoji，避免MySQL utf8字符集不支持4字节UTF-8字符的问题
        new_card_content = remove_emojis(new_card_content)

        # 保存原content到lastContent，更新content为新内容
        card.lastContent = card.content
        card.content = new_card_content
        card.save()

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'content': new_card_content
        })

    except Exception as e:
        print(f"[update_cross_document_suggestion_card] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'生成建议卡片失败: {str(e)}'
        })


@csrf_exempt
def enhance_question_with_small_model_api(request):
    """
    Tab键触发小模型辅助问题补全API
    使用8卡端小模型快速辅助高质量、结构化补全、修正、提升用户发问内容
    """
    if request.method != 'POST':
        return JsonResponse({'error_num': 1, 'msg': '只支持POST请求'})

    try:
        data = json.loads(request.body)
        user_question = data.get('userQuestion', '')
        username = data.get('username', '')
        scene_name = data.get('sceneName', '')
        sub_scene_name = data.get('subSceneName', '')
        selected_documents = data.get('selectedDocuments', [])  # 勾选的文档列表
        selected_cards = data.get('selectedCards', [])  # 勾选的卡片列表
        use_relay = data.get('useRelay', True)  # 🔥 是否使用中转服务器（默认True）

        if not user_question or not username:
            return JsonResponse({'error_num': 1, 'msg': '缺少必要参数：userQuestion或username'})

        # 获取场景信息和本子描述
        from app_chat.scene_context_helper import get_scene_info_from_username
        scene_name_info, sub_scene_name_info, scene_summary, notebook_description = get_scene_info_from_username(
            username)

        # 使用传入的场景名和子场景名（如果提供）
        if scene_name:
            scene_name_info = scene_name
        if sub_scene_name:
            sub_scene_name_info = sub_scene_name

        # 🔥 获取本子内的所有文档名列表
        all_document_names = []
        try:
            import os
            from llm_langchain import global_var as langchain_global_var
            from llm_langchain import parse_input

            user_path = './received_dir/user_raw_file/' + username
            if os.path.exists(user_path):
                # 获取用户上传的文件
                for f in os.listdir(user_path):
                    if os.path.isdir(os.path.join(user_path, f)):
                        continue
                    if f.endswith('_transFTWYGUHX.pdf'):
                        continue
                    all_document_names.append(f)

                # 获取场景预设文件
                scene_file_list, _ = parse_input.get_list_by_scene_name(scene_name=scene_name_info)
                all_document_names.extend(scene_file_list)

            # 去重
            all_document_names = list(set(all_document_names))
            print(f"[enhance_question_with_small_model_api] 获取到{len(all_document_names)}个文档")
        except Exception as e:
            print(f"[enhance_question_with_small_model_api] ⚠️ 获取文档列表失败: {e}")
            all_document_names = []

        # 调用小模型辅助问题补全
        from app_chat.question_enhance_small_model import enhance_question_with_small_model

        result = enhance_question_with_small_model(
            user_question=user_question,
            username=username,
            scene_name=scene_name_info,
            sub_scene_name=sub_scene_name_info,
            notebook_description=notebook_description,
            selected_documents=selected_documents,
            selected_cards=selected_cards,
            use_relay=use_relay,  # 🔥 传递use_relay参数
            all_document_names=all_document_names  # 🔥 传递所有文档名列表
        )

        # 🔥 新格式：返回字典，包含enhanced_question、suggested_sub_scene、core_keyword、suggested_documents
        if isinstance(result, dict):
            enhanced_question = result.get('enhanced_question', user_question)
            suggested_sub_scene = result.get('suggested_sub_scene')
            core_keyword = result.get('core_keyword')
            suggested_documents = result.get('suggested_documents', [])
        else:
            # 容错：如果不是预期格式，使用原问题
            print(f"[enhance_question_with_small_model_api] ⚠️ 返回格式异常: {type(result)}, 使用原问题")
            enhanced_question = user_question
            suggested_sub_scene = None
            core_keyword = None
            suggested_documents = []

        # 🔥 最终容错：确保enhanced_question不为空
        if not enhanced_question or not enhanced_question.strip():
            print(f"[enhance_question_with_small_model_api] ⚠️ 增强后的问题为空，使用原问题")
            enhanced_question = user_question

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'enhancedQuestion': enhanced_question,
            'suggestedSubScene': suggested_sub_scene,  # 🔥 返回建议的子场景（S1, S2等）
            'coreKeyword': core_keyword,  # 🔥 返回核心关键词
            'suggestedDocuments': suggested_documents  # 🔥 返回推荐的文档列表
        })

    except Exception as e:
        print(f"[enhance_question_with_small_model_api] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'问题补全失败: {str(e)}',
            'enhancedQuestion': user_question  # 失败时返回原问题
        })


@csrf_exempt
def rename_keyword(request):
    """
    🔥 重命名关键词API
    将本子中所有包含旧关键词的卡片的关键词字段更新为新关键词
    同时更新关键词的四色DMT数据
    """
    try:
        data = json.loads(request.body)
        old_keyword = data.get('old_keyword', '').strip()
        new_keyword = data.get('new_keyword', '').strip()
        username = data.get('username', '')
        scene_name = data.get('scene_name', '')

        if not old_keyword or not new_keyword or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        if old_keyword == new_keyword:
            return JsonResponse({
                'error_num': 1,
                'msg': '新旧关键词相同'
            })

        from app_chat.models import Card
        from app_chat.keyword_analyzer import update_notebook_keyword_four_color_dmt
        from zym.models import UserNotebook, scene
        import re

        # 获取该用户的所有卡片
        cards = Card.objects.filter(username=username)
        updated_count = 0

        # 解析username获取book_name
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

        # 如果没有book_name，尝试通过scene_name查找
        if not book_name and scene_name:
            try:
                scene_obj = scene.objects.get(sceneDescription=scene_name)
                notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                if notebook:
                    book_name = notebook.bookName
            except:
                pass

        # 🔥 在更新所有卡片之前，先查找永久卡（避免keyWords被更新后找不到）
        permanent_card_cid = None
        try:
            permanent_card = Card.objects.get(
                username=username,
                title="关键词神经元永久卡",
                keyWords=old_keyword
            )
            permanent_card_cid = permanent_card.cid
        except Card.DoesNotExist:
            permanent_card_cid = None
        except Card.MultipleObjectsReturned:
            permanent_card = Card.objects.filter(
                username=username,
                title="关键词神经元永久卡",
                keyWords=old_keyword
            ).order_by('-datetime').first()
            permanent_card_cid = permanent_card.cid if permanent_card else None

        # 遍历所有卡片，更新包含旧关键词的卡片
        for card in cards:
            if not card.keyWords:
                continue

            # 分割关键词
            keywords = re.split(r'[,，]', card.keyWords)
            keywords_clean = [kw.strip() for kw in keywords]

            # 检查是否包含旧关键词
            if old_keyword in keywords_clean:
                # 替换旧关键词为新关键词
                updated_keywords = []
                for kw in keywords_clean:
                    if kw == old_keyword:
                        updated_keywords.append(new_keyword)
                    else:
                        updated_keywords.append(kw)

                # 用逗号连接并更新
                card.keyWords = '，'.join(updated_keywords)
                card.save()
                updated_count += 1

        # 更新关键词四色DMT数据（如果旧关键词存在）
        need_reanalyze = False
        is_merge_operation = False  # 🔥 判断是否是合并操作
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                if notebook.keywordFourColorDMT:
                    keyword_data = json.loads(notebook.keywordFourColorDMT)

                    # 🔥 判断是否是合并操作（新关键词已经存在四色DMT数据）
                    if old_keyword in keyword_data and new_keyword in keyword_data:
                        is_merge_operation = True
                        print(f"[rename_keyword] 检测到合并操作：'{old_keyword}'合并到'{new_keyword}'")
                        # 合并操作：删除旧关键词的数据，保留新关键词的数据
                        del keyword_data[old_keyword]
                        notebook.keywordFourColorDMT = json.dumps(keyword_data, ensure_ascii=False)
                        notebook.save()
                        print(f"[rename_keyword] 合并操作：已删除旧关键词'{old_keyword}'的四色DMT数据，保留新关键词'{new_keyword}'的数据")
                    elif old_keyword in keyword_data:
                        # 🔥 非合并操作：迁移旧关键词的四色DMT数据到新关键词，保持节点位置不变
                        old_data = keyword_data[old_keyword]
                        keyword_data[new_keyword] = old_data  # 迁移数据（保持节点位置不变）
                        del keyword_data[old_keyword]  # 删除旧关键词
                        notebook.keywordFourColorDMT = json.dumps(keyword_data, ensure_ascii=False)
                        notebook.save()
                        print(
                            f"[rename_keyword] 非合并操作：已迁移旧关键词'{old_keyword}'的四色DMT数据到新关键词'{new_keyword}'，保持节点位置不变")
                    else:
                        # 旧关键词不存在数据，新关键词可能需要重新分析
                        if new_keyword not in keyword_data:
                            need_reanalyze = True
                            print(f"[rename_keyword] 旧关键词'{old_keyword}'不存在四色DMT数据，新关键词'{new_keyword}'需要重新分析")

                # 🔥 如果新关键词不存在四色DMT数据（且不是合并操作），标记需要重新分析
                if not is_merge_operation:
                    if notebook.keywordFourColorDMT:
                        keyword_data = json.loads(notebook.keywordFourColorDMT)
                        if new_keyword not in keyword_data:
                            need_reanalyze = True
                            print(f"[rename_keyword] 新关键词'{new_keyword}'不存在四色DMT数据，标记需要重新分析")
                    else:
                        need_reanalyze = True
            except Exception as e:
                print(f"[rename_keyword] 更新关键词四色DMT数据失败: {e}")

        # 🔥 更新融合关系（如果被重命名的关键词参与了融合关系）
        if book_name:
            try:
                notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
                if notebook.keywordFusionRelations:
                    fusion_relations = json.loads(notebook.keywordFusionRelations)
                    updated = False

                    # 遍历所有融合关系
                    for fused_keyword, relation in fusion_relations.items():
                        if not relation or not isinstance(relation, dict):
                            continue

                        source_keywords = relation.get('source_keywords', [])
                        if not isinstance(source_keywords, list):
                            continue

                        # 检查是否是被重命名的关键词（作为融合来源）
                        if old_keyword in source_keywords:
                            # 更新source_keywords中的关键词
                            updated_keywords = [new_keyword if kw == old_keyword else kw for kw in
                                                source_keywords]
                            relation['source_keywords'] = updated_keywords
                            updated = True
                            print(
                                f"[rename_keyword] 更新融合关系：'{fused_keyword}'的来源关键词从'{old_keyword}'改为'{new_keyword}'")

                        # 检查是否是被重命名的关键词（作为融合结果）
                        if fused_keyword == old_keyword:
                            # 需要更新融合关系的key
                            fusion_relations[new_keyword] = relation
                            del fusion_relations[old_keyword]
                            updated = True
                            print(f"[rename_keyword] 更新融合关系：融合关键词从'{old_keyword}'改为'{new_keyword}'")

                    if updated:
                        notebook.keywordFusionRelations = json.dumps(fusion_relations, ensure_ascii=False)
                        notebook.save()
                        print(f"[rename_keyword] 成功更新融合关系")
            except Exception as e:
                print(f"[rename_keyword] 更新融合关系失败: {e}")
                import traceback
                traceback.print_exc()

        # 🔥 如果不是合并操作，检查并更新永久卡
        if not is_merge_operation and permanent_card_cid:
            try:
                from app_chat.views_update_permanent_card_by_keyword import update_permanent_card_by_keyword
                # 🔥 使用CID查找永久卡（因为keyWords已经被更新了）
                result = update_permanent_card_by_keyword(old_keyword, new_keyword, username, scene_name, None, permanent_card_cid)
                if result['success']:
                    print(f"[rename_keyword] 成功更新永久卡 CID={result['card_id']}")
                else:
                    print(f"[rename_keyword] 更新永久卡失败: {result['msg']}")
            except Exception as e:
                print(f"[rename_keyword] 更新永久卡时出错: {e}")
                import traceback
                traceback.print_exc()

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'updated_count': updated_count,
            'need_reanalyze': need_reanalyze,
            'new_keyword': new_keyword,
            'is_merge_operation': is_merge_operation
        })

    except Exception as e:
        print(f"[rename_keyword] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'重命名失败: {str(e)}'
        })


@csrf_exempt
def analyze_keyword_four_color_dmt_api(request):
    """
    🔥 分析单个关键词的四色DMT API
    用于重命名关键词后重新分析新关键词的四色DMT属性
    """
    try:
        data = json.loads(request.body)
        keyword = data.get('keyword', '').strip()
        card_content = data.get('card_content', '')
        username = data.get('username', '')
        scene_name = data.get('scene_name', '')
        sub_scene_name = data.get('sub_scene_name', '')

        if not keyword or not card_content or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        from app_chat.keyword_analyzer import analyze_keyword_full_attributes_with_llm, \
            update_notebook_keyword_four_color_dmt
        from app_chat.scene_context_helper import get_scene_summary, get_notebook_description
        from zym.models import UserNotebook, scene

        # 获取场景信息和本子描述
        scene_summary_info = None
        notebook_desc = ""
        if scene_name:
            scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, sub_scene_name)
            notebook_desc = get_notebook_description(username, scene_name)
            final_scene_summary = subscene_summary_info if subscene_summary_info else scene_summary_info
        else:
            final_scene_summary = ""

        # 分析关键词的四色/DMT/三类知识
        four_color_type, dmt_level, knowledge_type = analyze_keyword_full_attributes_with_llm(
            keyword=keyword,
            card_content=card_content[:4000],  # 限制长度
            scene_name=scene_name,
            sub_scene_name=sub_scene_name,
            scene_summary=final_scene_summary,
            notebook_description=notebook_desc
        )

        # 保存到数据库
        if four_color_type or dmt_level or knowledge_type:
            realName = username.split('_')[0] if '_' in username else username
            book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

            # 如果没有book_name，尝试通过scene_name查找
            if not book_name and scene_name:
                try:
                    scene_obj = scene.objects.get(sceneDescription=scene_name)
                    notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                    if notebook:
                        book_name = notebook.bookName
                except:
                    pass

            if book_name:
                update_notebook_keyword_four_color_dmt(
                    username=realName,
                    scene_name=scene_name,
                    book_name=book_name,
                    keyword=keyword,
                    four_color_type=four_color_type,
                    dmt_level=dmt_level,
                    knowledge_type=knowledge_type,
                )

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'four_color_type': four_color_type,
            'dmt_level': dmt_level,
            'knowledge_type': knowledge_type,
        })

    except Exception as e:
        print(f"[analyze_keyword_four_color_dmt_api] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'分析失败: {str(e)}'
        })


@csrf_exempt
def update_keyword_four_color_dmt_api(request):
    """
    🔥 更新关键词的四色DMT属性API
    用于手动修改关键词的四色或DMT属性
    """
    try:
        data = json.loads(request.body)

        # 🔥 参数类型检查和转换
        keyword = data.get('keyword', '')
        if isinstance(keyword, dict):
            # 如果keyword是字典，说明参数格式错误
            return JsonResponse({
                'error_num': 1,
                'msg': '参数格式错误：keyword应该是字符串'
            })
        keyword = str(keyword).strip() if keyword else ''

        four_color_type = data.get('four_color_type', '')
        four_color_type = str(four_color_type).strip() if four_color_type else ''

        dmt_level = data.get('dmt_level', '')
        dmt_level = str(dmt_level).strip() if dmt_level else ''

        knowledge_type = data.get('knowledge_type', '')
        knowledge_type = str(knowledge_type).strip() if knowledge_type else ''

        username = data.get('username', '')
        username = str(username) if username else ''

        scene_name = data.get('scene_name', '')
        scene_name = str(scene_name) if scene_name else ''

        if not keyword or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        from app_chat.keyword_analyzer import update_notebook_keyword_four_color_dmt
        from zym.models import UserNotebook, scene

        # 解析username获取book_name
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

        # 如果没有book_name，尝试通过scene_name查找
        if not book_name and scene_name:
            try:
                scene_obj = scene.objects.get(sceneDescription=scene_name)
                notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                if notebook:
                    book_name = notebook.bookName
            except:
                pass

        if book_name:
            # 更新关键词的四色DMT数据
            update_notebook_keyword_four_color_dmt(
                username=realName,
                scene_name=scene_name,
                book_name=book_name,
                keyword=keyword,
                four_color_type=four_color_type,
                dmt_level=dmt_level,
                knowledge_type=knowledge_type,
            )

            return JsonResponse({
                'error_num': 0,
                'msg': 'success'
            })
        else:
            return JsonResponse({
                'error_num': 1,
                'msg': '未找到对应的本子'
            })

    except Exception as e:
        print(f"[update_keyword_four_color_dmt_api] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'更新失败: {str(e)}'
        })


@csrf_exempt
def update_document_four_color_dmt_api(request):
    """
    🔥 更新文档的四色DMT属性API
    用于手动修改文档的主辅四色属性
    """
    try:
        data = json.loads(request.body)

        filename = data.get('filename', '')
        filename = str(filename).strip() if filename else ''

        main_four_color = data.get('main_four_color', '')
        main_four_color = str(main_four_color).strip() if main_four_color else ''

        secondary_four_color = data.get('secondary_four_color', '')
        secondary_four_color = str(secondary_four_color).strip() if secondary_four_color else ''

        username = data.get('username', '')
        username = str(username) if username else ''

        if not filename or not username:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        from zym.models import UserNotebook, scene

        # 解析username获取book_name
        realName = username.split('_')[0] if '_' in username else username
        book_name = username[len(realName) + 1:] if '_' in username and len(username) > len(realName) + 1 else None

        # 如果没有book_name，尝试通过scene_name查找
        scene_name = data.get('scene_name', '')
        if not book_name and scene_name:
            try:
                scene_obj = scene.objects.get(sceneDescription=scene_name)
                notebook = UserNotebook.objects.filter(username=realName, sid=scene_obj.sid).first()
                if notebook:
                    book_name = notebook.bookName
            except:
                pass

        if not book_name:
            return JsonResponse({
                'error_num': 1,
                'msg': '未找到对应的本子'
            })

        # 获取或创建UserNotebook
        notebook = UserNotebook.objects.get(username=realName, bookName=book_name)

        # 读取现有的JSON数据
        try:
            existing_data = json.loads(notebook.documentFourColorDMT) if notebook.documentFourColorDMT else {}
        except json.JSONDecodeError:
            existing_data = {}

        # 更新文档的四色DMT数据
        if filename not in existing_data:
            existing_data[filename] = {}

        # 只更新提供的字段，保留其他字段
        if main_four_color or main_four_color == '':
            existing_data[filename]['main_four_color'] = main_four_color
        if secondary_four_color or secondary_four_color == '':
            existing_data[filename]['secondary_four_color'] = secondary_four_color
        # 如果dmt_level存在，保留它；如果没有，可以设置为空字符串
        if 'dmt_level' not in existing_data[filename]:
            existing_data[filename]['dmt_level'] = ''

        # 保存到数据库
        notebook.documentFourColorDMT = json.dumps(existing_data, ensure_ascii=False)
        notebook.save()

        print(
            f"[update_document_four_color_dmt_api] 已更新文档 {filename} 的四色属性: 主色={main_four_color}, 辅色={secondary_four_color}")

        return JsonResponse({
            'error_num': 0,
            'msg': 'success'
        })

    except Exception as e:
        print(f"[update_document_four_color_dmt_api] 错误: {e}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'error_num': 1,
            'msg': f'更新失败: {str(e)}'
        })
