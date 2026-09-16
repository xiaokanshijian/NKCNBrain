from langchain_community.llms.huggingface_hub import HuggingFaceHub
from langchain_community.chat_models.huggingface import ChatHuggingFace, HuggingFaceEndpoint
from app_chat.core.models.base_model import BaseModel

class HuggingFaceModel(BaseModel):
    """
    HuggingFace 模型封装类。
    """

    def __init__(self, config: dict, prompts: dict = None) -> None:
        """
        初始化 HuggingFace 模型。

        :param config: 配置字典。
        """
        self.config = config
        self.model = None

    def initialize(self) -> None:
        """
        初始化 HuggingFace 模型实例。
        """
        try:
            print(f"初始化 HuggingFace 模型: {self.config}")
            self.model = ChatHuggingFace(llm = HuggingFaceEndpoint(**self.config))
        except Exception as e:
            raise RuntimeError(f"初始化 HuggingFace 模型失败: {e}")