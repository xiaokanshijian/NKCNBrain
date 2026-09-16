from django.apps import AppConfig
import llm_langchain.normal_qa as normal_qa
import llm_langchain.init as init

class AppChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_chat'

    def ready(self):
        #在这里初始化服务
        init.init()
        print('init ready')

        # 启动Chroma解锁调度器
        try:
            from app_chat.chroma_unlock_scheduler import start_chroma_unlock_scheduler
            start_chroma_unlock_scheduler()
            print('Chroma解锁调度器已启动')
        except Exception as e:
            print(f'启动Chroma解锁调度器失败: {e}')