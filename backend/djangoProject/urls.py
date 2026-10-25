"""
URL configuration for djangoProject project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, re_path, include
from django.contrib import admin
from app1 import urls as app1_urls
from app_chat import urls as chat_urls
from zym import urls as zym_urls
# from app_seed import urls as seed_urls
from django.views.generic.base import TemplateView

from app1 import views

from app_chat.voice_session import voice_session

urlpatterns = [
    path('api/voice/session', voice_session),
    # path('admin/', admin.site.urls),
    # 访问xxx/login，执行此函数
    # path('login/', views.login),
    re_path('admin/', admin.site.urls),
    re_path('api/', include(app1_urls)),
    re_path('api/', include(chat_urls)),
    re_path('api/',include(zym_urls)),
    # re_path('api/', include(seed_urls)),
    # 修改入口urls文件为前端
    # re_path(r'^$', TemplateView.as_view(template_name='index.html')),
]
