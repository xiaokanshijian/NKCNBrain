"""CI 离线单测使用的最小 Django 配置，不连接数据库或外部服务。"""
from pathlib import Path

from django.conf import settings


if not settings.configured:
    settings.configure(
        SECRET_KEY='synthetic-ci-test-key',
        DEFAULT_CHARSET='utf-8',
        ALLOWED_HOSTS=['testserver'],
        BASE_DIR=Path.cwd(),
    )
