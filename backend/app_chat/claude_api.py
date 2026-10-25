import nkcn_public_config as _public_config
#encoding=utf-8
import re
import argparse
import string
from openai import OpenAI
import anthropic

from llm_langchain import global_var


def extract_sentences(text):
    """
    从文本中提取句子列表
    """
    sentences = []
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            sentences.append(line)
    return sentences


def find_word_in_string(word, text):
    """
    在字符串中查找单词（不区分大小写）
    """
    return word.lower() in text.lower()


def post_process_claude_response(response_text):
    """
    处理Claude API的响应文本，提取和过滤指令

    Args:
        response_text: Claude API返回的文本内容

    Returns:
        处理后的指令列表
    """
    if not response_text or len(response_text) == 0:
        return []

    raw_instructions = extract_sentences(response_text)
    # 列表所有的inst合并成一个长串用作切分
    inst_long_str = '\n'.join(raw_instructions)
    instructions_list = inst_long_str.split('\n')

    instructions = []
    for inst in instructions_list:
        inst = re.sub(r"\s+", " ", inst).strip()
        inst = inst.strip().capitalize()
        inst_sub_list = inst.split('.')
        if len(inst_sub_list) >= 2:
            inst = inst_sub_list[1]
        else:
            continue
        # filter out too short or too long instructions
        if len(inst) <= 3 or len(inst) > 150:
            continue
        # filter based on keywords that are not suitable for language models.
        if any(find_word_in_string(word, inst) for word in
               ["image", "images", "graph", "graphs", "picture", "pictures", "file", "files", "map", "maps", "draw",
                "plot", "go to"]):
            continue
        if inst.startswith("Write a program"):
            continue
        # filter those starting with punctuation
        if inst[0] in string.punctuation:
            continue
        # filter those starting with non-english character
        if inst[0].isnumeric():
            continue
        instructions.append(inst)
    return instructions


# def make_claude_text_requests(user_prompt, system_prompt=""):
#     client = anthropic.Anthropic()
#     message = client.messages.create(
#         model="claude-3-5-sonnet-20241022",
#         max_tokens=global_var.claudeConfig["max_tokens"],
#         temperature=global_var.claudeConfig["temperature"],
#         system=system_prompt,
#         messages=[
#             {
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": user_prompt}
#                 ]
#             }
#         ]
#     )
#     return message.content


def make_claude_text_requests(user_prompt, system_prompt="", model=None):
    client = OpenAI(
        api_key=_public_config.secret('OPENAI_API_KEY'),
        base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
        default_headers={"x-foo": "true"}
    )
    if model is None:
        # model = "claude-3-7-sonnet-20250219"
        model = "claude-sonnet-4-20250514"
    message = client.chat.completions.create(
        model=model,
        max_tokens=global_var.claudeConfig["max_tokens"],
        temperature=global_var.claudeConfig["temperature"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}],
    )
    return message.choices[0].message.content


def make_claude_text_requests_feishu_ta_chain(user_prompt, system_prompt=""):
    """
    飞书 TA 答疑：优先 Sonnet 4.5，失败重试；三次失败后降级 Sonnet 4，再失败降级 3.7。
    各档内最多尝试 3 次（共「再给 2 次机会」语义）。
    model id 随中转商别名可能需调整，见 FEISHU_TA_MODEL_CHAIN。
    """
    # (model_id, 连续尝试次数)
    chain = [
        ("claude-sonnet-4-5-20250929", 3),
        ("claude-sonnet-4-20250514", 3),
        ("claude-3-7-sonnet-20250219", 3),
    ]
    last_err = None
    for model, max_tries in chain:
        for attempt in range(1, max_tries + 1):
            try:
                print(
                    f"[claude_api/feishu_ta] model={model!r} attempt {attempt}/{max_tries}"
                )
                out = make_claude_text_requests(
                    user_prompt, system_prompt, model=model
                )
                if out is not None and str(out).strip():
                    return out
                print(
                    f"[claude_api/feishu_ta] model={model!r} attempt {attempt} empty content"
                )
            except Exception as e:
                last_err = e
                print(
                    f"[claude_api/feishu_ta] model={model!r} attempt {attempt} error: {e}"
                )
        print(f"[claude_api/feishu_ta] give up on {model!r} after {max_tries} tries")
    if last_err is not None:
        print(f"[claude_api/feishu_ta] chain exhausted, last error: {last_err!r}")
    return ""


async def make_claude_text_requests_async(user_prompt, system_prompt=""):
    # client = anthropic.Anthropic()
    # message = client.messages.create(
    #     model="claude-3-5-sonnet-20241022",
    #     max_tokens=global_var.claudeConfig["max_tokens"],
    #     temperature=global_var.claudeConfig["temperature"],
    #     system=system_prompt,
    #     messages=[
    #         {
    #             "role": "user",
    #             "content": [
    #                 {"type": "text", "text": user_prompt}
    #             ]
    #         }
    #     ]
    # )
    # return message.content[0].text
    client = OpenAI(
        api_key=_public_config.secret('OPENAI_API_KEY'),
        base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
        default_headers={"x-foo": "true"}
    )
    message = client.chat.completions.create(
        # model="claude-3-7-sonnet-20250219",
        model="claude-sonnet-4-20250514",
        max_tokens=global_var.claudeConfig["max_tokens"],
        temperature=global_var.claudeConfig["temperature"],
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}],
    )
    return message.choices[0].message.content


def make_gpt4o_text_requests(user_prompt, system_prompt=""):
    res = ""
    client = OpenAI(
        api_key=_public_config.secret('NKCN_CLAUDE_API_API_KEY'),
    )
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}],
    )

    res = response.choices[0].message.content
    return res


def make_claude_image_text_requests(user_prompt, base64_image, system_prompt="", use_fixed_params=False, text_after_image=None):
    client = OpenAI(
        api_key=_public_config.secret('OPENAI_API_KEY'),
        base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
        default_headers={"x-foo": "true"},
    )

    # 构建消息内容
    content_parts = [
        {
            "type": "text",
            "text": user_prompt
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
            }
        }
    ]

    # 如果有图片后的文本，则添加
    if text_after_image:
        content_parts.append({
            "type": "text",
            "text": text_after_image
        })

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_parts}
    ]

    # 根据参数选择配置
    if use_fixed_params:
        # 使用固定参数
        response = client.chat.completions.create(
            # model='claude-3-7-sonnet-20250219',
            model='claude-sonnet-4-20250514',
            messages=messages,
            temperature=0,
            max_tokens=2048
        )
    else:
        # 使用global_var.config参数（保持向后兼容）
        response = client.chat.completions.create(
            # model='claude-3-7-sonnet-20250219',
            model='claude-sonnet-4-20250514',
            messages=messages,
            temperature=global_var.claudeConfig["temperature"],
            # top_p=global_var.config["top_p"],
            # frequency_penalty=global_var.config["frequency_penalty"],
            # presence_penalty=global_var.config["presence_penalty"],
            # max_tokens=global_var.config["max_tokens"],
            # n=global_var.config["n"]
        )

    res = response.choices[0].message.content
    return res


def get_question_split(question, answer, username, special_prompt, depth_suggestion=""):
    res = ""
    system_prompt = """Now here is a text related to the question and answer, which contains the questions or requests raised and the answers to them.

    Now you need to stand in the perspective of the questioner and ask follow-up questions to the content of the question and answer in order to better explore it.

    You only need to give the questions you ask(please ask 3 to 4 follow-up questions), and no other redundant content is required.

    Remember to use Chinese.

    For identifying easily the output， you should follow the format like that:
    {'output_question1','output_question2','output_question3'}"""
    user_prompt = "问题或要求：\n" + question + "回答：\n" + answer
    if depth_suggestion:
        user_prompt += "\n\n【追问策略建议】（小模型建议，供你生成追问时作为重要参考之一）：\n" + depth_suggestion
    client = OpenAI(
        api_key=_public_config.secret('OPENAI_API_KEY'),
        base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
        default_headers={"x-foo": "true"},
    )
    response = client.chat.completions.create(
        # model='claude-3-7-sonnet-20250219',
        model='claude-sonnet-4-20250514',
        messages=[
            {"role": "system", "content": system_prompt + special_prompt},
            {"role": "user", "content": user_prompt}],
        temperature=global_var.claudeConfig["temperature"],
        max_tokens=global_var.claudeConfig["max_tokens"]
        # top_p=global_var.config["top_p"],
        # frequency_penalty=global_var.config["frequency_penalty"],
        # presence_penalty=global_var.config["presence_penalty"],
        # n=global_var.config["n"]
    )

    res = response.choices[0].message.content
    begin = res.rfind('{')
    end = res.rfind('}')
    all_message = res[begin + 1:end]
    all_message = all_message.replace("'", '')
    question_list = all_message.split(',')
    return question_list