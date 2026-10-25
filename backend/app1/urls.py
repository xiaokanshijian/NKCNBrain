from django.urls import path, re_path

from app1 import views, session_views

urlpatterns = [
    # path('admin/', admin.site.urls),
    # 访问xxx/login，执行此函数
    # path('login/', views.login),
    re_path('add_user$', views.add_user),
    re_path('show_users/', views.show_users),
    re_path(r'^verify_user/?$', views.verify_user),
    path('auth/csrf', session_views.csrf_token),
    path('auth/session', session_views.current_session),
    path('auth/logout', session_views.logout_session),
    re_path('ban_user/', views.ban_user),
    re_path('open_user/', views.open_user),
    re_path('user_exit/', views.user_exit),
    re_path('get_onlineNum/', views.get_onlineNum),
    re_path('get_userChosen/', views.get_userChosen),
    re_path('get_userUpDownLevelInfo/', views.get_userUpDownLevelInfo),
    re_path('get_system_choice/', views.get_system_choice),
    re_path('set_system_choice/', views.set_system_choice),
]