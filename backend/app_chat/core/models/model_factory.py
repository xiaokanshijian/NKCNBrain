from typing import Dict, Any
from app_chat.core.models.openai_model import OpenAIModel
from app_chat.core.models.huggingface_model import HuggingFaceModel
from app_chat.core.models.anthropic_model import AnthropicModel
from app_chat.core.models.base_model import BaseModel

def create_model(model_type: str, config: Dict[str, Any], prompts: Dict[str, Any]) -> BaseModel:
    """
    根据类型创建模型实例。

    :param model_type: 模型类型（如 "openai"、"huggingface" 或 "anthropic"）。
    :param config: json配置中的config字段，包含信息：
        1. model_name：模型全称
        2. openai_api_key：OpenAI API密钥（如果需要）
        3. openai_api_base：OpenAI API基础URL（如果需要）
        4. anthropic_api_key：Anthropic API密钥（如果需要）
        5. anthropic_api_base：Anthropic API基础URL（如果需要）
        6. default_headers：默认请求头（如果需要）
        7. 超参数
        8. streaming：是否开启流式输出
    
    :return: 模型实例。
    """
    if model_type == "openai":
        return OpenAIModel(config, prompts)
    elif model_type == "huggingface":
        return HuggingFaceModel(config, prompts)
    elif model_type == "anthropic":
        return AnthropicModel(config, prompts)
    else:
        raise ValueError(f"未知的模型类型: {model_type}")
