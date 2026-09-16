from langchain_anthropic import ChatAnthropic
from app_chat.core.models.base_model import BaseModel
import anthropic
from typing import Dict, Any, List, AsyncGenerator
import asyncio
import json


class AnthropicModel(BaseModel):
    """
    Anthropic 模型封装类，支持原生Anthropic API调用和LangChain集成。
    """

    def __init__(self, config: dict, prompts: dict = None) -> None:
        """
        初始化 Anthropic 模型。

        :param config: 配置字典。
        :param prompts: 提示词配置字典。
        """
        super().__init__(config, prompts)
        self.config = config
        self.prompts = prompts
        self.model = None
        self.native_client = None

    def initialize(self) -> None:
        """
        初始化 Anthropic 模型实例。
        同时创建LangChain模型和原生Anthropic客户端。
        """
        try:
            # 为LangChain ChatAnthropic准备配置（移除不支持的参数）
            langchain_config = self.config.copy()
            # 移除LangChain不支持的参数
            langchain_config.pop("anthropic_api_base", None)
            langchain_config.pop("openai_api_base", None)
            langchain_config.pop("openai_api_key", None)  # 移除openai_api_key
            # 确保使用正确的API key参数名
            if "anthropic_api_key" not in langchain_config and "openai_api_key" in self.config:
                langchain_config["anthropic_api_key"] = self.config["openai_api_key"]

            # 只保留LangChain ChatAnthropic支持的参数
            supported_params = {
                "model": langchain_config.get("model_name"),
                "anthropic_api_key": langchain_config.get("anthropic_api_key"),
                "temperature": langchain_config.get("temperature", 0.7),
                "max_tokens": langchain_config.get("max_tokens", 4096),
                "streaming": langchain_config.get("streaming", True)
            }

            # 创建LangChain模型实例（用于文档问答等链式调用）
            self.model = ChatAnthropic(**supported_params)
            
            # 创建原生Anthropic客户端（用于普通问答）
            self.native_client = anthropic.Anthropic(
                api_key=self.config.get("anthropic_api_key", self.config.get("openai_api_key")),
                base_url=self.config.get("anthropic_api_base", self.config.get("openai_api_base"))
            )
            
        except Exception as e:
            raise RuntimeError(f"初始化 Anthropic 模型失败: {e}")

    def get_native_client(self):
        """
        获取原生Anthropic客户端，用于直接API调用。
        """
        return self.native_client

    async def create_native_chat_completion(self, messages: List[Dict[str, str]], 
                                          model: str, max_tokens: int = 1024, 
                                          temperature: float = 0.5) -> AsyncGenerator[str, None]:
        """
        使用原生Anthropic API创建聊天完成，支持流式输出。
        
        :param messages: 消息列表，格式为[{"role": "user", "content": "..."}]
        :param model: 模型名称
        :param max_tokens: 最大token数
        :param temperature: 温度参数
        :return: 异步生成器，产生流式响应内容
        """
        try:
            # # 转换消息格式为Anthropic格式
            # anthropic_messages = []
            # system_message = None
            #
            # for msg in messages:
            #     if msg["role"] == "system":
            #         system_message = msg["content"]
            #     elif msg["role"] == "user":
            #         anthropic_messages.append({
            #             "role": "user",
            #             "content": msg["content"]
            #         })
            #     elif msg["role"] == "assistant":
            #         anthropic_messages.append({
            #             "role": "assistant",
            #             "content": msg["content"]
            #         })

            # 使用专门的方法转换消息格式为Anthropic格式
            anthropic_messages, system_message = self.convert_messages_to_anthropic_format(messages)

            # 创建流式响应
            with self.native_client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=anthropic_messages,
                system=system_message
            ) as stream:
                for text in stream.text_stream:
                    yield text
                    
        except Exception as e:
            print(f"[ERROR] Anthropic原生API调用失败: {e}")
            yield f"Anthropic API调用出错: {str(e)}"

    def convert_messages_to_anthropic_format(self, messages: List[Dict[str, Any]]) -> tuple:
        """
        将OpenAI格式的消息转换为Anthropic格式。
        
        :param messages: OpenAI格式的消息列表
        :return: (anthropic_messages, system_message) 元组
        """
        anthropic_messages = []
        system_message = None
        
        for msg in messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            elif msg["role"] == "user":
                # 处理多模态内容
                if isinstance(msg["content"], list):
                    content = []
                    for item in msg["content"]:
                        if item["type"] == "text":
                            content.append({
                                "type": "text",
                                "text": item["text"]
                            })
                        elif item["type"] == "image_url":
                            # 转换图片格式
                            content.append({
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": item["image_url"]["url"].split(",")[1] if "," in item["image_url"]["url"] else item["image_url"]["url"]
                                }
                            })
                    anthropic_messages.append({
                        "role": "user",
                        "content": content
                    })
                else:
                    anthropic_messages.append({
                        "role": "user",
                        "content": msg["content"]
                    })
            elif msg["role"] == "assistant":
                anthropic_messages.append({
                    "role": "assistant",
                    "content": msg["content"]
                })
        
        return anthropic_messages, system_message
