#encoding=utf-8
import os
import re
import argparse
import string
from openai import OpenAI

from llm_langchain import global_var


def make_requests(
        engine, prompts, api_key=None
):

    client = OpenAI(
        api_key=api_key,
    )

    response = client.chat.completions.create(
        model=engine,
        messages=[{"role": "user", "content": prompts}],
    )
    return response



def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_file",
        type=str,
        help="The input file that contains the prompts to GPT3.",
    )
    parser.add_argument(
        "--output_file",
        type=str,
        help="The output file to save the responses from GPT3.",
    )
    parser.add_argument(
        "--engine",
        type=str,
        help="The openai GPT3 engine to use.",
    )
    parser.add_argument(
        "--max_tokens",
        default=500,
        type=int,
        help="The max_tokens parameter of GPT3.",
    )
    parser.add_argument(
        "--temperature",
        default=0.7,
        type=float,
        help="The temprature of GPT3.",
    )
    parser.add_argument(
        "--top_p",
        default=0.5,
        type=float,
        help="The `top_p` parameter of GPT3.",
    )
    parser.add_argument(
        "--frequency_penalty",
        default=0,
        type=float,
        help="The `frequency_penalty` parameter of GPT3.",
    )
    parser.add_argument(
        "--presence_penalty",
        default=0,
        type=float,
        help="The `presence_penalty` parameter of GPT3.",
    )
    parser.add_argument(
        "--stop_sequences",
        default=["\n\n"],
        nargs="+",
        help="The `stop_sequences` parameter of GPT3.",
    )
    parser.add_argument(
        "--logprobs",
        default=5,
        type=int,
        help="The `logprobs` parameter of GPT3"
    )
    parser.add_argument(
        "--n",
        type=int,
        help="The `n` parameter of GPT3. The number of responses to generate."
    )
    parser.add_argument(
        "--best_of",
        type=int,
        help="The `best_of` parameter of GPT3. The beam size on the GPT3 server."
    )
    parser.add_argument(
        "--use_existing_responses",
        action="store_true",
        help="Whether to use existing responses from the output file if it exists."
    )
    parser.add_argument(
        "--request_batch_size",
        default=20,
        type=int,
        help="The number of requests to send to GPT3 at a time."
    )
    return parser.parse_args()


def extract_sentences(text):
    # 定义正则表达式模式：序号+点开始
    pattern = r'\b\d+\.\s.*?(?=\n{2,}|$)'
    # 匹配正则表达式模式
    sentences = re.findall(pattern, text, re.DOTALL)
    return sentences


def find_word_in_string(w, s):
    return re.compile(r'\b({0})\b'.format(w), flags=re.IGNORECASE).search(s)


def post_process_gpt4_response(response):
    if response is None or response.choices[0].finish_reason == "length":
        return []
    raw_instructions = extract_sentences(response.choices[0].message.content)
    # 列表所有的inst合并成一个长串用作切分
    inst_long_str = merged_string = '\n'.join(raw_instructions)
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
        if any(find_word_in_string(word, inst) for word in ["image", "images", "graph", "graphs", "picture", "pictures", "file", "files", "map", "maps", "draw", "plot", "go to"]):
            continue
        # We found that the model tends to add "write a program" to some existing instructions, which lead to a lot of such instructions.
        # And it's a bit comfusing whether the model need to write a program or directly output the result.
        # Here we filter them out.
        # Note this is not a comprehensive filtering for all programming instructions.
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


def make_gpt4o_image_text_requests(user_prompt, base64_image, system_prompt="", use_fixed_params=False, text_after_image=None):
    client = OpenAI(
        api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
        base_url='https://chat.cloudapi.vip/v1/',
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
            model='gpt-4o',
            messages=messages,
            temperature=0,
            max_tokens=2048
        )
    else:
        # 使用global_var.config参数（保持向后兼容）
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=messages,
            temperature=global_var.config["temperature"],
            top_p=global_var.config["top_p"],
            frequency_penalty=global_var.config["frequency_penalty"],
            presence_penalty=global_var.config["presence_penalty"],
            max_tokens=global_var.config["max_tokens"],
            n=global_var.config["n"]
        )

    res = response.choices[0].message.content
    return res


def make_gpt4o_image_text_requests_stream(user_prompt, base64_image, system_prompt="", use_fixed_params=False,
                                          text_after_image=None):
    """流式版本的GPT-4o图片文本请求"""
    client = OpenAI(
        api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
        base_url='https://chat.cloudapi.vip/v1/',
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
        # 使用固定参数，开启流式
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=messages,
            temperature=0,
            max_tokens=2048,
            stream=True
        )
    else:
        # 使用global_var.config参数，开启流式
        response = client.chat.completions.create(
            model='gpt-4o',
            messages=messages,
            temperature=global_var.config["temperature"],
            top_p=global_var.config["top_p"],
            frequency_penalty=global_var.config["frequency_penalty"],
            presence_penalty=global_var.config["presence_penalty"],
            max_tokens=global_var.config["max_tokens"],
            n=global_var.config["n"],
            stream=True
        )

    # return response
    for chunk in response:
        if chunk.choices[0].delta.content is not None:
            yield chunk.choices[0].delta.content


def make_gpt4o_text_requests(user_prompt, system_prompt="", use_fixed_params=False):
    res = ""
    client = OpenAI(
        api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
        base_url='https://chat.cloudapi.vip/v1/',
        default_headers={"x-foo": "true"},
    )
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}],
        temperature=global_var.config["temperature"],
        top_p=global_var.config["top_p"],
        frequency_penalty=global_var.config["frequency_penalty"],
        presence_penalty=global_var.config["presence_penalty"],
        max_tokens=global_var.config["max_tokens"],
        n=global_var.config["n"]
    )

    res = response.choices[0].message.content
    return res


async def make_gpt4o_text_requests_async(user_prompt, system_prompt=""):
    res = ""
    client = OpenAI(
        api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
        base_url='https://chat.cloudapi.vip/v1/',
        default_headers={"x-foo": "true"},
    )
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}],
        temperature=global_var.config["temperature"],
        top_p=global_var.config["top_p"],
        frequency_penalty=global_var.config["frequency_penalty"],
        presence_penalty=global_var.config["presence_penalty"],
        max_tokens=global_var.config["max_tokens"],
        n=global_var.config["n"]
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
        api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
        base_url='https://chat.cloudapi.vip/v1/',
        default_headers={"x-foo": "true"},
    )
    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[
            {"role": "system", "content": system_prompt + special_prompt},
            {"role": "user", "content": user_prompt}],
        temperature=global_var.config["temperature"],
        top_p=global_var.config["top_p"],
        frequency_penalty=global_var.config["frequency_penalty"],
        presence_penalty=global_var.config["presence_penalty"],
        max_tokens=global_var.config["max_tokens"],
        n=global_var.config["n"]
    )

    res = response.choices[0].message.content
    begin = res.rfind('{')
    end = res.rfind('}')
    all_message = res[begin + 1:end]
    all_message = all_message.replace("'", '')
    question_list = all_message.split(',')
    return question_list


if __name__ == "__main__":
    api_key = os.environ.get("OPENAI_API_KEY", "")

    chinese_input = 'Come up with a series of tasks with the same format:\n1. 如何使用信息技术为思政教育赋能？\n2. 请详细说明劳模精神、劳动精神、工匠精神的内涵和作用分别是什么，以及如何培育这些精神\n3. 红蓝融合中，理论和实践哪一个更重要？\n4. 见义勇为是否值得提倡？\n5. 信息时代，如何激发创新活力，产出创新成果？\n6. 请列举几个知行合一的名人事例\n7. 领导让我作一周工作的汇报总结，但我这周没有做实质性的工作，我该怎么办？\n8. 为什么要讲红蓝融合，其内涵是什么？\n9.'
    input = "Come up with a series of tasks with the same format:1.What's your name? 2.How's the weather? 3.How old are you? 4."
    multiple_chinese_input = [chinese_input] * 3
    instructions = []
    # results = make_requests(
    #     engine="gpt-4-turbo-preview",
    #     prompts=chinese_input,
    #     api_key=api_key
    # )
    # print(post_process_gpt4_response(results))

    for input in multiple_chinese_input:
        print(input)
        results = make_requests(
            engine="gpt-4-turbo-preview",
            prompts=input,
            api_key=api_key
        )
        print(post_process_gpt4_response(results))
        instructions += post_process_gpt4_response(results)
    print(instructions)
