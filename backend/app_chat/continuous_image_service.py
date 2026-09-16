"""连续图片认知无损理解兼容层。

Phase 7.3b 起，旧的 continuous_image_service.py 收口为薄转发层：
    - 真实实现位于 app_chat.ci 包
    - 保持既有导入路径兼容：from app_chat.continuous_image_service import ...
"""

from app_chat.ci import *  # noqa: F401,F403
from app_chat.ci import __all__ as __all__
