import nkcn_public_config as _public_config
from openai import OpenAI
import time
import string
import re
from llm_langchain import global_var


def find_word_in_string(w, s):
    return re.compile(r'\b({0})\b'.format(w), flags=re.IGNORECASE).search(s)


def extract_sentences(text):
    # 定义正则表达式模式：序号+点开始
    pattern = r'\b\d+\.\s.*?(?=\n{2,}|$)'
    # 匹配正则表达式模式
    sentences = re.findall(pattern, text, re.DOTALL)
    return sentences


def post_process_kimi_response(response):
    if response is None or response.choices[0].finish_reason=='length':
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
        if any(find_word_in_string(word, inst) for word in
               ["image", "images", "graph", "graphs", "picture", "pictures", "file", "files", "map", "maps", "draw",
                "plot", "go to"]):
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


def make_requests(prompt, api_key, is_completion, temperature=0.8):

    if api_key is None:
        API_KEY = _public_config.secret('DEEPSEEK_API_KEY')
    else:
        API_KEY = api_key

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

    client = OpenAI(
        api_key=API_KEY,
        base_url="https://api.deepseek.com",
    )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": role},
            {"role": "user", "content": prompt}
        ],
        temperature=global_var.deepseekConfig["temperature"],
        top_p=global_var.deepseekConfig["top_p"],
        frequency_penalty=global_var.deepseekConfig["frequency_penalty"],
        presence_penalty=global_var.deepseekConfig["presence_penalty"],
        max_tokens=global_var.deepseekConfig["max_tokens"]
    )

    print("temperature="+str(global_var.deepseekConfig["temperature"]))
    return response


async def make_requests_async(prompt, api_key, is_completion, system_prompt, temperature=0.8):

    if api_key is None:
        API_KEY = _public_config.secret('DEEPSEEK_API_KEY')
    else:
        API_KEY = api_key

    if system_prompt != "":
        role = system_prompt
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

    client = OpenAI(
        api_key=API_KEY,
        base_url="https://api.deepseek.com",
    )
    # client = OpenAI(
    #     api_key='[redacted]',
    #     base_url='http://localhost:9999/v1/',
    #     default_headers={"x-foo": "true"}
    # )

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": role},
            {"role": "user", "content": prompt}
        ],
        temperature=global_var.deepseekConfig["temperature"],
        top_p=global_var.deepseekConfig["top_p"],
        frequency_penalty=global_var.deepseekConfig["frequency_penalty"],
        presence_penalty=global_var.deepseekConfig["presence_penalty"],
        max_tokens=global_var.deepseekConfig["max_tokens"]
    )

    print("temperature="+str(global_var.deepseekConfig["temperature"]))
    return response


if __name__ == '__main__':
    MOONSHOT_API_KEY = _public_config.secret('KIMI_API_KEY') # from chen lei
    # prompt_completion = "按照相同格式提出若干相关的问题：1.西红柿炒鸡蛋怎么做？2.拍黄瓜是哪里的凉菜？3.枸杞在烹饪中的作用有哪些？4."
    prompt_completion = 'Come up with a series of tasks with the same format:\n1. 如何使用信息技术为思政教育赋能？\n2. 请详细说明劳模精神、劳动精神、工匠精神的内涵和作用分别是什么，以及如何培育这些精神\n3. 红蓝融合中，理论和实践哪一个更重要？\n4. 见义勇为是否值得提倡？\n5. 信息时代，如何激发创新活力，产出创新成果？\n6. 请列举几个知行合一的名人事例\n7. 领导让我作一周工作的汇报总结，但我这周没有做实质性的工作，我该怎么办？\n8. 为什么要讲红蓝融合，其内涵是什么？\n9.'
    res = make_requests(prompt_completion, None, True, 0.8)
    insts = []
    insts += post_process_kimi_response(res)
    print(insts)