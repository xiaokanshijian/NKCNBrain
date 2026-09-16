from app_chat.core.model_handler import ModelHandler
from app_chat.config.config_manager import config_manager


def singleton(cls):
    instances = {}
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance


@singleton
class ModelManager:
    """
    管理所有模型的处理器
    """
    
    # 根据config_manager.py中的配置，初始化模型处理器
    def __init__(self):
        self._model_handlers = {}        
        configs = config_manager.configs

        # 仅根据模型名称创建处理器

        for model_name, config in configs.items():
            # 仅创建处理器，不加载模型
            handler = ModelHandler(model_name=model_name)
            self._model_handlers[model_name] = handler

    def get_model_handler(self, model_name: str) -> ModelHandler:
        """获取指定模型的处理器"""
        return self._model_handlers.get(model_name, None)

    def get_model_handler_by_id(self, model_id: str) -> ModelHandler:
        """根据模型ID获取对应的处理器"""
        model_name = config_manager.get_model_name_by_id(model_id)
        print(f"[DEBUG] 根据模型ID获取处理器: {model_id} -> {model_name}")
        if model_name in self._model_handlers:
            return self._model_handlers[model_name]
        print(f"[ERROR] 根据模型ID '{model_id}' 找不到对应的处理器")
        return None
    
    # 返回所有的模型名称列表
    def get_all_model_names(self) -> list:
        """获取所有模型名称"""
        return list(self._model_handlers.keys())
    
    def get_model_handler_by_seq(self, sequence:int) -> ModelHandler:
        '''根据sequence获取handler'''
        model_name = config_manager.get_model_by_seq(sequence)
        if model_name in self._model_handlers:
            return self._model_handlers[model_name]
        return None
    
    # 新建模型处理器
    def create_model_handler(self, model_name: str) -> ModelHandler:
        """新建模型处理器，只要先把config_manager中的配置加载完毕，就可以直接根据模型名创建处理器"""
        print(f"[DEBUG] 正在创建模型处理器: {model_name}")
        if model_name not in self._model_handlers:
            handler = ModelHandler(model_name=model_name)
            self._model_handlers[model_name] = handler
            print(f"[INFO] 新建模型处理器: {model_name}")
            return handler
        return None
    
    def remove_model_handler(self, model_name: str) -> ModelHandler:
        """
        从模型管理器中删除指定模型的处理器

        Args:
            model_name: 要删除的模型名称

        Returns:
            ModelHandler: 如果成功删除，返回被删除的处理器对象；如果模型不存在，返回None
        """
        print(f"[DEBUG] 尝试删除模型处理器: {model_name}")

        if model_name in self._model_handlers:
            # 获取要删除的处理器对象
            handler = self._model_handlers[model_name]

            # 从字典中删除
            del self._model_handlers[model_name]

            print(f"[INFO] 成功删除模型处理器: {model_name}")
            return handler
        else:
            print(f"[WARNING] 尝试删除不存在的模型处理器: {model_name}")
            return None

    def update_model_handler(self, model_name: str, model_id: str) -> ModelHandler:
        """
        更新指定模型的处理器，使其使用最新的配置信息

        Args:
            model_name: 要更新的模型名称（旧）
            model_id: 模型的ID（唯一标志）

        Returns:
            ModelHandler: 如果成功更新，返回新创建的处理器对象；如果模型不存在，返回None
        """
        print(f"[DEBUG] 尝试更新模型处理器: {model_name}")

        # 检查模型是否存在于配置管理器中
        # if not config_manager.model_exists(model_name):
        #     print(f"[ERROR] 模型 '{model_name}' 在配置管理器中不存在，无法更新处理器")
        #     return None

        # 从配置中获取新的模型配置
        model_name_new = config_manager.get_model_name_by_id(model_id)

        # 移除旧的处理器（如果存在）
        if model_name in self._model_handlers:
            old_handler = self._model_handlers[model_name]
            del self._model_handlers[model_name]
            print(f"[DEBUG] 已移除旧的模型处理器: {model_name}")

        # 创建新的处理器
        try:
            handler = ModelHandler(model_name=model_name_new)
            self._model_handlers[model_name_new] = handler
            print(f"[INFO] 成功更新模型处理器: {model_name_new}")
            return handler
        except Exception as e:
            print(f"[ERROR] 更新模型处理器 '{model_name_new}' 时出错: {str(e)}")
            return None

    def has_model(self, model_name: str) -> bool:
        """
        检查指定的模型名称是否存在于模型管理器中

        Args:
            model_name: 要检查的模型名称

        Returns:
            bool: 如果模型存在返回True，否则返回False
        """
        return model_name in self._model_handlers


model_manager = ModelManager()
