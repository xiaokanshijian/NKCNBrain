from typing import Dict, Any

class HyperPara:
    """
    管理超参数的类。
    """

    def __init__(self, temperature: float = 0.7, top_p: float = 1.0, frequency_penalty: int = 0,
                 presence_penalty: int = 0, max_tokens: int = 4096, n: int = 1):
        self.temperature = temperature
        self.top_p = top_p
        self.frequency_penalty = frequency_penalty
        self.presence_penalty = presence_penalty
        self.max_tokens = max_tokens
        self.n = n
        

    def update(self, hyper_para_dict: Dict[str, Any]) -> None:
        '''
        更新超参数
        输入字典格式的超参数，更新当前对象的超参数
        如果字典中没有定义某个超参数，则不更新该超参数
        '''
        for key, value in hyper_para_dict.items():
            if hasattr(self, key):
                setattr(self, key, value)
                
    # 将超参数转换为字典格式
    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "max_tokens": self.max_tokens,
            "n": self.n
        }


class ModelConfig:
    """
    管理单个模型的配置信息。
    """

    def __init__(self, config_data: Dict[str, Any]):
        self.config_data = config_data

        # 超参数初始值，如果json文件中没有定义，则使用默认值
        # 如果json文件中定义了超参数，但是没有定义某个超参数，这个超参数得使用默认值
        self.hyper_para = HyperPara(
            temperature=self.config_data.get("config").get("temperature", 0.7),
            top_p=self.config_data.get("config").get("top_p", 1.0),
            frequency_penalty=self.config_data.get("config").get("frequency_penalty", 0),
            presence_penalty=self.config_data.get("config").get("presence_penalty", 0),
            max_tokens=self.config_data.get("config").get("max_tokens", 4096),
            n=self.config_data.get("config").get("n", 1)
        )
        
        # 检查输入的所有超参数
        print("[INFO] 超参数检查：")
        for key, value in self.hyper_para.to_dict().items():
            if key in config_data:
                print(f"  {key}: {value} (从配置文件中读取)")
            else:
                print(f"  {key}: {value} (使用默认值)")

    # def is_allow_img(self) -> bool:
    #     """判断模型是否可以接受图片输入"""
    #     return self.config_data.get("allow_img", False)

    def get_hyper_para(self) -> HyperPara:
        """获取超参数"""
        return self.hyper_para

    def get_model_name(self) -> str:
        """获取模型名称"""
        return self.config_data.get("abbr_name")
    
    def get_model_id(self) -> str:
        """获取模型 ID"""
        return self.config_data.get("model_id")
    
    def get_full_name(self) -> str:
        """获取模型的完整名称"""
        return self.config_data.get("config", {}).get("model_name")
    
    def get_base_url(self) -> str:
        """获取模型的基础 URL"""
        config = self.config_data.get("config", {})
        model_type = self.config_data.get("model_type")

        if model_type == "anthropic":
            # 对于Anthropic模型，优先使用anthropic_api_base，如果没有则使用openai_api_base
            return config.get("anthropic_api_base", config.get("openai_api_base", ""))
        else:
            # 对于其他模型，使用openai_api_base
            return config.get("openai_api_base", "")

    def get_sequence(self) -> int:
        """获取 sequence 值"""
        return self.config_data.get("sequence")

    def get_model_type(self) -> str:
        """获取 model_type 值"""
        return self.config_data.get("model_type")

    def get_config(self) -> Dict[str, Any]:
        """获取 config 部分"""
        config = self.config_data.get("config", {}).copy()  # Create a copy to avoid modifying original
        
        if self.config_data.get("model_type") == "huggingface":
            # Perform transformations for HuggingFace models
            if "model_name" in config:
                config["repo_id"] = config.pop("model_name")
            if "openai_api_key" in config:
                config["huggingfacehub_api_token"] = config.pop("openai_api_key")
            if "openai_api_base" in config:
                config.pop("openai_api_base")
            
            # Add task field if not present
            if "task" not in config:
                config["task"] = "text-generation"

        elif self.config_data.get("model_type") == "anthropic":
            # Perform transformations for Anthropic models
            # 保持原有的openai_api_key和openai_api_base字段，用于向后兼容
            # 同时添加anthropic_api_key和anthropic_api_base字段
            if "openai_api_key" in config and "anthropic_api_key" not in config:
                config["anthropic_api_key"] = config["openai_api_key"]
            if "openai_api_base" in config and "anthropic_api_base" not in config:
                config["anthropic_api_base"] = config["openai_api_base"]

            # 确保模型名称正确
            if "model_name" in config:
                # 如果模型名称包含claude，确保格式正确
                model_name = config["model_name"]
                if "claude" in model_name.lower() and not model_name.startswith("claude-"):
                    # 转换格式，例如 "claude-3-5-sonnet-20241022-X" -> "claude-3-5-sonnet-20241022"
                    if model_name.endswith("-X"):
                        config["model_name"] = model_name[:-2]

            # 为LangChain ChatAnthropic清理配置，移除不支持的参数
            # 但保留anthropic_api_key用于原生客户端
            config.pop("openai_api_base", None)  # LangChain ChatAnthropic不支持这个参数
            config.pop("anthropic_api_base", None)  # LangChain ChatAnthropic不支持这个参数

        return config

    # def get_config(self) -> Dict[str, Any]:
    #     """获取 config 部分"""
    #     config = self.config_data.get("config", {}).copy()  # Create a copy to avoid modifying original
        
    #     if self.config_data.get("model_type") == "huggingface":
    #         # Initialize model_kwargs if not present
    #         model_kwargs = config.pop("model_kwargs", {})
            
    #         # Fields that should remain at the top level
    #         preserved_fields = {
    #             "repo_id": config.pop("model_name", ""),
    #             "huggingfacehub_api_token": config.pop("openai_api_key", ""),
    #             "task": "text-generation"
    #         }
            
    #         # Remove openai_api_base if present
    #         config.pop("openai_api_base", None)
            
    #         # All remaining fields go into model_kwargs
    #         model_kwargs.update(config)
            
    #         # Combine preserved fields with model_kwargs
    #         final_config = {**preserved_fields}
    #         if model_kwargs:  # Only add model_kwargs if not empty
    #             final_config["model_kwargs"] = model_kwargs
                
    #         return final_config
        
    #     return config

    def get_prompts(self) -> Dict[str, Any]:
        """获取 prompts 部分"""
        return self.config_data.get("prompts", {})

    def get_system_prompt(self) -> str:
        """返回 system_prompt（在 prompts 字段下）"""
        return self.config_data.get("prompts", {}).get("system_prompt", "")

    def get_user_prompt(self) -> str:
        """返回 user_prompt（在 prompts 字段下）"""
        return self.config_data.get("prompts", {}).get("user_prompt", "")

    def get_description(self) -> str:
        """获取模型的描述信息"""
        return self.config_data.get("description", "")

    def get_response_speed(self) -> str:
        """
        获取模型的响应速度等级。

        枚举值说明：
        - 'fast'：
        - 'medium_fast'：
        - 'medium_slow'：
        - 'slow'：

        返回:
            str: 响应速度等级
        """
        return self.config_data.get("response_speed", "medium_fast")

    def get_reasoning_level(self) -> str:
        """
        获取模型的推理能力等级。

        枚举值说明：
        - 'high'：具备高水平逻辑推理、数学计算、复杂任务处理能力
        - 'medium'：具备基础推理能力，适用于简单逻辑推理任务
        - 'low'：仅支持非常有限的推理能力
        - 'none'：不支持推理（默认值）

        返回:
            str: 推理能力等级
        """
        return self.config_data.get("reasoning_level", "low_nonnative")

    def get_multimodal_level(self) -> str:
        """
        获取模型的多模态能力等级。

        枚举值说明：
        - 'high'：支持多种模态（如文本 + 图像 + 视频 + 音频等）
        - 'medium'：支持图像和文本组合输入输出
        - 'low'：支持单一非文本模态（如音频或图像中的一种）
        - 'none'：仅支持纯文本输入输出（默认值）

        返回:
            str: 多模态能力等级
        """
        return self.config_data.get("multimodal_level", "none")

    def is_reasoner(self) -> bool:
        """
        判断是否是原生推理模型
        """
        # return self.get_reasoning_level() != "none"
        return self.get_reasoning_level().endswith("_native")

    def is_allow_img(self) -> bool:
        """
        判断是否支持图片输入（向后兼容）
        只要 multimodal_level 不是 'none'，就认为支持多模态
        """
        return self.get_multimodal_level() != "none"

    # def is_reasoner(self) -> bool:
    #     """判断是否为推理模型"""
    #     return self.config_data.get("reasoner", False)

