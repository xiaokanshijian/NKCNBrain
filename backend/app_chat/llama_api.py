import nkcn_public_config as _public_config
from openai import OpenAI
import time
import string
import re
from llm_langchain import global_var


async def make_requests_async(user_prompt, system_prompt=""):
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=_public_config.secret('NVIDIA_API_KEY')
    )

    response = client.chat.completions.create(
        model="meta/llama-3.1-405b-instruct",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=global_var.llama3Config["temperature"],
        top_p=global_var.llama3Config["top_p"],
        frequency_penalty=global_var.llama3Config["frequency_penalty"],
        presence_penalty=global_var.llama3Config["presence_penalty"],
        max_tokens=global_var.llama3Config["max_tokens"]
    )

    return response
