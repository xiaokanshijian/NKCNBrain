import contextvars
import functools
import traceback

from app_chat.core.models.model_factory import create_model

from app_chat.global_state import GLOBAL_STATE
from app_chat.core.construct import construct_data
from app_chat.config.config_manager import config_manager

from llm_langchain import global_var, util, normal_qa_new

from openai import OpenAI, AsyncOpenAI

# 导入clean_json_content函数
from app_chat.utils import clean_json_content, resolve_prompt_storage_key
from app_chat.socratic_probe import (
    apply_socratic_to_system_prompt,
    apply_socratic_to_user_text,
    resolve_socratic_probe_for_request,
)

import asyncio
import time
import json
import re
from anthropic import APITimeoutError

# 导入中断管理器
from app_chat.interrupt_manager import interrupt_manager

from langchain_core.prompts import SystemMessagePromptTemplate, HumanMessagePromptTemplate, ChatPromptTemplate, \
    MessagesPlaceholder, FewShotChatMessagePromptTemplate
from langchain_core.language_models import BaseChatModel, SimpleChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
)


def _memory_system_enabled(data) -> bool:
    # 测试阶段默认不注入；显式 true 才注入（写盘/Dream 不走此开关）
    flag = str(data.get("isMemorySystemUsed") or data.get("is_memory_system_used") or "false").strip().lower()
    return flag in ("true", "1", "yes", "on")


def _mem_log(msg: str, account: str = "", book_key: str = "") -> None:
    try:
        from app_chat.notebook_memory import log_notebook_memory
        log_notebook_memory(msg, account=account, book_key=book_key)
    except Exception:
        print(f"[notebook_memory] {msg}", flush=True)


def _inject_notebook_memory_prompt(base_prompt: str, data, constructed_data) -> str:
    """发问前注入本子/场景/USER 记忆块（可开关）。"""
    username = ""
    try:
        username = (constructed_data or {}).get("user_name") or (data or {}).get("username") or ""
    except Exception:
        pass
    if not _memory_system_enabled(data):
        _mem_log("注入跳过：前端关闭长短记忆", book_key=username)
        return base_prompt or ""
    try:
        from app_chat.notebook_memory import build_memory_injection_block
        scene = data.get("sceneName") or data.get("scene_name") or ""
        sub = data.get("subSceneName") or data.get("sub_scene_name") or ""
        q = constructed_data.get("message") or constructed_data.get("question") or data.get("message") or ""
        block = build_memory_injection_block(
            username, scene_name=scene, sub_scene=sub, question=str(q), enabled=True
        )
        if not block:
            _mem_log("注入为空块", book_key=username)
            return base_prompt or ""
        return (base_prompt or "") + "\n\n" + block
    except Exception as e:
        _mem_log(f"注入失败: {e}", book_key=username)
        return base_prompt or ""


def _schedule_memory_write_after_qa(data, constructed_data, user_q: str, assistant_a: str) -> None:
    """问答结束后后台写记忆；与前端「启用长短记忆」注入开关解耦（关注入仍可落盘）。
    仅主窗(left)写盘，避免三窗同轮各写一遍。
    """
    username = ""
    try:
        username = (constructed_data or {}).get("user_name") or (data or {}).get("username") or ""
    except Exception:
        username = ""
    if not (assistant_a or "").strip() or "API调用出错" in (assistant_a or ""):
        _mem_log("跳过写记忆：无有效回答", book_key=username)
        return
    win = str(data.get("windowId") or data.get("window_id") or "left").strip().lower()
    if win and win not in ("left", "main", ""):
        _mem_log(f"跳过写记忆：非主窗 windowId={win!r}", book_key=username)
        return
    try:
        from app_chat.notebook_memory import start_write_after_qa_background
        if not username:
            _mem_log("跳过写记忆：username 为空")
            return
        scene = data.get("sceneName") or data.get("scene_name") or ""
        sub = data.get("subSceneName") or data.get("sub_scene_name") or ""
        _mem_log(
            f"调度后台写记忆 scene={scene!r} q_len={len(user_q or '')} a_len={len(assistant_a or '')}",
            book_key=username,
        )
        start_write_after_qa_background(
            username, user_q or "", assistant_a or "", scene_name=scene, sub_scene=sub
        )
    except Exception as e:
        _mem_log(f"调度写记忆失败: {e}", book_key=username)


def _is_moonshot_fixed_sampling_model(model_full_name: str) -> bool:
    """
    Moonshot 部分推理模型采样参数固定，传错会直接 400。
    例如 kimi-k3: temperature 仅允许 1；top_p/n/penalty 也不可随意改。
    官方建议：省略这些参数，或 temperature=1。
    """
    name = (model_full_name or '').strip().lower()
    if not name:
        return False
    # kimi-k3 / kimi-k3-xxx（含 kimi-k3-dmx）；kimi-k2.7-code 等同系固定 temperature=1
    if name == 'kimi-k3' or name.startswith('kimi-k3'):
        return True
    if name == 'kimi-k2.7-code' or name.startswith('kimi-k2.7'):
        return True
    return False


def _filter_astream_hyper_para(model_abbr: str, model_config, hyper_para_dict: dict) -> dict:
    """
    过滤传给 langchain astream 的超参数。
    覆盖：Anthropic/Claude、Moonshot 固定采样（kimi-k3 等）、dmxapi 精简参数。
    """
    model_type = model_config.get_model_type()
    try:
        full_name = model_config.get_full_name() or ''
    except Exception:
        full_name = ''
    cur_config = model_config.get_config() or {}
    cur_base_url = cur_config.get('openai_api_base', '')
    model_name_lower = (model_abbr or '').lower()
    is_claude_model = ('claude' in model_name_lower) or (model_type == 'anthropic')

    if model_type == 'anthropic' or is_claude_model:
        filtered = {
            'temperature': hyper_para_dict.get('temperature', 0.7),
            'max_tokens': hyper_para_dict.get('max_tokens', 4096),
        }
        print(f'[INFO] Anthropic/Claude模型过滤后的超参数: {filtered}')
        return filtered

    if _is_moonshot_fixed_sampling_model(full_name) or _is_moonshot_fixed_sampling_model(model_abbr) or _is_moonshot_fixed_sampling_model(cur_config.get('model_name', '')):
        # 必须显式覆盖 ChatOpenAI 实例上可能残留的 presence_penalty=1 等非法值
        filtered = {
            'temperature': 1.0,
            'max_tokens': hyper_para_dict.get('max_tokens', 4096),
            'presence_penalty': 0,
            'frequency_penalty': 0,
            'top_p': 0.95,
            'n': 1,
        }
        print(f'[INFO] Moonshot固定采样模型过滤后的超参数: {filtered}')
        return filtered

    cur_use_async_stream = '.dmxapi.' in cur_base_url and model_type != 'anthropic'
    if cur_use_async_stream:
        filtered = {
            'temperature': hyper_para_dict.get('temperature', 0.6),
            'max_tokens': hyper_para_dict.get('max_tokens', 7192),
        }
        print(f'[INFO] dmxapi异步流超参数: {filtered}')
        return filtered

    print(f'[INFO] 传递给astream的超参数: {hyper_para_dict}')
    return hyper_para_dict


def _build_openai_chat_create_kwargs(
        full_name: str,
        messages,
        *,
        temperature,
        top_p,
        frequency_penalty,
        presence_penalty,
        n,
        max_tokens,
        stream: bool = True,
        timeout=None,
        include_sampling_extras: bool = True,
) -> dict:
    """组装 OpenAI chat.completions.create 参数，并对 Moonshot 固定采样模型做兼容。"""
    kwargs = {
        'model': full_name,
        'messages': messages,
        'max_tokens': max_tokens,
        'stream': stream,
    }
    if _is_moonshot_fixed_sampling_model(full_name):
        # 只显式传 temperature=1，避免 top_p / penalty 再触发 invalid_request_error
        kwargs['temperature'] = 1.0
        print(f"[Debug:create_chat_comopletion] {full_name} 固定采样：temperature=1.0（已省略 top_p/penalty/n）")
    else:
        kwargs['temperature'] = temperature
        if include_sampling_extras:
            kwargs['top_p'] = top_p
            kwargs['frequency_penalty'] = frequency_penalty
            kwargs['presence_penalty'] = presence_penalty
            kwargs['n'] = n
    if timeout is not None:
        kwargs['timeout'] = timeout
    return kwargs


# 创建一个单独的函数来处理问号和叹号的检测
def detect_special_markers(message):
    """
    检测用户消息中的特殊标记：
    - 三个问号 (???)
    - 两个问号 (??) 及可选的加号
    - 叹号 (!) 及可选的加号

    返回:
        dict: 包含检测结果的字典，包括：
            - has_triple_question_marks: 布尔值
            - has_double_question_marks: 布尔值
            - double_question_match: 匹配对象或None
            - plus_count: 双问号后的加号数量(0-3)
            - exclamation_match: 匹配对象或None
            - exclamation_plus_count: 叹号后的加号数量(0-3)
    """
    result = {
        'has_triple_question_marks': False,
        'has_double_question_marks': False,
        'double_question_match': None,
        'plus_count': 0,
        'exclamation_match': None,
        'exclamation_plus_count': 0
    }

    # 检测三个问号
    result['has_triple_question_marks'] = bool(
        re.search(r'(?<!\?)\?\?\?(?!\?)', message) or
        re.search(r'(?<!？)？？？(?!？)', message)
    )

    # 检测两个问号及可选的加号
    double_question_mark_match = re.search(r'(?<!\?)\?\?\+{0,3}(?!\?)|(?<!？)？？\+{0,3}(?!？)', message)
    result['has_double_question_marks'] = double_question_mark_match is not None
    result['double_question_match'] = double_question_mark_match

    # 如果找到双问号，计算加号数量
    if double_question_mark_match:
        match_string = double_question_mark_match.group(0)
        result['plus_count'] = match_string.count('+')

    # 检查叹号及可选的加号 - 在最后6个字符中搜索
    # exclamation_match = re.search(r'[!！]\+{0,3}', message[-6:] if len(message) >= 6 else message)
    # result['exclamation_match'] = exclamation_match

    # 如果找到叹号，计算加号数量
    # if exclamation_match:
    #     match_string = exclamation_match.group(0)
    #     result['exclamation_plus_count'] = match_string.count('+')

    return result


def _convert_message_to_dict(message: BaseMessage) -> dict:
    if isinstance(message, ChatMessage):
        message_dict = {"role": message.role, "content": message.content}
    elif isinstance(message, HumanMessage):
        message_dict = {"role": "user", "content": message.content}
    elif isinstance(message, AIMessage):
        message_dict = {"role": "assistant", "content": message.content}
        if "function_call" in message.additional_kwargs:
            message_dict["function_call"] = message.additional_kwargs["function_call"]
    elif isinstance(message, SystemMessage):
        message_dict = {"role": "system", "content": message.content}
    elif isinstance(message, FunctionMessage):
        message_dict = {
            "role": "function",
            "content": message.content,
            "name": message.name,
        }
    else:
        raise ValueError(f"Got unknown type {message}")
    if "name" in message.additional_kwargs:
        message_dict["name"] = message.additional_kwargs["name"]
    return message_dict


async def to_thread(func, /, *args, **kwargs):
    loop = asyncio.get_running_loop()
    ctx = contextvars.copy_context()
    func_call = functools.partial(ctx.run, func, *args, **kwargs)
    return await loop.run_in_executor(None, func_call)


class ModelHandler:
    def __init__(self, model_name: str = None):
        """
        初始化模型处理器。
        """
        self.model_name = model_name

        print("[Debug] 初始化模型处理器，模型名称:", model_name)

        self.model_with_langchain = self.initialize_model_with_langchain()
        self.model_original = self.initialize_model()
        self.latest_response = None  # 用于存储最新的响应

        self.qa_chain = None  # 用于存储QA链的实例
        self.sma_chain = None  # 用于存储SMA链的实例
        self.que_chain = None  # 用于存储追问问题链的实例
        self.topic_chain = None  # 用于存储主题链的实例
        self.rate_chain = None  # 用于存储红蓝融合链的实例
        self.card_chain = None  # 用于存储卡片链的实例

        self.init_qa()  # 初始化qa_chain
        self.init_suma()  # 初始化sma_chain
        self.init_que()  # 初始化que_chain
        self.init_topic()  # 初始化topic_chain
        self.init_rate()  # 初始化rate_chain
        self.init_card_suma()  # 初始化card_chain

    def _fix_unclosed_thinking_checking(self, text):
        """
        检测并修复未闭合的```thinking和```checking代码块

        如果发现```checking前的```thinking没有闭合，自动补上```

        Args:
            text: 要检测的文本

        Returns:
            修复后的文本
        """
        lines = text.split('\n')
        result_lines = []
        in_thinking = False
        in_checking = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # 检测```thinking
            if stripped == '```thinking':
                in_thinking = True
                in_checking = False
                result_lines.append(line)
                continue

            # 检测```checking
            if stripped == '```checking':
                # 如果之前的```thinking还未闭合，自动添加```闭合
                if in_thinking:
                    result_lines.append('```')
                    print(f"[修复] 在```checking前补充```闭合未闭合的thinking块")
                in_thinking = False
                in_checking = True
                result_lines.append(line)
                continue

            # 检测```（闭合）
            if stripped == '```':
                if in_thinking:
                    in_thinking = False
                elif in_checking:
                    in_checking = False
                result_lines.append(line)
                continue

            result_lines.append(line)

        # 如果文本结束时还有未闭合的块，补上```
        if in_thinking or in_checking:
            result_lines.append('```')
            print(f"[修复] 在文本结尾补充```闭合未闭合的{'thinking' if in_thinking else 'checking'}块")

        return '\n'.join(result_lines)

    def get_latest_response(self):
        return self.latest_response

    def initialize_model_with_langchain(self):
        """
        根据模型配置初始化实际模型实例。（走LangChain的流程）

        :return: 模型实例（如 OpenAIModel 或 HuggingFaceModel）。
        """
        # 优先获取模型配置
        model_config = config_manager.get_model_config(self.model_name)
        model_type = model_config.get_model_type()

        model_instance = create_model(model_type, model_config.get_config(), model_config.get_prompts())
        model_instance.initialize()  # 初始化模型

        return model_instance

    def get_model_langchain(self):  # 获取的是LangChain的模型
        return self.model_with_langchain

    def get_model(self):  # 获取的是OpenAI模型
        return self.model_original

    def initialize_model(self):
        '''
        走一般的流程，而不是LangChain的流程
        20250609:当前仅支持OpenAI的方式，后续通过工厂模式新增
        20250914:支持OpenAI和Anthropic的方式
        '''

        print("[Debug:initialize_client] 初始化模型客户端")
        print("[Debug:initialize_client] 模型名称:", self.model_name)
        # 获取模型api-key和base_url
        model_config = config_manager.get_model_config(self.model_name)
        cur_config = model_config.get_config()
        model_type = model_config.get_model_type()

        print("[INFO] 正在初始化模型客户端")
        print("[INFO] 模型名称:", self.model_name)
        print("[INFO] 模型类型:", model_type)

        if model_type == "anthropic":
            # 使用Anthropic原生客户端
            api_key = cur_config.get("anthropic_api_key", cur_config.get("openai_api_key"))
            base_url = cur_config.get("anthropic_api_base", cur_config.get("openai_api_base"))

            print("[INFO] Anthropic credential configured:", bool(api_key))
            print("[INFO] Anthropic BASE_URL:", base_url)

            # 返回AnthropicModel实例，包含原生客户端
            return self.model_with_langchain
        else:
            # 使用OpenAI客户端（原有逻辑）
            api_key = cur_config.get("openai_api_key")
            base_url = cur_config.get("openai_api_base")

            print("[INFO] Model credential configured:", bool(api_key))
            print("[INFO] BASE_URL:", base_url)

            return OpenAI(
                api_key=api_key,
                base_url=base_url,
                default_headers={"x-foo": "true"},
            )

    def create_anthropic_chat_completion(self, client, messages):
        '''
        为Anthropic模型创建聊天完成，返回异步生成器
        '''
        # 根据self.model_name获取其它参数
        model_config = config_manager.get_model_config(self.model_name)
        full_name = model_config.get_full_name()
        model_type = model_config.get_model_type()
        hyper_para = model_config.get_hyper_para()
        max_tokens = hyper_para.max_tokens
        temperature = hyper_para.temperature

        # print("[Debug:create_anthropic_chat_completion] 消息列表:", messages)
        print("[Debug:create_anthropic_chat_completion] 模型类型:", model_type)

        # 创建流式响应（直接传递原始消息，在方法内部转换格式）
        response = client.create_native_chat_completion(
            messages=messages,
            model=full_name,
            max_tokens=max_tokens,
            temperature=temperature
        )

        return response

    async def create_chat_completion(self, client, messages):
        '''
        构造完成prompt，并向模型发送请求
        支持OpenAI和Anthropic两种方式
        '''

        # print("[Debug:create_chat_comopletion] 创建聊天补全请求")
        # 根据self.model_name获取其它参数
        model_config = config_manager.get_model_config(self.model_name)
        full_name = model_config.get_full_name()
        model_type = model_config.get_model_type()

        # 获取超参数
        hyper_para = model_config.get_hyper_para()
        temperature = hyper_para.temperature
        max_tokens = hyper_para.max_tokens

        # 获取配置信息（用于判断是否需要异步客户端）
        cur_config = model_config.get_config()

        # print("[Debug:create_chat_comopletion] 消息列表:", messages)
        print("[Debug:create_chat_comopletion] 模型类型:", model_type)

        if model_type == "anthropic":
            # 使用Anthropic原生API
            if hasattr(client, 'get_native_client'):
                native_client = client.get_native_client()
            else:
                # 如果client就是AnthropicModel实例
                native_client = client.get_native_client()

            # # 转换消息格式
            # anthropic_messages, system_message = client.convert_messages_to_anthropic_format(messages)
            #
            # # 创建流式响应
            # response = await client.create_native_chat_completion(
            #     messages=anthropic_messages,
            #     model=full_name,
            #     max_tokens=max_tokens,
            #     temperature=temperature
            # )

            # 创建流式响应（直接传递原始消息，在方法内部转换格式）
            # 注意：create_native_chat_completion返回的是异步生成器，不需要await
            response = client.create_native_chat_completion(
                messages=messages,
                model=full_name,
                max_tokens=max_tokens,
                temperature=temperature
            )

            print("[Debug:create_chat_comopletion] Anthropic原生响应:", response)
            return response
        else:
            # 使用OpenAI API（原有逻辑）
            top_p = hyper_para.top_p
            frequency_penalty = hyper_para.frequency_penalty
            presence_penalty = hyper_para.presence_penalty
            n = hyper_para.n

            # 检查一下所有输入的参数
            # print("[Debug:create_chat_comopletion] 模型名称:", full_name)
            # print("[Debug:create_chat_comopletion] 温度:", temperature)
            # print("[Debug:create_chat_comopletion] top_p:", top_p)
            # print("[Debug:create_chat_comopletion] 频率惩罚:", frequency_penalty)
            # print("[Debug:create_chat_comopletion] 存在惩罚:", presence_penalty)
            # print("[Debug:create_chat_comopletion] 最大token数:", max_tokens)
            # print("[Debug:create_chat_comopletion] n:", n)

            # 清理messages中的特殊字符，防止JSON解析错误
            def clean_messages(msgs):
                cleaned = []
                for msg in msgs:
                    if isinstance(msg, dict):
                        cleaned_msg = {}
                        for key, value in msg.items():
                            if isinstance(value, str):
                                # 清理字符串中的特殊字符
                                cleaned_value = clean_json_content(value)
                                cleaned_msg[key] = cleaned_value
                            else:
                                cleaned_msg[key] = value
                        cleaned.append(cleaned_msg)
                    else:
                        cleaned.append(msg)
                return cleaned

            # cleaned_messages = messages
            # if full_name == "Baichuan-M2":
            #     cleaned_messages = clean_messages(messages)

            # 🔥 检测base_url，判断是否需要使用异步客户端
            # 某些渠道（如http://localhost:9999/v1）在同步客户端+to_thread+stream模式下会超时
            base_url = cur_config.get("openai_api_base", "")
            use_async_client = ".dmxapi." in base_url

            if use_async_client:
                # 对于特定渠道，使用AsyncOpenAI避免超时
                api_key = cur_config.get("openai_api_key")
                default_headers = cur_config.get("default_headers", {})

                async_client = AsyncOpenAI(
                    api_key=api_key,
                    base_url=base_url
                )

                # 🔥 直接使用异步客户端创建流式响应
                # 参考测试代码：AsyncOpenAI的create需要await，但不设置timeout参数
                # 让AsyncOpenAI使用默认的超时设置，避免在create阶段就超时
                create_kwargs = _build_openai_chat_create_kwargs(
                    full_name,
                    messages,
                    temperature=temperature,
                    top_p=top_p,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
                    n=n,
                    max_tokens=max_tokens,
                    stream=True,
                    include_sampling_extras=False,  # 原异步路径本身也不传 top_p/penalty
                )
                response = await async_client.chat.completions.create(**create_kwargs)
                print(f"[Debug:create_chat_comopletion] 使用AsyncOpenAI创建流式响应: {base_url}，返回流对象")
                return response
            else:
                # 原有逻辑：使用同步客户端 + to_thread（兼容其他渠道）
                create_kwargs = _build_openai_chat_create_kwargs(
                    full_name,
                    messages,
                    temperature=temperature,
                    top_p=top_p,
                    frequency_penalty=frequency_penalty,
                    presence_penalty=presence_penalty,
                    n=n,
                    max_tokens=max_tokens,
                    stream=True,
                    timeout=GLOBAL_STATE.timeout,
                    include_sampling_extras=True,
                )
                response = await asyncio.wait_for(
                    to_thread(
                        client.chat.completions.create,
                        **create_kwargs,
                    ),
                    timeout=GLOBAL_STATE.timeout
                )
                print("[Debug:create_chat_comopletion] 响应:", response)
                return response

    async def stream_generator(self, data, is_reasoner=False):
        from app_chat.views import chat_content, QS_QQ_base, time_out, chat_with_files_params

        constructed_data = construct_data(data)
        response_data = constructed_data["response_data"]
        username = constructed_data["user_name"]
        _prompt_store_key = constructed_data.get("prompt_storage_key") or constructed_data["writer"]
        now_turn_message = constructed_data["message"]

        markers = detect_special_markers(now_turn_message)
        has_double_question_marks = markers['has_double_question_marks']
        has_consecutive_question_marks = markers['has_triple_question_marks']

        chat_content[username][self.model_name] = ""
        print("[INFO] 数据解析完成，开始向模型发送请求")

        # 【新增】创建会话ID用于中断控制
        model_id = data.get("model_id", "unknown")
        # 在异步上下文中安全地获取任务名称
        try:
            task = asyncio.current_task()
            task_name = task.get_name() if task else str(int(time.time() * 1000))
        except RuntimeError:
            # 如果没有运行中的事件循环，使用时间戳
            task_name = str(int(time.time() * 1000))
        session_id = f"{username}_{model_id}_{task_name}"
        interrupt_event = interrupt_manager.create_session(session_id)

        try:
            # 初始化会话管理器
            GLOBAL_STATE.conversation_manager.get_conversation(
                username, self.model_name)

            # 公共变量
            start_time = time.time()
            new_response = ""
            content_field = "reasoning_content" if is_reasoner else "content"

            # 没有文件的情况
            system_prompt = config_manager.get_system_prompt(self.model_name)
            user_prompt = config_manager.get_user_prompt(self.model_name)

            if not constructed_data["file_list"]:
                try:
                    print("[INFO]", self.model_name, " 不勾选文件，发送消息: ", constructed_data["question"])
                    client = self.get_model()
                    print("[Debug:stream_generator] 客户端类型:", client.__class__.__name__)

                    # 系统提示处理
                    useSystemPrompt = ""
                    if data.get("noScene", "false") != "true":
                        # useSystemPrompt = "当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
                        useSystemPrompt = "当前的场景阶段提示：\n" + global_var.store_memory[_prompt_store_key]["prompt"]["LUI2"][
                            "qa"]
                    if has_consecutive_question_marks:
                        # useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                        useSystemPrompt = system_prompt + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                    if has_double_question_marks:
                        base_prompt = QS_QQ_base
                        if markers['plus_count'] == 1:
                            useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                        elif markers['plus_count'] == 2:
                            useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                        elif markers['plus_count'] == 3:
                            useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                        else:
                            useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"

                    useSystemPrompt = _inject_notebook_memory_prompt(useSystemPrompt, data, constructed_data)

                    # 语义反问：按「本轮原问题」读取共享判定，主辅窗口同轮一致
                    _req_window = str(data.get('windowId') or data.get('window_id') or '').strip()
                    _cur_msg = str(constructed_data.get('message') or constructed_data.get('question') or '')
                    _bound_msg = str(data.get('socraticBoundMessage') or data.get('originalQuestion') or _cur_msg)
                    _socratic = resolve_socratic_probe_for_request(
                        chat_with_files_params,
                        name_keys=[username, constructed_data.get('writer')],
                        window_id=_req_window,
                        current_message=_cur_msg,
                        bound_message=_bound_msg,
                        prefer_mode=str(data.get('mode') or 'normal'),
                    )
                    question_for_model = constructed_data["question"]
                    if _socratic.get('should_counter_ask') and _socratic.get('instruction'):
                        useSystemPrompt = apply_socratic_to_system_prompt(useSystemPrompt, _socratic)
                        question_for_model = apply_socratic_to_user_text(question_for_model, _socratic)
                        print(
                            f"[INFO] {self.model_name} 启用语义反问模式 window={_req_window} "
                            f"decision={_socratic.get('decision')} analysis={_socratic.get('analysis')}",
                            flush=True,
                        )
                    else:
                        print(
                            f"[INFO] {self.model_name} 本轮直接回答 window={_req_window} "
                            f"decision={_socratic.get('decision')} forced={_socratic.get('forced_by_streak')}",
                            flush=True,
                        )

                    # NKCN Skill 注入（优先本轮 params；组本不回退共享键）
                    try:
                        from app_chat.skill_router import apply_skills_to_system_prompt, pull_skill_injection
                        _inj = pull_skill_injection(
                            chat_with_files_params,
                            username,
                            constructed_data.get('writer'),
                        )
                        if _inj:
                            useSystemPrompt = apply_skills_to_system_prompt(useSystemPrompt, _inj)
                            print(f"[INFO] {self.model_name} 已注入 NKCN_ACTIVE_SKILLS", flush=True)
                    except Exception as _sk_inj_e:
                        print(f"[WARN] Skill 注入失败: {_sk_inj_e}", flush=True)

                    # 构造消息
                    if constructed_data["info_list"]:
                        constructed_data["info_list"].insert(0, {
                            "type": "text",
                            "text": question_for_model
                        })

                        # 将user_prompt也转换为消息格式
                        user_content = [{"type": "text", "text": user_prompt}] + constructed_data["info_list"]

                        messages = [
                            {"role": "system", "content": useSystemPrompt},
                            {"role": "user", "content": user_content}
                        ]
                    else:
                        messages = [
                            {"role": "system", "content": useSystemPrompt},
                            {"role": "user", "content": user_prompt + question_for_model}
                        ]

                    # 获取响应生成器
                    model_type = config_manager.get_model_config(self.model_name).get_model_type()
                    if model_type == "anthropic":
                        # Anthropic模型：直接调用非异步方法获取异步生成器
                        response_generator = self.create_anthropic_chat_completion(client, messages)
                    else:
                        # OpenAI模型需要await
                        response_generator = await self.create_chat_completion(client, messages)
                    print(f"[Debug:stream_generator] {self.model_name} 响应创建用时: {time.time() - start_time}秒")

                    # 处理流式响应
                    model_type = config_manager.get_model_config(self.model_name).get_model_type()

                    # 🔥 检测是否使用了AsyncOpenAI（某些渠道需要使用异步生成器）
                    cur_config = config_manager.get_model_config(self.model_name).get_config()
                    base_url = cur_config.get("openai_api_base", "")
                    use_async_stream = ".dmxapi." in base_url and model_type != "anthropic"

                    if model_type == "anthropic":
                        # 处理Anthropic原生流式响应
                        async for content in response_generator:
                            # 【新增】检查中断状态
                            if interrupt_manager.is_interrupted(session_id):
                                print(f"[INFO] {self.model_name} 响应被中断: {session_id}")
                                interrupt_data = {
                                    "type": "interrupt",
                                    "message": f"{self.model_name} 响应已被用户中断",
                                    "session_id": session_id,
                                    "model": self.model_name
                                }
                                yield json.dumps(interrupt_data, ensure_ascii=False)
                                return

                            if content is None:
                                continue

                            # 记录首次响应时间
                            if not new_response:
                                print(f"[INFO] {self.model_name} 响应时间: {time.time() - start_time}秒")

                            new_response += content
                            response_data['model'] = self.model_name
                            response_data['content'] = content
                            response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                            yield json.dumps(response_data, ensure_ascii=False)

                        # 🔥 新增：Anthropic模型检测并修复未闭合的thinking/checking代码块
                        fixed_response = self._fix_unclosed_thinking_checking(new_response)
                        if fixed_response != new_response:
                            print(f"[INFO] {self.model_name} 检测到未闭合的代码块，已自动修复")
                            fix_content = fixed_response[len(new_response):]
                            response_data['model'] = self.model_name
                            response_data['content'] = fix_content
                            response_data['session_id'] = session_id
                            yield json.dumps(response_data, ensure_ascii=False)
                            new_response = fixed_response
                    elif use_async_stream:
                        # 🔥 处理AsyncOpenAI流式响应（异步生成器）
                        reasoning_stop = False
                        async for chunk in response_generator:
                            # 【新增】检查中断状态
                            if interrupt_manager.is_interrupted(session_id):
                                print(f"[INFO] {self.model_name} 响应被中断: {session_id}")
                                interrupt_data = {
                                    "type": "interrupt",
                                    "message": f"{self.model_name} 响应已被用户中断",
                                    "session_id": session_id,
                                    "model": self.model_name
                                }
                                yield json.dumps(interrupt_data, ensure_ascii=False)
                                return

                            if not chunk.choices:
                                continue  # 如果没有choices，跳过

                            # 获取内容字段
                            if is_reasoner:
                                reasoning_content = getattr(chunk.choices[0].delta, "reasoning_content", None)
                                plain_content = getattr(chunk.choices[0].delta, "content", None)

                                if reasoning_content is not None:
                                    reasoning_stop = False
                                    content = "```" + reasoning_content if new_response == "" else reasoning_content
                                elif plain_content is not None:
                                    content = plain_content if reasoning_stop else "```" + plain_content
                                    reasoning_stop = True
                                else:
                                    continue
                            else:
                                content = getattr(chunk.choices[0].delta, content_field, None)
                                if content is None:
                                    continue

                            # 记录首次响应时间
                            if not new_response:
                                print(f"[INFO] {self.model_name} 响应时间: {time.time() - start_time}秒")

                            new_response += content
                            response_data['model'] = self.model_name
                            response_data['content'] = content
                            response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                            yield json.dumps(response_data, ensure_ascii=False)

                        # 🔥 新增：AsyncOpenAI模型检测并修复未闭合的thinking/checking代码块
                        fixed_response = self._fix_unclosed_thinking_checking(new_response)
                        if fixed_response != new_response:
                            print(f"[INFO] {self.model_name} 检测到未闭合的代码块，已自动修复")
                            fix_content = fixed_response[len(new_response):]
                            response_data['model'] = self.model_name
                            response_data['content'] = fix_content
                            response_data['session_id'] = session_id
                            yield json.dumps(response_data, ensure_ascii=False)
                            new_response = fixed_response
                    else:
                        # 处理OpenAI流式响应（同步生成器，原有逻辑）
                        reasoning_stop = False
                        for chunk in response_generator:
                            # 【新增】检查中断状态
                            if interrupt_manager.is_interrupted(session_id):
                                print(f"[INFO] {self.model_name} 响应被中断: {session_id}")
                                interrupt_data = {
                                    "type": "interrupt",
                                    "message": f"{self.model_name} 响应已被用户中断",
                                    "session_id": session_id,
                                    "model": self.model_name
                                }
                                yield json.dumps(interrupt_data, ensure_ascii=False)
                                return

                            if not chunk.choices:
                                continue  # 如果没有choices，跳过

                            # 获取内容字段
                            if is_reasoner:
                                reasoning_content = getattr(chunk.choices[0].delta, "reasoning_content", None)
                                plain_content = getattr(chunk.choices[0].delta, "content", None)

                                if reasoning_content is not None:
                                    reasoning_stop = False
                                    content = "```" + reasoning_content if new_response == "" else reasoning_content
                                elif plain_content is not None:
                                    content = plain_content if reasoning_stop else "```" + plain_content
                                    reasoning_stop = True
                                else:
                                    continue
                            else:
                                content = getattr(chunk.choices[0].delta, content_field, None)
                                if content is None:
                                    continue

                            # 记录首次响应时间
                            if not new_response:
                                print(f"[INFO] {self.model_name} 响应时间: {time.time() - start_time}秒")

                            new_response += content
                            response_data['model'] = self.model_name
                            response_data['content'] = content
                            response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                            yield json.dumps(response_data, ensure_ascii=False)

                        # 🔥 新增：OpenAI模型检测并修复未闭合的thinking/checking代码块
                        fixed_response = self._fix_unclosed_thinking_checking(new_response)
                        if fixed_response != new_response:
                            print(f"[INFO] {self.model_name} 检测到未闭合的代码块，已自动修复")
                            fix_content = fixed_response[len(new_response):]
                            response_data['model'] = self.model_name
                            response_data['content'] = fix_content
                            response_data['session_id'] = session_id
                            yield json.dumps(response_data, ensure_ascii=False)
                            new_response = fixed_response

                    # 保存完整响应
                    chat_content[username][self.model_name] = new_response

                except Exception as e:
                    print(self.model_name, f" API error: {e}, 详细错误信息:")
                    traceback.print_exc()
                    if time.time() - start_time > time_out and chat_content[username][self.model_name] == "":
                        print(self.model_name, f" API调用超时, 超时时间: {time.time() - start_time}秒")

                    error_content = f"{self.model_name} API调用出错"
                    chat_content[username][self.model_name] = error_content
                    response_data['model'] = self.model_name
                    response_data['content'] = error_content
                    yield json.dumps(response_data, ensure_ascii=False)

            # 有文件的情况
            else:
                constructed_params = chat_with_files_params[username]
                # print(self.model_name, " 勾选文件，发送消息: ", constructed_params["question_with_history"])
                # chat_sendParams 阶段写入的 question_with_history 不含 construct_data 内 NK2026 Gxx 等后处理；
                # 须以本轮 constructed_data["message"] 为准，并按当前模型拼接历史（与 construct_data 一致）。
                _msg_full = constructed_data["message"]
                if constructed_data["history"]:
                    effective_question = normal_qa_new.get_model_specific_histories2(
                        constructed_data["writer"],
                        _msg_full,
                        self.model_name,
                        constructed_data["rounds"],
                    )
                else:
                    effective_question = _msg_full
                _q_preview = effective_question[:500] + ("..." if len(effective_question) > 500 else "")
                print(self.model_name, " 勾选文件，发送消息(含后处理提问前500字): ", _q_preview)

                # 系统提示处理
                # qa_prompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
                qa_prompt = global_var.store_memory[_prompt_store_key]["prompt"]["LUI2"]["qa"]
                if has_consecutive_question_marks:
                    # qa_prompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                    qa_prompt = system_prompt + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                if has_double_question_marks:
                    base_prompt = QS_QQ_base
                    if markers['plus_count'] == 1:
                        qa_prompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                    elif markers['plus_count'] == 2:
                        qa_prompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                    elif markers['plus_count'] == 3:
                        qa_prompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                    else:
                        qa_prompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"

                qa_prompt = _inject_notebook_memory_prompt(qa_prompt, data, constructed_data)

                # 语义反问：按「本轮原问题」共享判定
                _req_window = str(data.get('windowId') or data.get('window_id') or '').strip()
                _cur_msg = str(
                    constructed_params.get('question')
                    or constructed_data.get('message')
                    or constructed_data.get('question')
                    or ''
                )
                _bound_msg = str(data.get('socraticBoundMessage') or data.get('originalQuestion') or _cur_msg)
                _socratic = resolve_socratic_probe_for_request(
                    chat_with_files_params,
                    name_keys=[username, constructed_data.get('writer')],
                    window_id=_req_window,
                    current_message=_cur_msg,
                    bound_message=_bound_msg,
                    prefer_mode=str(data.get('mode') or 'normal'),
                )
                if _socratic.get('should_counter_ask') and _socratic.get('instruction'):
                    qa_prompt = apply_socratic_to_system_prompt(qa_prompt, _socratic)
                    effective_question = apply_socratic_to_user_text(effective_question, _socratic)
                    print(
                        f"[INFO] {self.model_name} 启用语义反问模式(有文档) window={_req_window} "
                        f"decision={_socratic.get('decision')} analysis={_socratic.get('analysis')}",
                        flush=True,
                    )
                else:
                    print(
                        f"[INFO] {self.model_name} 本轮直接回答(有文档) window={_req_window} "
                        f"decision={_socratic.get('decision')} forced={_socratic.get('forced_by_streak')}",
                        flush=True,
                    )

                try:
                    from app_chat.skill_router import apply_skills_to_system_prompt, pull_skill_injection
                    # 优先用本轮已取出的 constructed_params，避免组本并发串键
                    _inj = pull_skill_injection(
                        chat_with_files_params,
                        username,
                        constructed_data.get('writer'),
                        params_hint=constructed_params,
                    )
                    if _inj:
                        qa_prompt = apply_skills_to_system_prompt(qa_prompt, _inj)
                        print(f"[INFO] {self.model_name} 已注入 NKCN_ACTIVE_SKILLS(有文档)", flush=True)
                except Exception as _sk_inj_e:
                    print(f"[WARN] Skill 注入失败(有文档): {_sk_inj_e}", flush=True)

                # 处理图像输入
                cur_config = config_manager.get_model_config(self.model_name)
                images_store = constructed_params["images_store"] if cur_config.is_allow_img() else []

                chain_input = {
                    "text": constructed_params["text"],
                    # "question": user_prompt + constructed_params["question_with_history"][self.model_name],
                    "question": user_prompt + effective_question,
                    "images_store": images_store,
                    "qa_prompt": qa_prompt
                }

                chain = self.qa_chain
                print(f"[INFO] QA链: {str(self.qa_chain)[:50]}")

                try:
                    for _, step in enumerate(chain.steps):
                        print(f"[INFO] 当前step的类型: {type(step)}")

                        # 模型处理步骤
                        if isinstance(step, (BaseChatModel, SimpleChatModel)):
                            print("[INFO] 勾选文件，开始流式输出")
                            # print(f"[INFO] chain_input: {chain_input}")

                            # 特殊处理reasoner模式
                            if is_reasoner:
                                # print(f"[INFO] chain_input_before: {chain_input}")
                                message_dicts = [_convert_message_to_dict(m) for m in chain_input.messages]
                                # print(f"[INFO] chain_input_after: {message_dicts}")

                                response_generator = await self.create_chat_completion(self.get_model(), message_dicts)
                                reasoning_stop = False

                                for chunk in response_generator:
                                    # 【新增】检查中断状态
                                    if interrupt_manager.is_interrupted(session_id):
                                        print(f"[INFO] {self.model_name} 响应被中断: {session_id}")
                                        interrupt_data = {
                                            "type": "interrupt",
                                            "message": f"{self.model_name} 响应已被用户中断",
                                            "session_id": session_id,
                                            "model": self.model_name
                                        }
                                        yield json.dumps(interrupt_data, ensure_ascii=False)
                                        return

                                    reasoning_content = getattr(chunk.choices[0].delta, "reasoning_content", None)
                                    plain_content = getattr(chunk.choices[0].delta, "content", None)

                                    if reasoning_content is not None:
                                        reasoning_stop = False
                                        content = "```" + reasoning_content if new_response == "" else reasoning_content
                                    elif plain_content is not None:
                                        content = plain_content if reasoning_stop else "```" + plain_content
                                        reasoning_stop = True
                                    else:
                                        continue

                                    new_response += content
                                    response_data['model'] = self.model_name
                                    response_data['content'] = content
                                    response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                                    yield json.dumps(response_data, ensure_ascii=False)

                            # 非reasoner模式处理
                            else:
                                async def stream_with_timeout(step, chain_input):
                                    # 获取异步生成器
                                    model_config = config_manager.get_model_config(self.model_name)
                                    hyper_para = model_config.get_hyper_para()
                                    hyper_para_dict = hyper_para.to_dict()

                                    # 🔥 调试：打印从配置文件读取的max_tokens
                                    print(f"[INFO] 从配置文件读取的max_tokens: {hyper_para_dict.get('max_tokens')}")

                                    model_type = model_config.get_model_type()
                                    filtered_hyper_para = _filter_astream_hyper_para(
                                        self.model_name, model_config, hyper_para_dict
                                    )

                                    # print("[INFO] 输入的内容:", chain_input)
                                    print("[INFO] 输入chain_input")

                                    # Anthropic模型重试机制：最多重试2次
                                    max_retries = 2 if model_type == "anthropic" else 0
                                    retry_count = 0

                                    while retry_count <= max_retries:
                                        try:
                                            async_stream = step.astream(chain_input, **filtered_hyper_para)
                                            while True:
                                                try:
                                                    # 【新增】在每次获取chunk前检查中断状态
                                                    if interrupt_manager.is_interrupted(session_id):
                                                        print(f"[INFO] {self.model_name} 流式响应被中断: {session_id}")
                                                        return

                                                    # 为每个块的生成设置超时
                                                    chunk = await asyncio.wait_for(
                                                        async_stream.__anext__(),  # 等待下一个异步块
                                                        timeout=time_out,  # 设置超时时间
                                                    )
                                                    yield chunk
                                                except StopAsyncIteration:
                                                    return  # 流式结束，成功
                                                except asyncio.TimeoutError:
                                                    print(
                                                        f"{self.model_name} 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                                                    raise APITimeoutError(f"{self.model_name} 流式块生成超时!")
                                        except Exception as e:
                                            if model_type == "anthropic" and retry_count < max_retries:
                                                retry_count += 1
                                                print(f"[INFO] Anthropic模型第{retry_count}次重试，错误: {e}")
                                                await asyncio.sleep(1)  # 等待1秒后重试
                                                continue
                                            else:
                                                raise e

                                async for chunk in stream_with_timeout(step, chain_input):
                                    # 【新增】最后一层中断检查
                                    if interrupt_manager.is_interrupted(session_id):
                                        print(f"[INFO] {self.model_name} 响应被中断: {session_id}")
                                        interrupt_data = {
                                            "type": "interrupt",
                                            "message": f"{self.model_name} 响应已被用户中断",
                                            "session_id": session_id,
                                            "model": self.model_name
                                        }
                                        yield json.dumps(interrupt_data, ensure_ascii=False)
                                        return

                                    content = chunk.content
                                    if content is None:
                                        continue

                                    if not new_response:
                                        print(f"{self.model_name} 响应时间: {time.time() - start_time}秒")

                                    new_response += content
                                    response_data['model'] = self.model_name
                                    response_data['content'] = content
                                    response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                                    yield json.dumps(response_data, ensure_ascii=False)

                        # 非流式步骤，直接调用 invoke
                        else:
                            print(f"{self.model_name} invoke")
                            chain_input = step.invoke(chain_input)
                            # yield chain_input  # 返回非流式步骤的输出

                    # 保存完整响应
                    chat_content[username][self.model_name] = new_response

                except Exception as e:
                    print(self.model_name, f" API error: {e}, 详细错误信息:")
                    traceback.print_exc()
                    if time.time() - start_time > time_out and chat_content[username][self.model_name] == "":
                        print(self.model_name, f" API调用超时, 超时时间: {time.time() - start_time}秒")

                    error_content = f"{self.model_name} API调用出错"
                    chat_content[username][self.model_name] = error_content
                    response_data['model'] = self.model_name
                    response_data['content'] = error_content
                    yield json.dumps(response_data, ensure_ascii=False)

        finally:
            # 【新增】清理会话资源
            interrupt_manager.cleanup_session(session_id)

        # 更新chat_history - 在流式响应完成后
        if new_response and new_response.strip() and "待融合文本段" not in now_turn_message:
            from app_chat.views import chat_history
            from copy import deepcopy

            # 确保用户的历史记录列表存在
            if username not in chat_history:
                chat_history[username] = []

            # 添加当前对话到历史记录
            chat_history[username].append({
                'filelist': deepcopy(constructed_data["file_list"]),
                'message': deepcopy(now_turn_message),
                'AImessage': deepcopy(new_response)
            })

            # 限制历史记录长度（保留最近3轮对话）
            rounds = int(data.get("rounds", 3))
            if len(chat_history[username]) > rounds:
                chat_history[username].pop(0)

            # 窗口紧时：先刷日记再压缩较早轮
            try:
                from app_chat.notebook_memory import maybe_compact_chat_history
                chat_history[username] = maybe_compact_chat_history(
                    username, chat_history[username], rounds
                )
            except Exception as _mem_c_e:
                _mem_log(f"压缩历史失败: {_mem_c_e}", book_key=username)

            print(f"[INFO] 已更新chat_history，当前历史记录数量: {len(chat_history[username])}")

            _schedule_memory_write_after_qa(
                data, constructed_data, now_turn_message, new_response
            )

    async def stream_generator_summa(self, data, is_reasoner=False):
        from app_chat.views import time_out
        username = data["username"]
        filename = data["filename"]
        fileNameList = data["fileNameList"]
        leftSelectList = data["leftSelectList"]
        rightSelectList = data["rightSelectList"]
        print(username + "请求获取文档摘要:" + filename + "，list info:")
        # file_list = fileNameList.split(',')
        try:
            file_list = json.loads(fileNameList)
        except json.JSONDecodeError:
            file_list = fileNameList.split(',')
        # [0, 2, 1, 0]
        left_select_list = [int(item) for item in leftSelectList.split(',')]
        right_select_list = [int(item) for item in rightSelectList.split(',')]
        print(file_list, left_select_list, right_select_list)

        # 【新增】创建会话ID用于中断控制
        model_id = data.get("model_id", "unknown")
        try:
            task = asyncio.current_task()
            task_name = task.get_name() if task else str(int(time.time() * 1000))
        except RuntimeError:
            task_name = str(int(time.time() * 1000))
        session_id = f"{username}_{model_id}_summa_{task_name}"
        interrupt_event = interrupt_manager.create_session(session_id)

        response_data = {}
        begin_time = time.time()
        all_segments = util.get_docs_all_split(username, file_list, left_select_list)
        print(f"执行 get_docs_all_split 耗时: {time.time() - begin_time}秒")
        begin_time = time.time()
        all_images, all_seqs, all_exts, _, _ = util.parse_image_in_segment_split(username, all_segments)
        print(f"执行 parse_image_in_segment_split 耗时: {time.time() - begin_time}秒")
        print(all_segments)

        mime_types = {
            'jpg': 'image/jpg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            # 添加其他需要支持的图片格式
        }

        # 🔥 先识别主文档索引，调整处理顺序
        main_doc_index = -1
        for i in range(len(file_list)):
            if file_list[i] == filename:
                main_doc_index = i
                break
        if main_doc_index == -1:
            main_doc_index = 0  # 默认第一个

        # 重排索引：主文档在前
        doc_indices = [main_doc_index] + [i for i in range(len(all_segments)) if i != main_doc_index]

        # —— 多本子增量综合摘要：勾选≥2 且其中增量文档≥2 时启用 ——
        scene_name = (
            data.get("sceneName")
            or data.get("scene_name")
            or data.get("scene")
            or ""
        )
        scene_name = str(scene_name).strip()
        use_multi_incremental = False
        incremental_names = []
        multi_main_name = filename
        multi_aux_names = []
        try:
            from app_chat.cross_document_suggestion import check_if_base_document
            if len(file_list) >= 2:
                for doc_name in file_list:
                    is_base = False
                    if scene_name:
                        is_base = check_if_base_document(scene_name, doc_name)
                    if not is_base:
                        incremental_names.append(doc_name)
                if len(incremental_names) >= 2:
                    use_multi_incremental = True
                    if filename in incremental_names:
                        multi_main_name = filename
                    else:
                        multi_main_name = incremental_names[0]
                    multi_aux_names = [n for n in incremental_names if n != multi_main_name]
                    print(
                        f"[Summary多增量] 启用综合摘要: main={multi_main_name}, "
                        f"aux={multi_aux_names}, scene={scene_name!r}"
                    )
                else:
                    print(
                        f"[Summary多增量] 未启用（增量数={len(incremental_names)}）: file_list={file_list}"
                    )
        except Exception as e:
            print(f"[Summary多增量] 判定失败，回退单文档模式: {e}")
            use_multi_incremental = False

        info_list = []

        # 🔥 读取每个文档的预处理md摘要（如果存在），添加到info_list开头
        import os

        def _read_presummary_bundle(doc_name: str) -> list:
            """返回该文档预处理章节摘要 + 图片分析摘要的 text 块列表。"""
            blocks = []
            if '_' not in username:
                return blocks
            realName = username.split('_')[0]
            bookName = username[len(realName) + 1:]
            doc_name_base = os.path.splitext(doc_name)[0]
            doc_ext = os.path.splitext(doc_name)[1].lstrip('.')
            md_file_path = (
                f'./received_dir/user_raw_file/{realName}_{bookName}/'
                f'pre_summary/{doc_name_base}_Presummary_{doc_ext}.md'
            )
            if os.path.exists(md_file_path):
                try:
                    with open(md_file_path, 'r', encoding='utf-8') as f:
                        md_content = f.read().strip()
                    if md_content:
                        blocks.append({
                            "type": "text",
                            "text": (
                                f"【文档 {doc_name} 的预处理章节分段摘要】\n"
                                f"（最终摘要输出时不要输出此处这些[页数]信息，而应该聚焦其中具体分段内容）\n"
                                f"{md_content}"
                            ),
                        })
                except Exception as e:
                    print(f"[stream_generator_summa] 读取预处理摘要失败 {doc_name}: {e}")
            if doc_name.lower().endswith('.pdf'):
                pre_image_summary_path = (
                    f'./received_dir/user_raw_file/{realName}_{bookName}/'
                    f'pre_image_summary/{doc_name_base}_PreImageSummary_pdf.md'
                )
                if os.path.exists(pre_image_summary_path):
                    try:
                        with open(pre_image_summary_path, 'r', encoding='utf-8') as f:
                            image_summary_content = f.read().strip()
                        if image_summary_content:
                            blocks.append({
                                "type": "text",
                                "text": (
                                    f"【文档 {doc_name} 的图片分析摘要】\n"
                                    f"（须与文本深度融合，图文约7:3，不要只输出页数）\n\n"
                                    f"{image_summary_content}"
                                ),
                            })
                    except Exception as e:
                        print(f"[stream_generator_summa] 读取图片摘要失败 {doc_name}: {e}")
            return blocks

        docs_for_presummary = incremental_names if use_multi_incremental else file_list
        for doc_name in docs_for_presummary:
            try:
                for block in _read_presummary_bundle(doc_name):
                    info_list.append(block)
                    print(f"[stream_generator_summa] 已添加文档 {doc_name} 的预处理类摘要块")
            except Exception as e:
                print(f"[stream_generator_summa] 读取文档 {doc_name} 的预处理摘要失败: {e}")
                continue

        # 多增量：正文已在 text 中按主/辅上限截断，勿再把全文/原图塞进 images_store（会重复约数万字+base64）
        if not use_multi_incremental:
            for idx in doc_indices:
                doc_name = file_list[idx] if idx < len(file_list) else ""
                doc_segments = all_segments[idx]
                text_docs = util.link_text([segment.page_content for segment in doc_segments[:len(doc_segments) - 1]])
                info_list.append({
                    "type": "text",
                    "text": text_docs
                })
                # for segment in doc_segments[:len(doc_segments)-1]:
                if global_var.store_memory[username]["model_num"] == 0 or global_var.store_memory[username][
                    "model_num"] == 4:
                    if len(all_images[idx]) != 0:
                        count = 0
                        for image in all_images[idx]:
                            count += 1
                            # 获取图片的后缀名（不带点'.'）
                            image_ext = all_exts[idx][count - 1].lower()
                            mime_type = mime_types.get(image_ext, 'image/jpeg')  # 默认使用'image/jpeg'
                            image_url = f"data:{mime_type};base64,{image}"
                            info_list.extend([
                                {
                                    "type": "text",
                                    "text": "This is the " + str(count) + "nd image of " + str(len(all_images[idx])) +
                                            ", its order in all images of this document should be"
                                            + str(all_seqs[idx][count - 1]) +
                                            ". If you use the image, use the order in all images of document as its reference."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": image_url
                                    }
                                }
                            ])
                info_list.append({
                    "type": "text",
                    "text": doc_segments[len(doc_segments) - 1].page_content
                })
        else:
            print(
                "[Summary多增量][篇幅] images_store 仅保留完整 Presummary/图片摘要，"
                "跳过全文段落与原图 base64（避免与 text 重复）"
            )
        images_list = [HumanMessage(content=info_list)]
        # text = ""
        print(f"[主文档判断] filename={filename}, file_list={file_list}, multi={use_multi_incremental}")

        def _cap_doc_text(doc_segments, max_chars: int, max_segs: int = None) -> str:
            segs = doc_segments if max_segs is None else doc_segments[:max_segs]
            content = util.link_text([segment.page_content for segment in segs])
            if len(content) > max_chars:
                return content[:max_chars] + "\n...(本文件后续正文已按篇幅截断，请优先结合该文件的预处理章节摘要)\n"
            return content

        # 🔥 重新组织文本：主文档在前，辅助文档在后
        main_text = ""
        auxiliary_text = ""

        if use_multi_incremental:
            name_to_idx = {file_list[i]: i for i in range(len(file_list))}
            main_idx = name_to_idx.get(multi_main_name, main_doc_index)
            main_segs = all_segments[main_idx]
            # 多增量正文上限（再压，配合去掉 images_store 全文重复）
            main_cap = 8000
            aux_cap = 4500 if len(multi_aux_names) <= 2 else 3000
            aux_max_segs = 8 if len(multi_aux_names) <= 2 else 6
            main_body = _cap_doc_text(main_segs, max_chars=main_cap)
            print(
                f"[Summary多增量][篇幅] 主《{multi_main_name}》正文={len(main_body)}字 "
                f"(上限{main_cap}, 段数={len(main_segs)})"
            )
            main_text = (
                f"【主文档】《{multi_main_name}》（用户点开的增量文档；定问题链与章节骨架）\n"
                f"{main_body}\n\n"
            )
            for aux_name in multi_aux_names:
                aux_idx = name_to_idx.get(aux_name)
                if aux_idx is None:
                    continue
                aux_segs = all_segments[aux_idx]
                aux_body = _cap_doc_text(aux_segs, max_chars=aux_cap, max_segs=aux_max_segs)
                print(
                    f"[Summary多增量][篇幅] 辅《{aux_name}》正文={len(aux_body)}字 "
                    f"(上限{aux_cap}, 段上限{aux_max_segs}, 实际段数={len(aux_segs)})"
                )
                auxiliary_text += (
                    f"【辅文档】《{aux_name}》（须在分文档要点与跨文档综合中点名引用，不可省略）\n"
                    f"{aux_body}\n\n"
                )
            aux_joined = " ".join(f"《{n}》" for n in multi_aux_names)
            text = (
                f"【重要提示】本次为多本子增量文档综合摘要。"
                f"主文档是《{multi_main_name}》，辅文档是{aux_joined}。"
                f"主辅已确定：用户点开的是主文档，其余勾选增量为辅文档；"
                f"你不得因内容长短或主题宏观程度而擅自对调主辅。"
                f"场景基础文档已忽略。请按综合摘要格式输出，"
                f"必须让读者看出多文档综合，禁止写成只像主文档单独摘要。\n\n"
                f"{main_text}{auxiliary_text}"
            )
            # info_list 里预处理摘要等文本块字数
            info_text_chars = 0
            info_text_blocks = 0
            for block in info_list:
                if isinstance(block, dict) and block.get("type") == "text":
                    info_text_chars += len(block.get("text") or "")
                    info_text_blocks += 1
            print(
                f"[Summary多增量][篇幅] text总输入={len(text)}字 "
                f"(主块={len(main_text)} 辅块合计={len(auxiliary_text)} 提示头≈{len(text)-len(main_text)-len(auxiliary_text)})；"
                f"images_store文本块={info_text_blocks}个 合计≈{info_text_chars}字；"
                f"约合计喂模型文档相关≈{len(text)+info_text_chars}字"
            )
        else:
            for i, doc_segments in enumerate(all_segments):
                # 🔥 判断当前文档是否是用户点开的主文档
                doc_name = file_list[i] if i < len(file_list) else ""
                is_main_doc = (doc_name == filename)
                print(f"[主文档判断] 文档{i}: doc_name={doc_name}, is_main_doc={is_main_doc}")

                if is_main_doc:
                    # 主文档：使用完整内容
                    doc_content = util.link_text([segment.page_content for segment in doc_segments])
                    main_text += "【主文档】（用户点开的文档，摘要应以此为主，占比80%以上）\n" + doc_content + "\n\n"
                else:
                    # 🔥 辅助文档：只使用前3段，避免干扰
                    doc_content_preview = util.link_text([segment.page_content for segment in doc_segments[:3]])
                    auxiliary_text += "【辅助文档】（仅供参考，已精简）\n" + doc_content_preview + "\n...(辅助文档内容已省略，请专注于主文档)\n\n"

            # 主文档在前，辅助文档在后
            # 🔥 在最前面添加明确的总指令，直接告知主文档名
            if main_text and auxiliary_text:
                text = f"【重要提示】本次摘要生成的核心对象是《{filename}》，这是用户点开查看的文档。请务必以该文档为主体（占比80%以上），生成的摘要应主要围绕该文档内容展开。其他文档仅作为辅助参考，切勿本末倒置！\n\n" + main_text + auxiliary_text
            else:
                text = main_text + auxiliary_text

        # 获取深度建议（如果存在）
        depth_suggestion = data.get("depth_suggestion", "")
        depth_suggestion_summary = ""  # 摘要建议
        depth_suggestion_topic = ""  # 主题建议

        # 解析深度建议（如果是summary任务，会包含两部分）
        if depth_suggestion and "【摘要建议】" in depth_suggestion:
            # 拆分摘要建议和主题建议
            parts = depth_suggestion.split("【主题关键词建议】")
            if len(parts) >= 2:
                depth_suggestion_summary = parts[0].replace("【摘要建议】", "").strip()
                depth_suggestion_topic = parts[1].strip()
            else:
                depth_suggestion_summary = depth_suggestion
        else:
            depth_suggestion_summary = depth_suggestion

        # 🔥 使用增强prompt（基于飞书启发）
        try:
            from llm_langchain.prompt_enhancement_config import get_enhanced_prompt
            prompt_type = "summary_multi_incremental" if use_multi_incremental else "summary"
            sum_prompt = get_enhanced_prompt(
                global_var.store_memory[username]["prompt"]["LUI1"]["summary"],
                prompt_type
            )
            print(f"[Summary] 使用增强prompt type={prompt_type}")
        except:
            sum_prompt = global_var.store_memory[username]["prompt"]["LUI1"]["summary"]
            print("[Summary] 使用原始prompt")

        chain_input = {
            # "sum_prompt": global_var.store_memory[username]["prompt"]["LUI1"]["summary"],
            "sum_prompt": sum_prompt,
            "text": text,
            "images_store": images_list
        }

        # 如果有深度建议，将其附加到sum_prompt中
        if use_multi_incremental:
            multi_fmt = (
                f"请综上，从【文档分工说明】写起，再输出【分文档要点】【跨文档综合】【整体摘要】，"
                f"然后再完成深度分析一、二、三。"
                f"**主辅已确定：主=《{multi_main_name}》，辅={aux_joined}；全文必须与此一致，禁止自行改换。**"
                f"**不可跳过【分文档要点】【跨文档综合】【整体摘要】；辅文档必须点名出现。**"
            )
            if depth_suggestion_summary:
                chain_input["sum_prompt"] = (
                    chain_input["sum_prompt"]
                    + "\n\n【摘要增强建议】（小模型提供，供你作为参考之一）：\n"
                    + depth_suggestion_summary
                    + "（多增量模式下：分文档要点优先忠实各文档自身结构；跨文档综合才做关联。"
                    + "原文有明确章节名时必须忠实原文）\n\n"
                    + multi_fmt
                )
            else:
                chain_input["sum_prompt"] = chain_input["sum_prompt"] + multi_fmt
        elif depth_suggestion_summary:
            chain_input["sum_prompt"] = chain_input[
                                            "sum_prompt"] + "\n\n【摘要增强建议】（小模型提供，供你作为参考之一）：\n" + depth_suggestion_summary + "（但注意如果原文有明确清晰的章节名信息，必须忠实原文，而非小模型的分章节建议；原文无直接明确的章节信息时，可采取小模型的分章节建议）\n\n请综上信息，先按如下格式完成基础摘要部分：\n【章节摘要】\n章节1名称xxx：\n...\n\n【整体摘要】\n...\n\n然后再按照前面的【深度理解增强要求】完成一、二、三的深度分析。\n**不可跳过【章节摘要】和【整体摘要】直接输出深度分析部分！基础和深度部分都必须有且按先后顺序**"
        else:
            # 即使没有深度建议，也要强调输出顺序
            chain_input["sum_prompt"] = chain_input[
                                            "sum_prompt"] + "请综上，先按如下格式完成基础摘要部分：\n【章节摘要】\n章节1名称xxx：\n...\n\n【整体摘要】\n...\n\n然后再按照前面的【深度理解增强要求】完成一、二、三的深度分析。\n**不可跳过【章节摘要】和【整体摘要】直接输出深度分析部分！基础和深度部分都必须有且按先后顺序**"

        chain = self.sma_chain
        print(f"[INFO] SUMMA链: {str(self.sma_chain)[:50]}")

        start_time = time.time()
        new_response = ""

        # 多增量模式：先写出固定标题行，保证格式可见
        multi_header = ""
        if use_multi_incremental:
            aux_joined = " ".join(f"《{n}》" for n in multi_aux_names)
            multi_header = f"【综合摘要】主文档：《{multi_main_name}》｜辅文档：{aux_joined}\n\n"
            new_response = multi_header
            response_data['model'] = self.model_name
            response_data['content'] = multi_header
            response_data['session_id'] = session_id
            yield json.dumps(response_data, ensure_ascii=False)

        try:
            for _, step in enumerate(chain.steps):
                print(f"[INFO] 当前step的类型: {type(step)}")

                # 模型处理步骤
                if isinstance(step, (BaseChatModel, SimpleChatModel)):
                    print("[INFO] 勾选文件，开始流式输出")
                    # 不再 print 完整 chain_input（含正文/base64，日志会爆）

                    # 特殊处理reasoner模式
                    if is_reasoner:
                        message_dicts = [_convert_message_to_dict(m) for m in chain_input.messages]

                        response_generator = await self.create_chat_completion(self.get_model(), message_dicts)
                        reasoning_stop = False

                        for chunk in response_generator:
                            reasoning_content = getattr(chunk.choices[0].delta, "reasoning_content", None)
                            plain_content = getattr(chunk.choices[0].delta, "content", None)

                            if reasoning_content is not None:
                                reasoning_stop = False
                                content = "```" + reasoning_content if new_response == multi_header else reasoning_content
                            elif plain_content is not None:
                                content = plain_content if reasoning_stop else "```" + plain_content
                                reasoning_stop = True
                            else:
                                continue

                            new_response += content
                            response_data['model'] = self.model_name
                            response_data['content'] = content
                            response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                            yield json.dumps(response_data, ensure_ascii=False)

                    # 非reasoner模式处理
                    else:
                        async def stream_with_timeout(step, chain_input):
                            # 获取异步生成器
                            model_config = config_manager.get_model_config(self.model_name)
                            hyper_para = model_config.get_hyper_para()
                            hyper_para_dict = hyper_para.to_dict()

                            # 过滤超参数（Anthropic / Moonshot 固定采样 / dmxapi）
                            filtered_hyper_para = _filter_astream_hyper_para(
                                self.model_name, model_config, hyper_para_dict
                            )

                            print("[INFO] 输入chain_input")

                            async_stream = step.astream(chain_input, **filtered_hyper_para)
                            while True:
                                try:
                                    # 为每个块的生成设置超时
                                    chunk = await asyncio.wait_for(
                                        async_stream.__anext__(),  # 等待下一个异步块
                                        timeout=time_out,  # 设置超时时间
                                    )
                                    yield chunk
                                except StopAsyncIteration:
                                    break  # 流式结束
                                except asyncio.TimeoutError:
                                    print(f"{self.model_name} 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                                    raise APITimeoutError(f"{self.model_name} 流式块生成超时!")

                        async for chunk in stream_with_timeout(step, chain_input):
                            content = chunk.content
                            if content is None:
                                continue

                            if not new_response or new_response == multi_header:
                                print(f"{self.model_name} 响应时间: {time.time() - start_time}秒")

                            new_response += content
                            response_data['model'] = self.model_name
                            response_data['content'] = content
                            response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                            yield json.dumps(response_data, ensure_ascii=False)


                # 非模型处理步骤
                else:
                    chain_input = step.invoke(chain_input)

        except Exception as e:
            print(f"{self.model_name}出错: {str(e)}, 详细错误信息:")
            traceback.print_exc()
            if time.time() - start_time > time_out and new_response == multi_header:
                print(f"{self.model_name} API调用超时, 超时时间: {time.time() - start_time}秒")

            error_content = f"{self.model_name}出错，参考文档内容偏多，或服务器繁忙！"

            response_data['model'] = self.model_name
            response_data['content'] = error_content
            yield json.dumps(response_data, ensure_ascii=False)
        finally:
            # 【新增】清理会话资源
            interrupt_manager.cleanup_session(session_id)

    async def stream_generator_rate(self, data, is_reasoner=False):
        from app_chat.views import time_out
        user_name = data["username"]
        text = data["content"]
        origin_real_name = data.get("originRealName") or data.get("origin_real_name")
        prompt_mem_key = resolve_prompt_storage_key(user_name, origin_real_name)

        # 【新增】创建会话ID用于中断控制
        model_id = data.get("model_id", "unknown")
        try:
            task = asyncio.current_task()
            task_name = task.get_name() if task else str(int(time.time() * 1000))
        except RuntimeError:
            task_name = str(int(time.time() * 1000))
        session_id = f"{user_name}_{model_id}_rate_{task_name}"
        interrupt_event = interrupt_manager.create_session(session_id)

        chain_input = {
            "rate": global_var.store_memory[prompt_mem_key]["prompt"]["LUI4"]["rate"],
            "text": text
        }
        print(f"[INFO] 浅评 prompt 存储键: writer={user_name}, origin={origin_real_name}, key={prompt_mem_key}")
        response_data = {}
        chain = self.rate_chain
        print(f"[INFO] RATE链: {str(self.rate_chain)[:50]}")

        start_time = time.time()
        new_response = ""

        try:
            for _, step in enumerate(chain.steps):
                print(f"[INFO] 当前step的类型: {type(step)}")

                # 模型处理步骤
                if isinstance(step, (BaseChatModel, SimpleChatModel)):
                    print("[INFO] 勾选文件，开始流式输出")
                    print(f"[INFO] chain_input: {chain_input}")

                    # 特殊处理reasoner模式
                    if is_reasoner:
                        print(f"[INFO] chain_input_before: {chain_input}")
                        message_dicts = [_convert_message_to_dict(m) for m in chain_input.messages]
                        print(f"[INFO] chain_input_after: {message_dicts}")

                        response_generator = await self.create_chat_completion(self.get_model(), message_dicts)
                        reasoning_stop = False

                        for chunk in response_generator:
                            reasoning_content = getattr(chunk.choices[0].delta, "reasoning_content", None)
                            plain_content = getattr(chunk.choices[0].delta, "content", None)

                            if reasoning_content is not None:
                                reasoning_stop = False
                                content = "```" + reasoning_content if new_response == "" else reasoning_content
                            elif plain_content is not None:
                                content = plain_content if reasoning_stop else "```" + plain_content
                                reasoning_stop = True
                            else:
                                continue

                            new_response += content
                            response_data['model'] = self.model_name
                            response_data['content'] = content
                            response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                            yield json.dumps(response_data, ensure_ascii=False)

                    # 非reasoner模式处理
                    else:
                        async def stream_with_timeout(step, chain_input):
                            # 获取异步生成器
                            model_config = config_manager.get_model_config(self.model_name)
                            hyper_para = model_config.get_hyper_para()
                            hyper_para_dict = hyper_para.to_dict()

                            # 过滤超参数（Anthropic / Moonshot 固定采样 / dmxapi）
                            filtered_hyper_para = _filter_astream_hyper_para(
                                self.model_name, model_config, hyper_para_dict
                            )

                            # print("[INFO] 输入的内容:", chain_input)
                            print("[INFO] 输入chain_input")

                            async_stream = step.astream(chain_input, **filtered_hyper_para)
                            while True:
                                try:
                                    # 为每个块的生成设置超时
                                    chunk = await asyncio.wait_for(
                                        async_stream.__anext__(),  # 等待下一个异步块
                                        timeout=time_out,  # 设置超时时间
                                    )
                                    yield chunk
                                except StopAsyncIteration:
                                    break  # 流式结束
                                except asyncio.TimeoutError:
                                    print(f"{self.model_name} 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                                    raise APITimeoutError(f"{self.model_name} 流式块生成超时!")

                        async for chunk in stream_with_timeout(step, chain_input):
                            content = chunk.content
                            if content is None:
                                continue

                            if not new_response:
                                print(f"{self.model_name} 响应时间: {time.time() - start_time}秒")

                            new_response += content
                            response_data['model'] = self.model_name
                            response_data['content'] = content
                            response_data['session_id'] = session_id  # 【新增】返回session_id给前端
                            yield json.dumps(response_data, ensure_ascii=False)


                # 非模型处理步骤
                else:
                    chain_input = step.invoke(chain_input)

        except Exception as e:
            print(f"{self.model_name}出错: {str(e)}, 详细错误信息:")
            traceback.print_exc()
            if time.time() - start_time > time_out and new_response == "":
                print(f"{self.model_name} API调用超时, 超时时间: {time.time() - start_time}秒")

            error_content = f"{self.model_name}出错，参考文档内容偏多，或服务器繁忙！"

            response_data['model'] = self.model_name
            response_data['content'] = error_content
            yield json.dumps(response_data, ensure_ascii=False)
        finally:
            # 【新增】清理会话资源
            interrupt_manager.cleanup_session(session_id)

    # async def stream_generator(self, data):
    #     from app_chat.views import chat_content, QS_QQ_base, time_out, chat_with_files_params

    #     constructed_data = construct_data(data)
    #     response_data = constructed_data["response_data"]
    #     username = constructed_data["user_name"]
    #     now_turn_message = constructed_data["message"]

    #     # 使用正则表达式匹配恰好连续的两个问号（不是三个或更多）
    #     # has_double_question_marks = bool(re.search(r'(?<!\?)\?\?(?!\?)', now_turn_message) or
    #     #                                          re.search(r'(?<!？)？？(?!？)', now_turn_message))
    #     # has_consecutive_question_marks = ("???" in now_turn_message) or ("？？？" in now_turn_message)

    #     markers = detect_special_markers(now_turn_message)
    #     has_double_question_marks = markers['has_double_question_marks']
    #     has_consecutive_question_marks = markers['has_triple_question_marks']

    #     chat_content[username][self.model_name] = ""

    #     print("[INFO] 数据解析完成，开始向模型发送请求")

    #     # 这里只做初始化，不干别的事情
    #     GLOBAL_STATE.conversation_manager.get_conversation (
    #         username, self.model_name, constructed_data["rounds"] )

    #     if not constructed_data["file_list"]:
    #         try:
    #             print("[INFO]", self.model_name, " 不勾选文件，发送消息: ", constructed_data["question"])

    #             client = self.get_model()
    #             print("[Debug:stream_generator] 客户端类型:", client.__class__.__name__)

    #             useSystemPrompt = "当前的场景阶段提示：\n" + global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"][
    #             "qa"]
    #             if has_consecutive_question_marks:
    #                 useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
    #             if has_double_question_marks:
    #                 base_prompt = QS_QQ_base
    #                 # 根据加号数量调整提示
    #                 if markers['plus_count'] == 1:
    #                     useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
    #                 elif markers['plus_count'] == 2:
    #                     useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
    #                 elif markers['plus_count'] == 3:
    #                     useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
    #                 else:
    #                     useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"

    #             messages = []
    #             if constructed_data["info_list"]:
    #                 constructed_data["info_list"].insert(0, {
    #                     "type": "text",
    #                     "text": constructed_data["question"]
    #                 })
    #                 messages = [
    #                     {"role": "system", "content": useSystemPrompt},
    #                     {"role": "user", "content": constructed_data["info_list"]}
    #                 ]
    #             else:
    #                 messages = [
    #                     {"role": "system", "content": useSystemPrompt},
    #                     {"role": "user", "content": constructed_data["question"]}
    #                 ]

    #             start_time = time.time()
    #             # messages = [
    #             #     {"role": "system", "content": constructed_data["system_prompt"]},
    #             #     {"role": "user", "content": constructed_data["question"]},
    #             # ]
    #             response_generator = await self.create_chat_completion(client, messages)

    #             print(f"[Debug:stream_generator] {self.model_name} 响应创建用时: {time.time() - start_time}秒")
    #             start_time = time.time()

    #             # 完整对话内容，当填充完整时，加入历史对话信息
    #             new_response = ""

    #             # 流式输出
    #             # 这里的response是一个异步生成器
    #             for chunk in response_generator:

    #                 # print(f"[DEBUG] chunk.choices的长度: {len(chunk.choices)}")
    #                 content = chunk.choices[0].delta.content
    #                 # print(f"[DEBUG] chunk的类型 2: {type(chunk)}")

    #                 if content is None:
    #                     continue

    #                 # 如果content为空，表示刚刚开始流式输出，打印响应时间
    #                 # 否则，表示流式输出的内容，然后添加到响应数据中
    #                 if new_response == "":
    #                     print(f"[INFO] {self.model_name} 响应时间: {time.time() - start_time}秒")
    #                 new_response += content

    #                 # 功能说明：构造响应数据，包含模型名称和内容，并将其转换为JSON格式
    #                 # 只要有content，就返回，实现流式输出
    #                 response_data['model'] = self.model_name
    #                 response_data['content'] = content
    #                 yield json.dumps(response_data, ensure_ascii=False)

    #             # 流式输出结束后，添加完整的响应内容到历史对话中
    #             chat_content[username][self.model_name] = new_response
    #             # GLOBAL_STATE.conversation_manager.add_interaction(
    #             #     username, self.model_name, constructed_data["message"], content)

    #         except Exception as e:
    #             print(self.model_name, f" API error: {e}")
    #             if time.time() - start_time > time_out and chat_content[username][self.model_name] == "":
    #                 print(self.model_name, f" API调用超时, 超时时间: {time.time() - start_time}秒")

    #             content = str(self.model_name) + " API调用出错"

    #             # 调用出错的历史信息也得保留
    #             # GLOBAL_STATE.conversation_manager.add_interaction(
    #             #     username, self.model_name, constructed_data["message"], content)

    #             chat_content[username][self.model_name] = content
    #             response_data['model'] = self.model_name
    #             response_data['content'] = content
    #             yield json.dumps(response_data, ensure_ascii=False)
    #     else:
    #         constructed_params = chat_with_files_params[username]
    #         print(self.model_name, " 勾选文件，发送消息: ", constructed_params["question_with_history"])

    #         useSystemPrompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
    #         if has_consecutive_question_marks:
    #             useSystemPrompt = constructed_data["system_prompt"] + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
    #         if has_double_question_marks:
    #             base_prompt = QS_QQ_base
    #             # 根据加号数量调整提示
    #             if markers['plus_count'] == 1:
    #                 useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
    #             elif markers['plus_count'] == 2:
    #                 useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
    #             elif markers['plus_count'] == 3:
    #                 useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
    #             else:
    #                 useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"

    #         # 有些模型，不支持images_store参数，所以这里需要判断一下
    #         # 应该如何做判断呢？新类型？暂时先完全忽视，空白即可
    #         # 这个text，似乎处理的是图像的内容，那么文档呢?
    #         cur_config = config_manager.get_model_config(self.model_name)
    #         if cur_config.is_allow_img():
    #             print("[INFO] 允许图片输入")
    #             images_store = constructed_params["images_store"]
    #             # text = []
    #         else:
    #             print("[INFO] 不允许图片输入")
    #             images_store = []
    #         text = constructed_params["text"]

    #         chain_input = {
    #             "text": text,
    #             "question": constructed_params["question_with_history"],
    #             "images_store": images_store,
    #             "qa_prompt": useSystemPrompt
    #         }

    #         # print("[INFO] chain_input_before:", chain_input)

    #         chain = self.qa_chain
    #         # print("[INFO] QA链:", str(self.qa_chain)[:50])

    #         start_time = time.time()
    #         async def stream_with_timeout(step, chain_input):
    #             # 获取异步生成器
    #             model_config = config_manager.get_model_config(self.model_name)
    #             hyper_para = model_config.get_hyper_para()
    #             hyper_para = hyper_para.to_dict()

    #             print("[INFO] 输入的内容:", chain_input)

    #             async_stream = step.astream(chain_input, **hyper_para)
    #             while True:
    #                 try:
    #                     # 为每个块的生成设置超时
    #                     chunk = await asyncio.wait_for(
    #                         async_stream.__anext__(),  # 等待下一个异步块
    #                         timeout=GLOBAL_STATE.timeout,  # 设置超时时间
    #                     )
    #                     yield chunk
    #                 except StopAsyncIteration:
    #                     break  # 流式结束
    #                 except asyncio.TimeoutError:
    #                     print(f"{self.model_name} 流式块生成超时, 超时时间: {time.time() - start_time}秒")
    #                     raise APITimeoutError(f"{self.model_name} 流式块生成超时!")

    #         try:
    #             for _, step in enumerate(chain.steps):
    #                 print(f"[INFO] 当前step的类型: {type(step)}")
    #                 if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
    #                     # 使用 astream 方法实现流式输出，并为每个块设置超时

    #                     print("[INFO] 勾选文件，开始流式输出")

    #                     new_response = ""
    #                     print(f"[INFO] chain_input: {chain_input}")

    #                     async for chunk in stream_with_timeout(step, chain_input):
    #                         # print(f"[DEBUG] chunk的类型: {type(chunk)}")

    #                         content = chunk.content
    #                         if content is None:
    #                             print(f"{self.model_name} 返回内容为空")
    #                             continue
    #                         response_data['model'] = self.model_name
    #                         response_data['content'] = content

    #                         if new_response == "":
    #                             print(f"{self.model_name} 响应时间: {time.time() - start_time}秒")
    #                         new_response += content

    #                         yield json.dumps(response_data, ensure_ascii=False)

    #                     GLOBAL_STATE.chat_content[username][self.model_name] = new_response
    #                         # 为每个流式块设置超时
    #                         # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
    #                 else:
    #                     # steps包含两部分：
    #                     # 1. first：ChatPromptTemplate，即prompt模板
    #                     # 2. last：模型对象，用于交流
    #                     # 因此这里调用invoke，不是啥非流式，而是填充模板，即将chain_input的内容
    #                     # 填充到step挖出来的格子中
    #                     chain_input = step.invoke(chain_input)
    #         except Exception as e:
    #             print(f"{self.model_name}出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
    #             if time.time() - start_time > GLOBAL_STATE.timeout and GLOBAL_STATE.chat_content[username][self.model_name] == "":
    #                 print(f"{self.model_name} API调用超时, 超时时间: {time.time() - start_time}秒")
    #             content = f"{self.model_name}出错，参考文档内容偏多，或服务器繁忙！"

    #             GLOBAL_STATE.chat_content[username][self.model_name] = content
    #             self.latest_response = content  # 更新最新响应内容

    #             response_data['model'] = self.model_name
    #             response_data['content'] = content
    #             yield json.dumps(response_data, ensure_ascii=False)

    # async def stream_generator_reasoner(self, data):
    #     from app_chat.views import chat_content, QS_QQ_base, time_out, chat_with_files_params
    #     constructed_data = construct_data(data)
    #     response_data = constructed_data["response_data"]
    #     username = constructed_data["user_name"]

    #     print("[INFO] 数据解析完成，开始向模型发送请求")

    #     # 这里只做初始化，不干别的事情
    #     GLOBAL_STATE.conversation_manager.get_conversation (
    #         username, self.model_name, constructed_data["rounds"] )
    #     if not constructed_data["file_list"]:
    #         try:
    #             print("[INFO]", self.model_name, " 不勾选文件，发送消息: ", constructed_data["question"])

    #             client = self.get_model()
    #             print("[Debug:stream_generator] 客户端类型:", client.__class__.__name__)

    #             start_time = time.time()
    #             messages = [
    #                 {"role": "system", "content": constructed_data["system_prompt"]},
    #                 {"role": "user", "content": constructed_data["question"]},
    #             ]
    #             response_generator = await self.create_chat_completion(client, messages)

    #             start_time = time.time()
    #             reasoning_stop = False

    #             # 完整对话内容，当填充完整时，加入历史对话信息
    #             new_response = ""
    #             result = ""

    #             # 流式输出
    #             # 这里的response是一个异步生成器
    #             # async for chunk in response_with_timeout(response_generator):
    #             for chunk in response_generator:
    #                 # 检查chunk的类型
    #                 # print(f"[DEBUG] chunk的类型: {type(chunk)}")

    #                 reasoning_content = chunk.choices[0].delta.reasoning_content
    #                 content = chunk.choices[0].delta.content

    #                 if reasoning_content is not None:
    #                     reasoning_stop = False
    #                     if result == "":
    #                         print(f"{self.model_name} 响应时间: {time.time() - start_time}")
    #                         result = "```" + reasoning_content
    #                     else:
    #                         result = reasoning_content
    #                 elif content is not None:
    #                     if reasoning_stop:
    #                         result = content
    #                     else:
    #                         result = "```" + content
    #                     reasoning_stop = True
    #                 else:
    #                     # print('Dsreasoner 返回内容为空')
    #                     continue

    #                 new_response += result

    #                 # 功能说明：构造响应数据，包含模型名称和内容，并将其转换为JSON格式
    #                 # 只要有content，就返回，实现流式输出
    #                 response_data['model'] = self.model_name
    #                 response_data['content'] = result
    #                 yield json.dumps(response_data, ensure_ascii=False)

    #             # 流式输出结束后，添加完整的响应内容到历史对话中
    #             GLOBAL_STATE.chat_content[username][self.model_name] = new_response
    #             self.latest_response = new_response  # 更新最新响应内容

    #         except Exception as e:
    #             print(self.model_name, f" API error: {e}")
    #             if time.time() - start_time > time_out and chat_content[username][self.model_name] == "":
    #                 print(self.model_name, f" API调用超时, 超时时间: {time.time() - start_time}秒")

    #             content = str(self.model_name) + " API调用出错"

    #             # 调用出错的历史信息也得保留
    #             # GLOBAL_STATE.conversation_manager.add_interaction(
    #             #     username, self.model_name, constructed_data["message"], content)

    #             response_data['model'] = self.model_name
    #             response_data['content'] = content
    #             yield json.dumps(response_data, ensure_ascii=False)
    #     else:
    #         constructed_params = chat_with_files_params[username]
    #         print(self.model_name, " 勾选文件，发送消息: ", constructed_params["question_with_history"])

    #         # 有些模型，不支持images_store参数，所以这里需要判断一下
    #         # 应该如何做判断呢？新类型？暂时先完全忽视，空白即可
    #         # 这个text，似乎处理的是图像的内容，那么文档呢?
    #         chain_input = {
    #             "text": constructed_params["text"],
    #             "question": constructed_params["question_with_history"],
    #             "images_store": [], # constructed_params["images_store"],
    #             "qa_prompt": global_var.store_memory[constructed_data['user_name']]["prompt"]["LUI2"]["qa"]
    #         }

    #         chain = self.qa_chain
    #         # 调用_convert_message_to_dict将chain_input转换为字典格式
    #         # 其余部分和上述无文档保持一致
    #         start_time = time.time()

    #         try:
    #             for _, step in enumerate(chain.steps):
    #                 print(f"[INFO] 当前step的类型: {type(step)}")
    #                 if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
    #                     # 使用 astream 方法实现流式输出，并为每个块设置超时
    #                     # 输出转换前
    #                     print(f"[INFO] chain_input_before: {chain_input}")
    #                     message_dicts = [_convert_message_to_dict(m) for m in chain_input.messages]
    #                     # 输出转换后
    #                     print(f"[INFO] chain_input_after: {message_dicts}")

    #                     print("[INFO] 勾选文件，开始流式输出")

    #                     new_response = ""
    #                     result = ""

    #                     # 靠，不管了，后续再看看有什么更好的管理方式吧
    #                     # ChatOpenAI和OpenAI的调用方法是不一样的
    #                     response_generator = await self.create_chat_completion(self.get_model(), message_dicts)

    #                     for chunk in response_generator:
    #                         # 检查chunk的类型
    #                         # print(f"[DEBUG] chunk的类型: {type(chunk)}")

    #                         reasoning_content = chunk.choices[0].delta.reasoning_content
    #                         content = chunk.choices[0].delta.content

    #                         if reasoning_content is not None:
    #                             reasoning_stop = False
    #                             if result == "":
    #                                 print(f"{self.model_name} 响应时间: {time.time() - start_time}")
    #                                 result = "```" + reasoning_content
    #                             else:
    #                                 result = reasoning_content
    #                         elif content is not None:
    #                             if reasoning_stop:
    #                                 result = content
    #                             else:
    #                                 result = "```" + content
    #                             reasoning_stop = True
    #                         else:
    #                             # print('Dsreasoner 返回内容为空')
    #                             continue

    #                         new_response += result

    #                         # 功能说明：构造响应数据，包含模型名称和内容，并将其转换为JSON格式
    #                         # 只要有content，就返回，实现流式输出
    #                         response_data['model'] = self.model_name
    #                         response_data['content'] = result
    #                         yield json.dumps(response_data, ensure_ascii=False)

    #                     # 流式输出结束后，添加完整的响应内容到历史对话中
    #                     GLOBAL_STATE.chat_content[username][self.model_name] = new_response
    #                     self.latest_response = new_response  # 更新最新响应内容
    #                         # 为每个流式块设置超时
    #                         # yield await asyncio.wait_for(json.dumps(response_data, ensure_ascii=False), timeout=60)  # 超时时间为60秒
    #                 else:
    #                     # 非流式步骤，直接调用 invoke
    #                     chain_input = step.invoke(chain_input)

    #         except Exception as e:
    #             print(f"{self.model_name}出错，参考文档内容偏多，或服务器繁忙: {str(e)}")
    #             if time.time() - start_time > GLOBAL_STATE.timeout and GLOBAL_STATE.chat_content[username][self.model_name] == "":
    #                 print(f"{self.model_name} API调用超时, 超时时间: {time.time() - start_time}秒")
    #             content = f"{self.model_name}出错，参考文档内容偏多，或服务器繁忙！"

    #             GLOBAL_STATE.chat_content[username][self.model_name] = content

    #             response_data['model'] = self.model_name
    #             response_data['content'] = content
    #             yield json.dumps(response_data, ensure_ascii=False)

    def init_qa(self):
        # 用handler中的model_with_langchain实现下述功能

        chat_model = self.model_with_langchain.get_model()
        messages = []
        messages_1, messages_2 = self.model_with_langchain.get_qa_msg()
        messages.extend(messages_1)
        messages.extend(messages_2)
        chat_template = ChatPromptTemplate.from_messages(messages)
        self.qa_chain = chat_template | chat_model
        self.qa_chain = self.model_with_langchain.unique_parse(self.qa_chain)

    def init_suma(self):
        # 用handler中的model_with_langchain实现下述功能
        chat_model = self.model_with_langchain.get_model()
        messages = self.model_with_langchain.get_sum_msg()
        chat_template = ChatPromptTemplate.from_messages(messages)

        self.sma_chain = chat_template | chat_model
        self.sma_chain = self.model_with_langchain.unique_parse(self.sma_chain)

    def parse_str_to_list(self, ai_message: AIMessage) -> list:
        print(ai_message.content)
        begin = ai_message.content.rfind('{')
        end = ai_message.content.rfind('}')
        all_message = ai_message.content[begin + 1:end]
        all_message = all_message.replace("'", '')
        topic_list = all_message.split(',')
        return topic_list

    def init_que(self):
        chat_model = self.model_with_langchain.get_model()
        messages_1, messages_2 = self.model_with_langchain.get_que_msg()
        messages = []
        messages.extend(messages_1)
        messages.append(MessagesPlaceholder("chat_history"))
        messages.extend(messages_2)
        chat_template = ChatPromptTemplate.from_messages(messages)
        self.que_chain = chat_template | chat_model
        self.que_chain = self.model_with_langchain.unique_parse(self.que_chain)
        self.que_chain = self.que_chain | self.parse_str_to_list

    def init_topic(self):
        chat_model = self.model_with_langchain.get_model()

        examples = [
            {"input": "大语言模型的研究融合了自然语言处理、机器学习、分布式计算、并行计算等多个学科领域。"
                      "其发展历程可以分为基础模型阶段、能力探索阶段和突破发展阶段。",
             "output": "{'大语言模型'}"},
            {"input": "有监督微调（Supervised Finetuning），也称为指令微调（Instruction Tuning），利用少量高质量数据"
                      "集合，包含用户输入的提示词（Prompt）和对应的理想输出结果。用户输入包括问题、闲聊对话、任务指令等多种形式和任务。。",
             "output": "{'指令微调'}"}
        ]
        example_prompt = ChatPromptTemplate.from_messages(
            [
                ("human", "{input}"),
                ("ai", "{output}"),
            ]
        )
        few_shot_prompt = FewShotChatMessagePromptTemplate(
            example_prompt=example_prompt,
            examples=examples,
        )
        messages_1, messages_2 = self.model_with_langchain.get_topic_msg()
        messages = []
        messages.extend(messages_1)
        messages.append(few_shot_prompt)
        messages.extend(messages_2)
        chat_template = ChatPromptTemplate.from_messages(messages)
        self.topic_chain = chat_template | chat_model
        self.topic_chain = self.model_with_langchain.unique_parse(self.topic_chain)
        self.topic_chain = self.topic_chain | self.parse_str_to_list

    def init_rate(self):
        # 用handler中的model_with_langchain实现下述功能

        chat_model = self.model_with_langchain.get_model()
        messages = [
            SystemMessagePromptTemplate.from_template(
                "{rate}"
            ),
            HumanMessagePromptTemplate.from_template(
                "请针对以下文本完成上述任务，记得上面的输出格式要求，涉及“红蓝融合第n层”要在后面括号具体描述，例如'1.5分_紫色_达到红蓝融合第一层（人文+科技）但"
                "不到第二层（认知+行动），建议增加实践方法'，文本如下：{text}"
            )
        ]
        chat_template = ChatPromptTemplate.from_messages(messages)
        # 重整chat得到prompt
        self.rate_chain = chat_template | chat_model
        self.rate_chain = self.model_with_langchain.unique_parse(self.rate_chain)

    def init_card_suma(self):
        # 用handler中的model_with_langchain实现下述功能

        chat_model = self.model_with_langchain.get_model()
        messages = [
            HumanMessagePromptTemplate.from_template(
                "{text}"),
        ]
        chat_template = ChatPromptTemplate.from_messages(messages)

        self.card_chain = chat_template | chat_model
        self.card_chain = self.model_with_langchain.unique_parse(self.card_chain)

    # chain_run(chain_type, chain_input)（用字符串表示链的类型）
    def chain_run(self, chain_type, chain_input):
        '''
        非流式且同步输出
        chain_type：qa_chain、sma_chain、que_chain、topic_chain、rate_chain、card_chain
        '''
        # 这里的chain_type是字符串类型
        # 通过getattr获取对应的链
        chain = getattr(self, f"{chain_type}")

        model_config = config_manager.get_model_config(self.model_name)
        hyper_para_dict = model_config.get_hyper_para().to_dict()

        # 过滤超参数（Anthropic / Moonshot 固定采样 / dmxapi）
        hyper_para = _filter_astream_hyper_para(
            self.model_name, model_config, hyper_para_dict
        )

        for i, step in enumerate(chain.steps):
            if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                print(f'[DEBUG] type_chain_input:', chain_input)
                # print(isinstance(chain_input, PromptValue))
                # print(datetime.now())
                chain_input = step.invoke(
                    chain_input,
                    **hyper_para
                )
            else:
                chain_input = step.invoke(
                    chain_input,
                )

        return chain_input

    async def chain_run_async(self, chain_type, chain_input):
        '''
        非流式且异步输出
        chain_type：qa_chain、sma_chain、que_chain、topic_chain、rate_chain、card_chain
        '''

        chain = getattr(self, f"{chain_type}")
        model_config = config_manager.get_model_config(self.model_name)
        hyper_para_dict = model_config.get_hyper_para().to_dict()

        # 过滤超参数（Anthropic / Moonshot 固定采样 / dmxapi）
        hyper_para = _filter_astream_hyper_para(
            self.model_name, model_config, hyper_para_dict
        )

        try:
            for i, step in enumerate(chain.steps):
                if isinstance(step, BaseChatModel) or isinstance(step, SimpleChatModel):
                    # print(chain_input)
                    # print(isinstance(chain_input, PromptValue))
                    # print(datetime.now())
                    chain_input = await step.astream(
                        chain_input,
                        **hyper_para
                    )
                else:
                    chain_input = step.invoke(
                        chain_input,
                    )
            return chain_input
        except Exception as e:
            print(str(e))
            return AIMessage(content='出错，参考文档内容偏多，或服务器繁忙！', response_metadata={'finish_reason': 'stop'})

    async def stream_generator_second_iteration_only(self, data, is_reasoner=False):
        """
        只做第二次迭代的流式生成器（重做功能使用）
        跳过第一次回答和深评，直接进行第二次迭代
        """
        from app_chat.views import chat_content, QS_QQ_base, time_out, chat_with_files_params

        constructed_data = construct_data(data)
        response_data = constructed_data["response_data"]
        username = constructed_data["user_name"]
        _prompt_store_key = constructed_data.get("prompt_storage_key") or constructed_data["writer"]
        now_turn_message = constructed_data["message"]

        markers = detect_special_markers(now_turn_message)
        has_double_question_marks = markers['has_double_question_marks']
        has_consecutive_question_marks = markers['has_triple_question_marks']

        chat_content[username][self.model_name] = ""
        print("[INFO] 重做第二次迭代 - 数据解析完成，开始向模型发送请求")

        # 【新增】创建会话ID用于中断控制
        model_id = data.get("model_id", "unknown")
        try:
            task = asyncio.current_task()
            task_name = task.get_name() if task else str(int(time.time() * 1000))
        except RuntimeError:
            task_name = str(int(time.time() * 1000))
        session_id = f"{username}_{model_id}_redo_{task_name}"
        interrupt_event = interrupt_manager.create_session(session_id)

        # 初始化会话管理器
        GLOBAL_STATE.conversation_manager.get_conversation(
            username, self.model_name)

        # 公共变量
        start_time = time.time()
        new_response = ""
        content_field = "reasoning_content" if is_reasoner else "content"

        # 系统提示处理
        system_prompt = config_manager.get_system_prompt(self.model_name)
        user_prompt = config_manager.get_user_prompt(self.model_name)

        if not constructed_data["file_list"]:
            try:
                print("[INFO] 重做第二次迭代 - 不勾选文件，发送消息: ", constructed_data["question"])
                client = self.get_model()
                print("[Debug:stream_generator_second_iteration_only] 客户端类型:", client.__class__.__name__)

                # 系统提示处理
                useSystemPrompt = ""
                if data.get("noScene", "false") != "true":
                    useSystemPrompt = "当前的场景阶段提示：\n" + \
                                      global_var.store_memory[_prompt_store_key]["prompt"]["LUI2"]["qa"]
                if has_consecutive_question_marks:
                    useSystemPrompt = system_prompt + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
                if has_double_question_marks:
                    base_prompt = QS_QQ_base
                    if markers['plus_count'] == 1:
                        useSystemPrompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                    elif markers['plus_count'] == 2:
                        useSystemPrompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                    elif markers['plus_count'] == 3:
                        useSystemPrompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                    else:
                        useSystemPrompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"

                # 慢思考迭代：按原问题读取共享判定并加深
                _req_window = str(data.get('windowId') or data.get('window_id') or '').strip()
                _cur_msg = str(constructed_data.get('message') or constructed_data.get('question') or '')
                _bound_msg = str(data.get('socraticBoundMessage') or data.get('originalQuestion') or '')
                _socratic = resolve_socratic_probe_for_request(
                    chat_with_files_params,
                    name_keys=[username, constructed_data.get('writer')],
                    window_id=_req_window,
                    current_message=_cur_msg,
                    bound_message=_bound_msg,
                    prefer_mode='iteration',
                )
                question_for_model = constructed_data["question"]
                if _socratic.get('should_counter_ask') and _socratic.get('instruction'):
                    useSystemPrompt = apply_socratic_to_system_prompt(useSystemPrompt, _socratic)
                    question_for_model = apply_socratic_to_user_text(question_for_model, _socratic)
                    print(
                        f"[INFO] 重做第二次迭代 - 延续语义反问加深 window={_req_window} "
                        f"phase={_socratic.get('phase')}",
                        flush=True,
                    )

                # 构造消息
                if constructed_data["info_list"]:
                    constructed_data["info_list"].insert(0, {
                        "type": "text",
                        "text": question_for_model
                    })

                    # 将user_prompt也转换为消息格式
                    user_content = [{"type": "text", "text": user_prompt}] + constructed_data["info_list"]

                    messages = [
                        {"role": "system", "content": useSystemPrompt},
                        {"role": "user", "content": user_content}
                    ]
                else:
                    messages = [
                        {"role": "system", "content": useSystemPrompt},
                        {"role": "user", "content": user_prompt + question_for_model}
                    ]

                # 获取响应生成器
                model_type = config_manager.get_model_config(self.model_name).get_model_type()
                if model_type == "anthropic":
                    # Anthropic模型：直接调用非异步方法获取异步生成器
                    response_generator = self.create_anthropic_chat_completion(client, messages)
                else:
                    # OpenAI模型需要await
                    response_generator = await self.create_chat_completion(client, messages)
                print(
                    f"[Debug:stream_generator_second_iteration_only] {self.model_name} 响应创建用时: {time.time() - start_time}秒")

                # 处理流式响应
                model_type = config_manager.get_model_config(self.model_name).get_model_type()

                if model_type == "anthropic":
                    # 处理Anthropic原生流式响应
                    async for content in response_generator:
                        if content is None:
                            continue

                        # 记录首次响应时间
                        if not new_response:
                            print(f"[INFO] 重做第二次迭代 - {self.model_name} 响应时间: {time.time() - start_time}秒")

                        new_response += content
                        response_data['model'] = self.model_name
                        response_data['content'] = content
                        response_data['session_id'] = session_id  # 【新增】返回session_id给前端

                        # 【新增】检查是否被中断
                        if interrupt_manager.is_interrupted(session_id):
                            print(f"[INFO] 重做第二次迭代 - 检测到中断信号，停止响应: {session_id}")
                            response_data['content'] = "\n[响应已中断]"
                            yield json.dumps(response_data, ensure_ascii=False)
                            return

                        yield json.dumps(response_data, ensure_ascii=False)
                else:
                    # 处理OpenAI流式响应（原有逻辑）
                    reasoning_stop = False
                    for chunk in response_generator:
                        if not chunk.choices:
                            continue  # 如果没有choices，跳过

                        # 获取内容字段
                        if is_reasoner:
                            reasoning_content = getattr(chunk.choices[0].delta, "reasoning_content", None)
                            plain_content = getattr(chunk.choices[0].delta, "content", None)

                            if reasoning_content is not None:
                                reasoning_stop = False
                                content = "```" + reasoning_content if new_response == "" else reasoning_content
                            elif plain_content is not None:
                                content = plain_content if reasoning_stop else "```" + plain_content
                                reasoning_stop = True
                            else:
                                continue
                        else:
                            content = getattr(chunk.choices[0].delta, content_field, None)
                            if content is None:
                                continue

                        # 记录首次响应时间
                        if not new_response:
                            print(f"[INFO] 重做第二次迭代 - {self.model_name} 响应时间: {time.time() - start_time}秒")

                        new_response += content
                        response_data['model'] = self.model_name
                        response_data['content'] = content
                        response_data['session_id'] = session_id  # 【新增】返回session_id给前端

                        # 【新增】检查是否被中断
                        if interrupt_manager.is_interrupted(session_id):
                            print(f"[INFO] 重做第二次迭代 - 检测到中断信号，停止响应: {session_id}")
                            response_data['content'] = "\n[响应已中断]"
                            yield json.dumps(response_data, ensure_ascii=False)
                            return

                        yield json.dumps(response_data, ensure_ascii=False)

                # 保存完整响应
                chat_content[username][self.model_name] = new_response

            except Exception as e:
                print(self.model_name, f" 重做第二次迭代 API error: {e}, 详细错误信息:")
                traceback.print_exc()
                if time.time() - start_time > time_out and chat_content[username][self.model_name] == "":
                    print(self.model_name, f" 重做第二次迭代 API调用超时, 超时时间: {time.time() - start_time}秒")

                error_content = f"{self.model_name} 重做第二次迭代 API调用出错"
                chat_content[username][self.model_name] = error_content
                response_data['model'] = self.model_name
                response_data['content'] = error_content
                yield json.dumps(response_data, ensure_ascii=False)

        # 有文件的情况 - 简化处理，直接调用原有逻辑
        else:
            constructed_params = chat_with_files_params[username]
            # # 重做时强制使用原始问题，不使用缓存的 question_with_history（可能包含综述前缀）
            # print(self.model_name, " 重做第二次迭代 - 勾选文件，使用原始问题: ", constructed_data["question"])
            # 与首答一致：以 constructed_data["message"]（含 NK2026 Gxx 等后处理）为准再拼历史
            _msg_full_redo = constructed_data["message"]
            if constructed_data["history"]:
                effective_question_redo = normal_qa_new.get_model_specific_histories2(
                    constructed_data["writer"],
                    _msg_full_redo,
                    self.model_name,
                    constructed_data["rounds"],
                )
            else:
                effective_question_redo = _msg_full_redo
            print(
                self.model_name,
                " 重做第二次迭代 - 勾选文件，含后处理提问前500字: ",
                effective_question_redo[:500] + ("..." if len(effective_question_redo) > 500 else ""),
            )

            # 系统提示处理
            # qa_prompt = global_var.store_memory[constructed_data['writer']]["prompt"]["LUI2"]["qa"]
            qa_prompt = global_var.store_memory[_prompt_store_key]["prompt"]["LUI2"]["qa"]
            if has_consecutive_question_marks:
                qa_prompt = system_prompt + "\n当前的场景阶段为通用问答，多个问号代表本次提问不需要考虑任何关联文档及描述，即最简单的对话"
            if has_double_question_marks:
                base_prompt = QS_QQ_base
                if markers['plus_count'] == 1:
                    qa_prompt += f"\n{base_prompt} 本次为低程度熵减引导（QS），要提供深刻、明确、可落实的建议，来引导用户思考。"
                elif markers['plus_count'] == 2:
                    qa_prompt += f"\n{base_prompt} 本次为中程度熵减引导（QS+QQ），减少明确建议，明显增加反问部分、问题链的引导张力和深度。"
                elif markers['plus_count'] == 3:
                    qa_prompt += f"\n{base_prompt} 本次为高程度熵减引导（QQ），几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供具有显著思考挑战性的问题链，高度进阶性、关联性、有张力。"
                else:
                    qa_prompt += f"\n{base_prompt} 本次请你对于建议和反向发问都要涉及，以此引导、激发用户思考。"

            # 慢思考迭代（有文档）：按原问题共享判定
            _req_window = str(data.get('windowId') or data.get('window_id') or '').strip()
            _cur_msg = str(constructed_data.get('message') or constructed_data.get('question') or '')
            _bound_msg = str(data.get('socraticBoundMessage') or data.get('originalQuestion') or '')
            _socratic = resolve_socratic_probe_for_request(
                chat_with_files_params,
                name_keys=[username, constructed_data.get('writer')],
                window_id=_req_window,
                current_message=_cur_msg,
                bound_message=_bound_msg,
                prefer_mode='iteration',
            )
            if _socratic.get('should_counter_ask') and _socratic.get('instruction'):
                qa_prompt = apply_socratic_to_system_prompt(qa_prompt, _socratic)
                effective_question_redo = apply_socratic_to_user_text(effective_question_redo, _socratic)
                print(
                    f"[INFO] 重做第二次迭代 - 启用语义反问加深模式(有文档) window={_req_window} "
                    f"analysis={_socratic.get('analysis')}",
                    flush=True,
                )

            # 处理图像输入
            cur_config = config_manager.get_model_config(self.model_name)
            images_store = constructed_params["images_store"] if cur_config.is_allow_img() else []

            chain_input = {
                "text": constructed_params["text"],
                # "question": user_prompt + constructed_params["question_with_history"][self.model_name],
                # "question": user_prompt + constructed_data["question"],  # 使用原始问题，不是 question_with_history
                "question": user_prompt + effective_question_redo,
                "images_store": images_store,
                "qa_prompt": qa_prompt
            }

            chain = self.qa_chain
            print(f"[INFO] 重做第二次迭代 - QA链: {str(self.qa_chain)[:50]}")

            try:
                for _, step in enumerate(chain.steps):
                    print(f"[INFO] 重做第二次迭代 - 当前step的类型: {type(step)}")

                    # 模型处理步骤
                    if isinstance(step, (BaseChatModel, SimpleChatModel)):
                        print("[INFO] 重做第二次迭代 - 勾选文件，开始流式输出")

                        # 特殊处理reasoner模式
                        if is_reasoner:
                            message_dicts = [_convert_message_to_dict(m) for m in chain_input.messages]

                            response_generator = await self.create_chat_completion(self.get_model(), message_dicts)
                            reasoning_stop = False

                            for chunk in response_generator:
                                reasoning_content = getattr(chunk.choices[0].delta, "reasoning_content", None)
                                plain_content = getattr(chunk.choices[0].delta, "content", None)

                                if reasoning_content is not None:
                                    reasoning_stop = False
                                    content = "```" + reasoning_content if new_response == "" else reasoning_content
                                elif plain_content is not None:
                                    content = plain_content if reasoning_stop else "```" + plain_content
                                    reasoning_stop = True
                                else:
                                    continue

                                new_response += content
                                response_data['model'] = self.model_name
                                response_data['content'] = content
                                response_data['session_id'] = session_id  # 【新增】返回session_id给前端

                                # 【新增】检查是否被中断
                                if interrupt_manager.is_interrupted(session_id):
                                    print(f"[INFO] 重做第二次迭代 - 检测到中断信号，停止响应: {session_id}")
                                    response_data['content'] = "\n[响应已中断]"
                                    yield json.dumps(response_data, ensure_ascii=False)
                                    return

                                yield json.dumps(response_data, ensure_ascii=False)

                        # 非reasoner模式处理
                        else:
                            async def stream_with_timeout(step, chain_input):
                                # 获取异步生成器
                                model_config = config_manager.get_model_config(self.model_name)
                                hyper_para = model_config.get_hyper_para()
                                hyper_para_dict = hyper_para.to_dict()

                                # 过滤超参数（Anthropic / Moonshot 固定采样 / dmxapi）
                                model_type = model_config.get_model_type()
                                filtered_hyper_para = _filter_astream_hyper_para(
                                    self.model_name, model_config, hyper_para_dict
                                )

                                print("[INFO] 重做第二次迭代 - 输入的内容:", chain_input)

                                # Anthropic模型重试机制：最多重试2次
                                max_retries = 2 if model_type == "anthropic" else 0
                                retry_count = 0

                                while retry_count <= max_retries:
                                    try:
                                        async_stream = step.astream(chain_input, **filtered_hyper_para)
                                        while True:
                                            try:
                                                # 为每个块的生成设置超时
                                                chunk = await asyncio.wait_for(
                                                    async_stream.__anext__(),  # 等待下一个异步块
                                                    timeout=time_out,  # 设置超时时间
                                                )
                                                yield chunk
                                            except StopAsyncIteration:
                                                return  # 流式结束，成功
                                            except asyncio.TimeoutError:
                                                print(
                                                    f"{self.model_name} 重做第二次迭代 - 流式块生成超时, 超时时间: {time.time() - start_time}秒")
                                                raise APITimeoutError(f"{self.model_name} 重做第二次迭代 - 流式块生成超时!")
                                    except Exception as e:
                                        if model_type == "anthropic" and retry_count < max_retries:
                                            retry_count += 1
                                            print(f"[INFO] 重做第二次迭代 - Anthropic模型第{retry_count}次重试，错误: {e}")
                                            await asyncio.sleep(1)  # 等待1秒后重试
                                            continue
                                        else:
                                            raise e
                                return

                            # 记录首次响应时间
                            if not new_response:
                                print(f"[INFO] 重做第二次迭代 - {self.model_name} 响应时间: {time.time() - start_time}秒")

                            async for chunk in stream_with_timeout(step, chain_input):
                                if hasattr(chunk, 'content') and chunk.content:
                                    new_response += chunk.content
                                    response_data['model'] = self.model_name
                                    response_data['content'] = chunk.content

                                    # 【新增】检查是否被中断
                                    if interrupt_manager.is_interrupted(session_id):
                                        print(f"[INFO] 重做第二次迭代 - 检测到中断信号，停止响应: {session_id}")
                                        response_data['content'] = "\n[响应已中断]"
                                        yield json.dumps(response_data, ensure_ascii=False)
                                        return

                                    yield json.dumps(response_data, ensure_ascii=False)
                    else:
                        chain_input = step.invoke(chain_input)

                # 保存完整响应
                chat_content[username][self.model_name] = new_response

            except Exception as e:
                print(self.model_name, f" 重做第二次迭代 - 勾选文件 API error: {e}, 详细错误信息:")
                traceback.print_exc()
                if time.time() - start_time > time_out and chat_content[username][self.model_name] == "":
                    print(self.model_name, f" 重做第二次迭代 - 勾选文件 API调用超时, 超时时间: {time.time() - start_time}秒")

                error_content = f"{self.model_name} 重做第二次迭代 - 勾选文件 API调用出错"
                chat_content[username][self.model_name] = error_content
                response_data['model'] = self.model_name
                response_data['content'] = error_content
                yield json.dumps(response_data, ensure_ascii=False)
            finally:
                # 【新增】清理会话
                interrupt_manager.cleanup_session(session_id)
                print(f"[INFO] 重做第二次迭代 - 清理会话: {session_id}")
