from app_chat.conversation.conversation_manager import ConversationManager


class GlobalState:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GlobalState, cls).__new__(cls)
            cls._instance.init_state()
        return cls._instance

    def init_state(self):
        """初始化所有全局变量"""
        self.conversation_manager = ConversationManager()
        # username选择的主模型（用sequence表示），主模型除了问答之外，还有其它功能
        # 类型是int，表示模型的序号
        # self.user_main_model_sequence = {}
        
        self.docs = None
        self.vectors = None
        self.global_lock = {}

        
        self.chat_count = {}
        
        
        # 字典格式: {username: {model_name: content}}
        # 例如：{'test_user1': {'GPT4': ''}}
        # 相当于一个交流的缓冲区
        # 1. 消费者：
        #     1. stream_generator：判断是否存在content，并且逐步增添content
        #     2. rel_questions_request：将现有的回答，全部载入历史记录（虽然个人感觉这个函数的位置不太对，但现在先不管了）
        # 2. 生产者：
        #     1. chat_sendParams："此模型您已暂时关闭"的初值赋予
        self.chat_content = {} 
        
        
        self.chat_seed = {}
        self.chat_history = {}
        self.chat_history_used = {}
        self.params_count = {}
        self.speech_content = {}
        self.speech_history = {}
        self.auto_safe_count = {}
        
        self.last_question = {} # 保存用户的上一个问题
        self.last_segments = {} # 保存上一次文档分割的内容
        self.chat_with_files_params = {} # 用于存储带文档对话参数

        # 新增全局字典用于存储分段信息
        self.text_segments = {}  # 格式: {username: {'segments': [], 'current_index': 0}}

        # 用户选择的小模型ID字典 {username: model_id}
        self.user_little_model_id = {}  # 格式: {'username': '3003'}
        
        self.timeout = 40 # 超时时间限制
        
    # set_user_model
    # def set_user_model(self, user_name, model_num):
    #     self.user_main_model_sequence[user_name] = model_num


# 使用单例模式获取全局状态实例
GLOBAL_STATE = GlobalState()


# if __name__ == "__main__":
#     # 测试全局状态类
#     global_state = GlobalState()
#     print(type(GLOBAL_STATE.runtime_configs))  # 输出: <class 'list'>
#     print(global_state.runtime_configs)  # 输出: [{'modelID': '1002', 'config': {...}}, ...]
