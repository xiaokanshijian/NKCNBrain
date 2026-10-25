from django.apps import AppConfig
import sys

class AppChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "app_chat"

    def ready(self):
        # Management checks must not initialize LLM chains or background workers.
        if any(command in sys.argv for command in
               ("check", "migrate", "makemigrations", "collectstatic", "test")):
            return
        from llm_langchain import init
        init.init()
        from app_chat.chroma_unlock_scheduler import start_chroma_unlock_scheduler
        start_chroma_unlock_scheduler()
