from abc import ABC, abstractmethod
from typing import Any, Tuple, List

from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import HumanMessagePromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate


class BaseModel(ABC):
    """
    基础模型类，定义所有模型需要实现的通用接口。
    """

    def __init__(self, config: dict, prompts: dict):
        """
        初始化模型配置。
        
        :param config: 模型配置字典。
        """
        self.config = config
        self.prompts = prompts
        self.model = None

    @abstractmethod
    def initialize(self) -> None:
        """初始化模型"""
        pass
    
    def get_model(self) -> Any:
        """
        获取模型实例
        :param temperature: 可选，温度参数
        :return: 模型实例
        """
        return self.model
    
    def get_sum_msg(self) -> list:
        """
        从JSON配置动态生成消息模板列表
        :return: 由MessagePromptTemplate对象组成的列表
        """
        sum_msg = self.prompts.get("sum_msg")  # 假设已通过类属性获取配置
        messages = []
        
        print("[DEBUG] sum_msg:", sum_msg)
        
        for msg_config in sum_msg:
            msg_type = msg_config["type"]
            
            if msg_type == "system":
                template = msg_config["template"]
                messages.append(SystemMessagePromptTemplate.from_template(template))
            elif msg_type == "human":
                template = msg_config["template"]
                messages.append(HumanMessagePromptTemplate.from_template(template))
            elif msg_type == "placeholder":
                variable_name = msg_config["variable_name"]
                messages.append(MessagesPlaceholder(variable_name=variable_name))
            # 可以继续添加其他类型的处理...
        print(f"[INFO] sum_msg: {messages}")
        
        return messages
    
    def get_que_msg(self) -> Tuple[List, List]:
        """
        从JSON配置动态生成问题消息模板
        返回: (messages_1, messages_2) 元组，每个元素是Message对象列表
        """
        que_msg = self.prompts.get("que_msg")  # 假设已通过类属性获取配置
        
        def build_messages(config_list: list) -> list:
            """内部函数：将单个消息配置列表转换为Message对象列表"""
            messages = []
            for msg_config in config_list:
                msg_type = msg_config["type"]
                
                if msg_type == "system":
                    if "template" in msg_config:  # 模板型系统消息
                        messages.append(
                            SystemMessagePromptTemplate.from_template(msg_config["template"])
                        )
                    elif "content" in msg_config:  # 固定内容系统消息
                        messages.append(SystemMessage(content=msg_config["content"]))
                        
                elif msg_type == "human":
                    messages.append(
                        HumanMessagePromptTemplate.from_template(msg_config["template"])
                    )
                    
                elif msg_type == "placeholder":
                    messages.append(
                        MessagesPlaceholder(variable_name=msg_config["variable_name"])
                    )
                    
            return messages
        
        # 分别构建两个消息组
        messages_1 = build_messages(que_msg["messages_1"])
        messages_2 = build_messages(que_msg["messages_2"])
        
        print(f"[INFO] que_msg: {messages_1}, {messages_2}")
        
        return messages_1, messages_2
    
    def get_qa_msg(self) -> Tuple[List, List]:
        """
        从JSON配置动态生成问答消息模板
        返回: (messages, messages_2) 元组，每个元素是Message对象列表
        """
        qa_msg = self.prompts.get("qa_msg")  # 假设已通过类属性获取配置
        
        # 处理主消息列表
        messages = []
        for msg_config in qa_msg["messages"]:
            msg_type = msg_config["type"]
            
            if msg_type == "system":
                messages.append(
                    SystemMessagePromptTemplate.from_template(msg_config["template"])
                )
            elif msg_type == "human":
                messages.append(
                    HumanMessagePromptTemplate.from_template(msg_config["template"])
                )
        
        # 处理附加消息列表
        messages_2 = []
        for msg_config in qa_msg["messages_2"]:
            if msg_config["type"] == "placeholder":
                messages_2.append(
                    MessagesPlaceholder(variable_name=msg_config["variable_name"])
                )
        
        print(f"[INFO] qa_msg: {messages}, {messages_2}")
        return messages, messages_2
    
    def get_topic_msg(self) -> Tuple[List, List]:
        """
        从JSON配置动态生成主题消息模板
        返回: (messages_1, messages_2) 元组，每个元素是Message对象列表
        """
        topic_msg = self.prompts.get("topic_msg")  # 假设已通过类属性获取配置
        
        # 处理messages_1
        messages_1 = []
        for msg_config in topic_msg["messages_1"]:
            if msg_config["type"] == "system":
                if "template" in msg_config:
                    messages_1.append(
                        SystemMessagePromptTemplate.from_template(msg_config["template"])
                    )
                elif "content" in msg_config:
                    messages_1.append(
                        SystemMessage(content=msg_config["content"])
                    )
        
        # 处理messages_2
        messages_2 = []
        for msg_config in topic_msg["messages_2"]:
            if msg_config["type"] == "human":
                messages_2.append(
                    HumanMessagePromptTemplate.from_template(msg_config["template"])
                )
            elif msg_config["type"] == "placeholder":
                messages_2.append(
                    MessagesPlaceholder(variable_name=msg_config["variable_name"])
                )
        
        print(f"[INFO] topic_msg: {messages_1}, {messages_2}")
        return messages_1, messages_2
    
    # 有的时候不太一样，还是得注意的
    def unique_parse(self, ai_message: AIMessage) -> AIMessage:
        """
        独特的解析方法
        :param qa_chain: 问答链
        :return: 处理后的问答链
        """
        return ai_message