import json
import os
from dotenv import load_dotenv

from typing import Dict, List
from app_chat.config.model_config import ModelConfig


_SECRET_KEY_FIELDS = {
    "openai_api_key",
    "anthropic_api_key",
    "huggingfacehub_api_token",
    "api_key",
}


def _looks_like_persisted_secret(value: str) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip()
    if not value or value.startswith("env:"):
        return False
    return value.startswith(("sk-", "nvapi-")) or len(value) >= 24


def _redact_secrets_for_disk(config):
    """Never write raw API keys back to model JSON files."""
    if isinstance(config, dict):
        redacted = {}
        for key, value in config.items():
            if key in _SECRET_KEY_FIELDS and _looks_like_persisted_secret(str(value)):
                redacted[key] = (
                    "env:ANTHROPIC_API_KEY"
                    if key == "anthropic_api_key"
                    else "env:NKCN_LLM_API_KEY"
                )
            else:
                redacted[key] = _redact_secrets_for_disk(value)
        return redacted
    if isinstance(config, list):
        return [_redact_secrets_for_disk(item) for item in config]
    return config


class ConfigManager:
    def __init__(self, config_dir: str, env_file_path: str = ".env"):
        self.config_dir = config_dir
        self.env_file_path = env_file_path
        self.configs = {}

        # 加载 .env 文件中的环境变量
        self._load_env_variables()

    def find_configs_by_abbr_name(self, model_name: str) -> List[str]:
        """
        查找指定目录下所有abbr_name字段与输入model_name匹配的json配置文件路径

        Args:
            model_name: 要匹配的模型名称(精确匹配abbr_name字段)

        Returns:
            list: 匹配的配置文件绝对路径列表
        """
        matched_files = []

        # 只检查指定目录下的json文件
        for filename in os.listdir(self.config_dir):
            if not filename.endswith('.json'):
                continue

            file_path = os.path.join(self.config_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                # 检查abbr_name字段是否匹配
                if config.get("abbr_name", "") == model_name:
                    matched_files.append(file_path)
            except (json.JSONDecodeError, IOError) as e:
                print(f"[WARNING] 读取配置文件 {filename} 时出错: {e}")
                continue

        return matched_files

    def _load_env_variables(self) -> None:
        """Load .env files if present. Missing files are not fatal."""
        candidates = [
            self.env_file_path,
            os.path.join(os.getcwd(), ".env"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".env"),
        ]
        loaded = False
        for path in candidates:
            if path and os.path.exists(path):
                load_dotenv(path, override=False)
                loaded = True
        if not loaded:
            print("[WARNING] 未找到 .env，模型 API Key 需通过环境变量注入。")

    def load_all_configs(self) -> None:
        """
        加载指定目录下的所有 .json 文件的配置（不包括子目录）。
        """
        if not os.path.exists(self.config_dir):
            raise FileNotFoundError(f"配置目录 '{self.config_dir}' 不存在。")

        for file_name in os.listdir(self.config_dir):
            if file_name.endswith(".json"):
                config_name = os.path.splitext(file_name)[0]
                try:
                    self.load_config(config_name)
                except (FileNotFoundError, ValueError) as e:
                    print(f"加载配置文件 '{file_name}' 失败: {e}")

    def load_config(self, config_name: str) -> None:
        """
        加载单个配置文件，并解析其中的环境变量。
        """
        file_path = os.path.join(self.config_dir, f"{config_name}.json")
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"配置文件 '{file_path}' 不存在。")

        with open(file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)

        # 解析配置中的环境变量
        self._resolve_env_variables(config_data)

        # 使用配置中的 model_name 作为键值
        model_name = config_data.get("abbr_name", config_name)  # 如果未定义 model_name，则回退到 config_name
        self.configs[model_name] = ModelConfig(config_data)

    def _resolve_env_variables(self, config: dict) -> None:
        """
        递归解析配置字典中的环境变量。
        """
        for key, value in config.items():
            if isinstance(value, dict):
                # 如果值是字典，递归解析
                self._resolve_env_variables(value)
            elif isinstance(value, str) and value.startswith("env:"):
                env_var_name = value[4:]
                env_var_value = os.getenv(env_var_name, "")
                if not env_var_value:
                    print(f"[WARNING] 环境变量 '{env_var_name}' 未设置。")
                config[key] = env_var_value
                

    def add_new_model_config(self, config_data: dict) -> None:
        """
        根据输入的字典构建 ModelConfig，并输出到新的 JSON 文件。
        自动配置输出路径为 config_dir/model_name.json。
        """
        print("[DEBUG] 添加新模型配置：", config_data)
        
        if "abbr_name" not in config_data:
            raise ValueError("配置数据中缺少 'abbr_name' 字段。")

        model_name = config_data["abbr_name"]
        print(f"[DEBUG] 模型名称: {model_name}")
        #  改为打开目录，然后再写入
        output_path = os.path.join(self.config_dir, f"{model_name}.json")
        
        # output_path = os.path.join(os.path.dirname(self.config_dir), f"{model_name}.json")
        print(f"[DEBUG] 输出路径: {output_path}")

        # 创建 ModelConfig 对象，加入当前model_config
        model_config = ModelConfig(config_data)
        self.configs[model_name] = model_config
        
        # 打印输出的配置数据：正在将config_data保存到 output_path
        print(f"[DEBUG] 正在将{model_name}配置数据保存到 {output_path}")
        

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(_redact_secrets_for_disk(config_data), f, ensure_ascii=False, indent=4)

        print(f"配置已保存到文件: {output_path}")


    def get_model_config(self, model_name: str) -> ModelConfig:
        """
        获取指定模型的配置。
        """
        if model_name not in self.configs:
            raise ValueError(f"模型 '{model_name}' 的配置未加载。")
        return self.configs[model_name]
    
    def get_all_model_names(self) -> list:
        """
        获取所有模型名称。
        """
        return list(self.configs.keys())
    
    def get_model_name_by_id(self, model_id: str) -> str:
        """
        根据模型ID获取对应的model_name, 如果未找到，返回 None
        """
        # for model_name, config in self.configs.items():
        #     if config.get_model_id() == model_id:
        #         print(f"[DEBUG] 根据model_id '{model_id}' 找到对应的模型名称: {model_name}")
        #         return model_name
        # raise ValueError(f"模型ID '{model_id}' 未找到。")
        for model_name, config in self.configs.items():
            if config.get_model_id() == model_id:
                print(f"[DEBUG] 根据model_id '{model_id}' 找到对应的模型名称: {model_name}")
                return model_name
        print(f"[DEBUG] 未找到模型ID '{model_id}' 对应的模型名称。")
        return None
    
    def get_model_id_by_name(self, model_name: str) -> str:
        """
        根据模型名称获取对应的model_id
        """
        if model_name not in self.configs:
            raise ValueError(f"模型 '{model_name}' 的配置未加载。")
        return self.configs[model_name].get_model_id()
    
    # 根据模型ID获取模型的sequence
    def get_model_sequence_by_id(self, model_id: str) -> str:
        """
        根据模型ID获取对应的sequence
        """
        for model_name, config in self.configs.items():
            if config.get_model_id() == model_id:
                return config.get_sequence()
        raise ValueError(f"模型ID '{model_id}' 未找到。")
    
    def update_model_hyper_para(self, model_id: str, hyper_para_dict: Dict[str, float]) -> None:
        """
        根据model_id，更新模型的超参数
        """
        for model_name, config in self.configs.items():
            if config.get_model_id() == model_id:
                config.get_hyper_para().update(hyper_para_dict)
                return
        raise ValueError(f"更新参数时模型ID '{model_id}' 未找到。")
    
    def get_model_hyper_para(self, model_id: str) -> Dict[str, float]:
        """
        获取指定模型的超参数。
        """
        for model_name, config in self.configs.items():
            if config.get_model_id() == model_id:
                return config.get_hyper_para().to_dict()
        raise ValueError(f"获取参数时模型ID '{model_id}' 未找到。")
    
    def get_model_sequence(self, model_name: str) -> str:
        """
        根据模型名称获取模型的sequence
        """
        if model_name not in self.configs:
            raise ValueError(f"模型 '{model_name}' 的配置未加载。")
        return self.configs[model_name].get_sequence()
    
    def get_model_by_seq(self, sequence: int) -> str:
        """
        根据sequence获取模型名称。
        """
        for model_name, config in self.configs.items():
            if config.get_sequence() == sequence:
                return model_name
        raise ValueError(f"序列号 '{sequence}' 未找到对应的模型。")
    
    def is_reasoner_model(self, model_name: str) -> bool:
        """
        根据模型名称判断是否为reasoner模型
        """
        if model_name not in self.configs:
            raise ValueError(f"模型 '{model_name}' 的配置未加载。")
        return self.configs[model_name].is_reasoner()
    
    # 判断模型是否支持图片
    def is_allow_img(self, model_name: str) -> bool:
        """
        判断模型是否支持图片输入
        """
        if model_name not in self.configs:
            raise ValueError(f"模型 '{model_name}' 的配置未加载。")
        return self.configs[model_name].is_allow_img()

    def get_user_prompt(self, model_name: str) -> str:
        """
        根据模型名称获取 user_prompt。
        """
        if model_name not in self.configs:
            raise ValueError(f"模型 '{model_name}' 的配置未加载。")
        return self.configs[model_name].get_user_prompt()

    def get_system_prompt(self, model_name: str) -> str:
        """
        根据模型名称获取 system_prompt。
        """
        if model_name not in self.configs:
            raise ValueError(f"模型 '{model_name}' 的配置未加载。")
        return self.configs[model_name].get_system_prompt()

    def model_exists(self, model_id: str) -> bool:
        """
        检查指定的模型名称是否存在于配置管理器中。

        Args:
            model_name: 要检查的模型名称

        Returns:
            bool: 如果模型存在返回True，否则返回False
        """
        # return model_name in self.configs
        for config in self.configs.values():
            if config.get_model_id() == model_id:
                return True
        return False


    def remove_model_config(self, model_name: str) -> None:
        """
        从配置管理器中删除指定模型的配置，并删除对应的配置文件。
        基于 abbr_name 字段匹配来删除配置文件。
        """
        print(f"[DEBUG] 尝试删除模型配置: {model_name}")

        if model_name not in self.configs:
            raise ValueError(f"模型 '{model_name}' 的配置未加载，无法删除。")

        # 使用新函数查找所有匹配文件
        matched_files = self.find_configs_by_abbr_name(model_name)

        # 从内存配置中删除
        del self.configs[model_name]
        print(f"[DEBUG] 已从配置字典中删除模型 '{model_name}'")

        # 删除所有匹配的文件
        deleted = False
        for file_path in matched_files:
            try:
                os.remove(file_path)
                deleted = True
                print(f"[DEBUG] 已删除配置文件: {file_path}")
            except OSError as e:
                print(f"[WARNING] 删除文件 {file_path} 时出错: {e}")

        if not deleted:
            print(f"[WARNING] 未找到模型 '{model_name}' 的配置文件")

        print(f"[DEBUG] 模型 '{model_name}' 的配置已成功删除")

    def update_model_config(self, config_data: dict) -> None:
        """
        更新现有模型配置，但保留原有的hyper_params和prompts不变。

        Args:
            config_data: 包含更新信息的配置数据字典

        Raises:
            ValueError: 如果模型ID不存在或配置数据不完整
        """
        print("[DEBUG] 更新模型配置：", config_data)

        # 检查必要字段
        if "model_id" not in config_data:
            raise ValueError("配置数据中缺少 'model_id' 字段。")

        model_id = config_data["model_id"]  # 一定得是ID，这是唯一的标识符

        # 查找对应的模型名称
        try:
            model_name = self.get_model_name_by_id(model_id)  # 旧版本的model_name
            print(f"[DEBUG] 找到模型名称: {model_name}")
        except ValueError:
            raise ValueError(f"模型ID '{model_id}' 不存在，无法更新。")

        # 获取现有配置 - 使用abbr_name查找
        existing_config = None
        matched_files = self.find_configs_by_abbr_name(model_name)

        if not matched_files:
            raise ValueError(f"模型 '{model_name}' 的配置文件不存在。")

        # 取第一个匹配的文件作为现有配置
        config_file_path = matched_files[0]
        with open(config_file_path, "r", encoding="utf-8") as f:
            existing_config = json.load(f)
        print(f"[DEBUG] 已加载现有配置: {config_file_path}")

        # 保留原有的hyper_params和prompts
        preserved_config = {}

        # 保留config中的hyper_params
        if "config" in existing_config and "config" in config_data:
            # 创建新的config字典，使用新配置的基本字段
            new_config = dict(config_data["config"])

            # 保留原有配置中的超参数相关字段
            for key, value in existing_config["config"].items():
                if key not in ["model_name", "openai_api_key", "openai_api_base", "default_headers"]:
                    new_config[key] = value

            preserved_config["config"] = new_config
        else:
            # 如果新配置中没有config字段，直接使用原有的
            preserved_config["config"] = existing_config.get("config", {})

        # 保留原有的prompts
        if "prompts" in existing_config:
            preserved_config["prompts"] = existing_config["prompts"]

        # 创建更新后的配置
        updated_config = {**config_data}

        # 更新config和prompts字段
        if "config" in preserved_config:
            updated_config["config"] = preserved_config["config"]
        if "prompts" in preserved_config:
            updated_config["prompts"] = preserved_config["prompts"]

        # 如果新配置中有abbr_name且与原来不同，需要处理文件名变更
        new_model_name = config_data.get("abbr_name", model_name)
        if new_model_name != model_name:
            print(f"[DEBUG] 模型名称变更: {model_name} -> {new_model_name}")

            # 从旧配置中删除
            if model_name in self.configs:
                del self.configs[model_name]

            # 删除所有abbr_name匹配的配置文件
            for file_path in self.find_configs_by_abbr_name(model_name):
                try:
                    os.remove(file_path)
                    print(f"[DEBUG] 删除abbr_name匹配的配置文件: {file_path}")
                except OSError as e:
                    print(f"[WARNING] 删除文件 {file_path} 时出错: {e}")

        # 更新配置对象
        self.configs[new_model_name] = ModelConfig(updated_config)

        # 保存更新后的配置到文件
        output_path = os.path.join(self.config_dir, f"{new_model_name}.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(_redact_secrets_for_disk(updated_config), f, ensure_ascii=False, indent=4)

        print(f"[DEBUG] 配置已更新并保存到: {output_path}")

        # 如果模型名称变更，删除旧的配置文件
        if new_model_name != model_name:
            try:
                os.remove(config_file_path)
                print(f"[DEBUG] 删除旧配置文件: {config_file_path}")
            except OSError as e:
                print(f"[WARNING] 删除旧配置文件时出错: {e}")


config_dir = os.path.join("app_chat", "config", "model_config")
config_manager = ConfigManager(config_dir=config_dir)
# config_manager = ConfigManager(config_dir="app_chat\\config\\model_config")
config_manager.load_all_configs()


