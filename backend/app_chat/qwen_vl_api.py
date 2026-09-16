import os
from openai import OpenAI

client = OpenAI(
    # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx"
    api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
)
# client = OpenAI(
#     api_key=os.environ.get("NKCN_LLM_API_KEY", ""),
#     base_url='https://chat.cloudapi.vip/v1/',
#     default_headers={"x-foo": "true"},
# )


def make_image_text_requests(user_prompt, base64_image, system_prompt="You are a helpful assistant.", use_fixed_params=False, text_after_image=None):
    client = OpenAI(
        api_key=os.environ.get("DASHSCOPE_API_KEY", ""),
        base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
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
            model='qwen-vl-max-latest',
            messages=messages,
            temperature=0,
            max_tokens=2048
        )
    else:
        # 使用global_var.config参数（保持向后兼容）
        response = client.chat.completions.create(
            model='qwen-vl-max-latest',
            messages=messages,
            # temperature=global_var.config["temperature"],
            # top_p=global_var.config["top_p"],
            # frequency_penalty=global_var.config["frequency_penalty"],
            # presence_penalty=global_var.config["presence_penalty"],
            # max_tokens=global_var.config["max_tokens"],
            # n=global_var.config["n"]
        )

    res = response.choices[0].message.content
    return res


def generate(image_urls: list, user_prompt: str, image_prompts: list = None):
    global client
    user_content = []
    for idx, image_url in enumerate(image_urls):
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            }
        )
        if image_prompts is not None and idx < len(image_prompts):
            user_content.append(
                {
                    "type": "text",
                    "text": image_prompts[idx]
                }
            )

    user_content.append({"type": "text", "text": user_prompt})
    completion = client.chat.completions.create(
        model="qwen-vl-max-latest",  # 此处以qwen-vl-max-latest为例，可按需更换模型名称。模型列表：https://help.aliyun.com/model-studio/getting-started/models
        messages=[
            {"role":"system","content":[{"type": "text", "text": "You are a helpful assistant."}]},
            {"role": "user","content":user_content}
        ],
    )

    return completion.choices[0].message.content


def generate_stream(image_urls: list, user_prompt: str, image_prompts: list = None):
    global client
    answer_content = ""     # 定义完整回复
    user_content = []
    for idx, image_url in enumerate(image_urls):
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            }
        )
        if image_prompts is not None and idx < len(image_prompts):
            user_content.append(
                {
                    "type": "text",
                    "text": image_prompts[idx]
                }
            )

    user_content.append({"type": "text", "text": user_prompt})
    completion = client.chat.completions.create(
        model="qwen-vl-max-latest",  # 此处以qwen-vl-max-latest为例，可按需更换模型名称。模型列表：https://help.aliyun.com/model-studio/getting-started/models
        messages=[
            {"role":"system","content":[{"type": "text", "text": "You are a helpful assistant."}]},
            {"role": "user","content":user_content}
        ],
        stream=True
    )

    for chunk in completion:
        # 如果chunk.choices为空，则打印usage
        if not chunk.choices:
            print("\nUsage:")
            print(chunk.usage)
        else:
            delta = chunk.choices[0].delta
            # 打印回复过程
            print(delta.content, end='', flush=True)
            answer_content += delta.content
    return answer_content


def generate_reasoning(image_urls: list, user_prompt: str):
    global client
    reasoning_content = ""  # 定义完整思考过程
    answer_content = ""     # 定义完整回复
    is_answering = False   # 判断是否结束思考过程并开始回复
    user_content = []
    for image_url in image_urls:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": image_url
                }
            }
        )
    user_content.append({"type": "text", "text": user_prompt})
    completion = client.chat.completions.create(
        model="qvq-max",
        messages=[
            {"role": "user", "content": user_content,}
        ],
        stream=True,
    )
    print("\n" + "=" * 20 + "思考过程" + "=" * 20 + "\n")

    for chunk in completion:
        # 如果chunk.choices为空，则打印usage
        if not chunk.choices:
            print("\nUsage:")
            print(chunk.usage)
        else:
            delta = chunk.choices[0].delta
            # 打印思考过程
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content != None:
                print(delta.reasoning_content, end='', flush=True)
                reasoning_content += delta.reasoning_content
            else:
                # 开始回复
                if delta.content != "" and is_answering is False:
                    print("\n" + "=" * 20 + "完整回复" + "=" * 20 + "\n")
                    is_answering = True
                # 打印回复过程
                print(delta.content, end='', flush=True)
                answer_content += delta.content
    return reasoning_content, answer_content
