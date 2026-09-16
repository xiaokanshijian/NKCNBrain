from langchain_community.chat_models.openai import ChatOpenAI
# from core.models.base_model import BaseModel
# from base_model import BaseModel
from app_chat.core.models.base_model import BaseModel


def _is_moonshot_fixed_sampling_model_name(model_name: str) -> bool:
    name = (model_name or '').strip().lower()
    if not name:
        return False
    return name.startswith('kimi-k3') or name.startswith('kimi-k2.7')


class OpenAIModel(BaseModel):
    """
    OpenAI 模型封装类。
    """

    def __init__(self, config: dict, prompts: dict = None) -> None:
        """
        初始化 OpenAI 模型。

        :param config: 配置字典。
        """
        super().__init__(config, prompts)
        self.config = config
        self.prompts = prompts
        self.model = None

    def initialize(self) -> None:
        """
        初始化 OpenAI 模型实例。
        """
        try:
            # 🔥 检测是否为Claude模型（通过模型名称或base_url判断）
            model_name = self.config.get("model_name", "").lower()
            base_url = self.config.get("openai_api_base", "").lower()
            is_claude_model = (
                    "claude" in model_name or
                    "anthropic" in base_url
            )

            # 🔥 对于Claude模型，移除不支持的参数（如stop/stop_sequences）
            init_config = self.config.copy()
            if is_claude_model:
                # Claude模型不支持stop参数，移除它
                init_config.pop("stop", None)
                init_config.pop("stop_sequences", None)
                init_config.pop("top_p", None)
                print(f"[INFO] 检测到Claude模型，已移除stop/stop_sequences参数")

            # Moonshot kimi-k3 / k2.7：采样参数固定，否则 ChatOpenAI 会把非法 penalty 打进请求
            if _is_moonshot_fixed_sampling_model_name(model_name):
                init_config['temperature'] = 1.0
                init_config['presence_penalty'] = 0
                init_config['frequency_penalty'] = 0
                init_config['top_p'] = 0.95
                init_config['n'] = 1
                init_config.pop('stop', None)
                init_config.pop('stop_sequences', None)
                print(
                    f"[INFO] Moonshot固定采样模型 {model_name}: "
                    f"temperature=1, presence/frequency_penalty=0, 已移除 stop"
                )

            if "max_tokens" in init_config:
                print(f"[INFO] ChatOpenAI初始化时传递的max_tokens: {init_config.get('max_tokens')}")
            self.model = ChatOpenAI(**init_config)
        except Exception as e:
            raise RuntimeError(f"初始化 OpenAI 模型失败: {e}")
