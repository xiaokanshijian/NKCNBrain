from app_chat.conversation.conversation import Conversation


class ConversationManager:
    def __init__(self):
        '''
        使用字典存储所有对话
        key: (username, model_name)
        value: Conversation对象
        '''
        
        self._conversations = {}  
    
    def is_empty(self) -> bool:
        """检查对话管理器是否为空"""
        return len(self._conversations) == 0
    
    def get_conversation(self, username: str, model_name: str) -> 'Conversation':
        """
        获取或创建对话对象
        如果不存在，则创建一个新的Conversation对象并返回
        如果存在，则返回已有的Conversation对象
        """
        key = (username, model_name)
        if key not in self._conversations:
            self._conversations[key] = Conversation(username, model_name)
        return self._conversations[key]
    
    def remove_conversation(self, username: str, model_name: str) -> None:
        """移除特定对话"""
        key = (username, model_name)
        if key in self._conversations:
            del self._conversations[key]
            
    def get_conversations_by_model(self, model_name: str) -> list:
        """获取所有指定模型的对话对象"""
        return [conv for conv in self._conversations.values() if conv.model_name == model_name]
    
    def get_response_list(self, username: str, model_name: str, rounds: int = None) -> list:
        """
        获取指定用户和模型的响应列表
        :param username: 用户名
        :param model_name: 模型名
        :param rounds: 要获取的历史记录轮数，None表示获取全部
        :return: 响应列表
        """
        key = (username, model_name)
        print(f"[DEBUG:get_response_list] 获取响应列表: {key}, rounds={rounds}")
        if key in self._conversations:
            if rounds is None:
                return self._conversations[key].responses
            return self._conversations[key].get_response_history(rounds)
        return []
    
    def get_question_list(self, username: str, model_name: str, rounds: int = None) -> list:
        """
        获取指定用户和模型的提问列表
        :param username: 用户名
        :param model_name: 模型名
        :param rounds: 要获取的历史记录轮数，None表示获取全部
        :return: 提问列表
        """
        key = (username, model_name)
        print(f"[DEBUG:get_question_list] 获取问题列表: {key}, rounds={rounds}")
        if key in self._conversations:
            if rounds is None:
                return self._conversations[key].questions
            return self._conversations[key].get_question_history(rounds)
        return []
    
    # 返回（username, model_name）的最新回复
    def get_latest_response(self, username: str, model_name: str) -> str:
        """获取指定用户和模型的最新回复"""
        key = (username, model_name)
        if key in self._conversations:
            return self._conversations[key].get_latest_response()
        return None
    
    def add_interaction(self, username: str, model_name: str, question: str, response: str) -> None:
        """
        新增历史问题和回复记录，确保不超过最大轮数，如果超过则删除最早的记录
        """
        key = (username, model_name)
        if key in self._conversations:
            self._conversations[key].add_question(question)
            self._conversations[key].add_response(response)
            print(f"[INFO] 新增历史记录: {key} - {question} -> {response}")
        else:
            print(f"[INFO] 新增历史记录时，对话管理器中没有找到对应的对话: {key}")
            
    def update_file_list(self, username: str, model_name: str, file_list: list) -> None:
        """更新指定用户和模型的文件列表"""
        key = (username, model_name)
        if key in self._conversations:
            self._conversations[key].file_list = file_list
        else:
            print(f"[INFO] 更新文件列表时，对话管理器中没有找到对应的对话: {key}")
        
    def get_conversations_by_username(self, username: str) -> dict:
        '''
        根据username，生成一个以model_name为key的字典，value是如下字典：
            'filelist': Conversation.file_list,
            'message': Conversation.questions,
            'AImessage': Conversation.responses,
        '''
        conversations = {}
        for (user, model_name), conversation in self._conversations.items():
            if user == username:
                conversations[model_name] = {
                    'filelist': conversation.file_list,
                    'message': conversation.questions,
                    'AImessage': conversation.responses,
                }
        return conversations

    def update_latest_response(self, username: str, model_name: str, new_response: str) -> bool:
        """
        更新指定用户和模型的最新回复（用于重做功能）
        :param username: 用户名
        :param model_name: 模型名
        :param new_response: 新的回复内容
        :return: 是否更新成功
        """
        key = (username, model_name)
        if key in self._conversations:
            conversation = self._conversations[key]
            if conversation.responses:  # 确保有回复记录
                conversation.responses[-1] = new_response  # 更新最后一个回复
                print(f"[INFO] 成功更新历史记录: {key} - 最新回复已更新")
                return True
            else:
                print(f"[WARNING] 对话中没有回复记录: {key}")
                return False
        else:
            print(f"[WARNING] 对话管理器中未找到对话: {key}")
            return False

    def update_response_by_question(self, username: str, model_name: str, question: str, new_response: str) -> bool:
        """
        根据问题内容更新对应的回复（用于重做功能）
        :param username: 用户名
        :param model_name: 模型名
        :param question: 问题内容
        :param new_response: 新的回复内容
        :return: 是否更新成功
        """
        key = (username, model_name)
        if key in self._conversations:
            conversation = self._conversations[key]

            # 查找匹配的问题
            for i, q in enumerate(conversation.questions):
                if q == question and i < len(conversation.responses):
                    conversation.responses[i] = new_response
                    print(f"[INFO] 成功更新历史记录: {key} - 问题'{question[:50]}...'的回复已更新")
                    return True

            print(f"[WARNING] 未找到匹配的问题: {key} - '{question[:50]}...'")
            return False
        else:
            print(f"[WARNING] 对话管理器中未找到对话: {key}")
            return False