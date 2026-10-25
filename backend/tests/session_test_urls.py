"""Use the actual account views, omitting unrelated LLM imports only."""
import importlib
import sys
import types
from unittest.mock import patch
from django.urls import include, path

chat_stub = types.ModuleType("app_chat.views")
chat_stub.global_lock = {}
parse_stub = types.ModuleType("llm_langchain.parse_input")
with patch.dict(sys.modules, {"app_chat.views": chat_stub, "llm_langchain.parse_input": parse_stub}):
    account_urls = importlib.import_module("app1.urls")

from app_chat.voice_session import voice_session
urlpatterns = [
    path("api/", include(account_urls)),
    path("api/voice/session", voice_session),
]
