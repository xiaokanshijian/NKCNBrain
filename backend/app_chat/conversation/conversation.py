class Conversation:
    '''
    用于管理完整的prompt，一个完整的prompt，包括如下内容：
        1. 当前用户的Question，作为外部参数传入
        2. 上下文的历史问题和回复，传入后需要保留
        3. LUI的场景prompt
        4. file_list，表示用户当前勾选的文件列表
        5. 其它部分
    '''
    
    def __init__(self, username: str, model_name: str) -> None:
        """
        初始化对话历史
        :param username: 用户名
        :param model_name: 模型名
        """
        self.username = username
        self.model_name = model_name
        self.max_round = 4  # 静态设置为最多保存10轮历史记录
        self.questions = []  # 存储历史问题列表
        self.responses = []  # 存储模型的历史回复列表
        self.file_list = []  # 存储用户当前勾选的文件列表
    
    def get_question_history(self, rounds: int) -> list:
        """
        获取指定轮数的历史问题
        :param rounds: 要获取的历史记录轮数
        :return: 历史问题列表
        """
        if rounds <= 0:
            return []
        return self.questions[-rounds:]  # 返回指定轮数的问题
    
    def get_response_history(self, rounds: int) -> list:
        """
        获取指定轮数的历史回复
        :param rounds: 要获取的历史记录轮数
        :return: 历史回复列表
        """
        if rounds <= 0:
            return []
        return self.responses[-rounds:]  # 返回指定轮数的回复
    
    def add_question(self, question: str) -> None:
        """新增历史对话记录，最多保存10轮"""
        if not question:
            return
            
        self.questions.append(question)
        if len(self.questions) > self.max_round:
            self.questions.pop(0)  # 保持最多10轮
    
    def add_response(self, response: str) -> None:
        """新增历史回复记录，最多保存10轮"""
        if not response:
            return
            
        self.responses.append(response)
        if len(self.responses) > self.max_round:
            self.responses.pop(0)  # 保持最多10轮
            
    def get_response_length(self) -> int:
        """获取历史回复数量"""
        return len(self.responses)
    
    def get_latest_response(self) -> str:
        """获取最新的回复"""
        return self.responses[-1] if self.responses else None
    
    def add_file_list(self, file_list: list) -> None:
        """更新文件列表"""
        self.file_list = file_list.copy() if file_list else []