from threading import RLock

from django.shortcuts import render, HttpResponse, redirect
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.cache import never_cache
from django.utils.crypto import constant_time_compare
from app1.session_auth import clear_user_session, establish_user_session

from app_chat.views import global_lock
# from app_chat.global_state import GLOBAL_STATE

# Create your views here.
# def login(request):
#     return HttpResponse("欢迎使用")

from app1.models import User
from app1.models import UserSceneParams
from zym.models import scene
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.core import serializers
import json
from zym.models import UserNotebook
from llm_langchain import parse_input

# 全局在线用户列表
online_users = []


@require_http_methods(["GET"])
def add_user(request):
    response = {}

    # 检查level关系，超级组织电脑S级、T级、TA级、组长GL级和组员GM级，共五级
    level_hierarchy = {
        'GM': 'GL',  # GM的上级是GL
        'GL': 'TA',  # GL的上级是TA
        'TA': 'T',  # TA的上级是T
        'T': 'S',  # T的上级是S
        'S': None  # S是最高级，没有上级
    }

    # 检查用户名是否已存在
    if User.objects.filter(username=request.GET.get('username')).exists():
        response['msg'] = 'Username already exists'
        response['error_num'] = 1
    else:
        if User.objects.filter(username=request.GET.get('coacher')).exists():
            # 检查用户的level是否是coacher的下一级
            user_level = request.GET.get('level')
            coacher = User.objects.get(username=request.GET.get('coacher'))
            if coacher.level == 'GM' or level_hierarchy.get(user_level) != coacher.level:
                # GM不能作为coacher，且用户的等级上级必须是coacher的等级
                response['msg'] = '您填写的组织关系或领航员有误'
                response['error_num'] = 1
            else:
                try:
                    # 如果用户名不存在，创建新用户
                    user = User(username=request.GET.get('username'), password=request.GET.get('password'),
                                coacher=request.GET.get('coacher'), level=request.GET.get('level'))
                    user.save()
                    response['msg'] = 'success'
                    response['error_num'] = 0
                except Exception as e:
                    # 如果保存用户时发生异常，记录错误信息
                    response['msg'] = str(e)
                    response['error_num'] = 1
        else:
            response['msg'] = 'coacher用户名不存在'
            response['error_num'] = 1

    return JsonResponse(response)


@require_http_methods(["GET"])
def show_users(request):
    response = {}
    try:
        users = User.objects.filter()
        response['list'] = json.loads(serializers.serialize("json", users))
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1

    return JsonResponse(response)


@never_cache
@require_http_methods(["POST"])
@csrf_protect
def verify_user(request):
    response = {}
    # A failed login/account switch must not retain an earlier signed-in identity.
    clear_user_session(request)
    try:
        data = json.loads(request.body) if request.content_type == 'application/json' else request.POST
        username = data.get('username')
        password = data.get('password')
        choose = data.get('choose')
        if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
            return JsonResponse({'msg': 'Invalid password', 'error_num': 0, 'name': '0'})

        # 在这里添加用户验证逻辑，例如检查数据库中是否存在该用户，并验证密码
        # 这里假设有一个名为 User 的模型来表示用户
        # user = User.objects.get(username=username)
        user = User.objects.get(username__exact=username)

        # 检查精确匹配
        matching_user = None
        if user.username == username:  # 精确匹配，区分大小写
            matching_user = user
        if not matching_user:
            raise User.DoesNotExist

        if constant_time_compare(user.password, password) and (user.allowed == 1):
            # 登录成功
            # parse_input.load_user(username)
            # global_lock[username] = RLock()
            if choose == "full":
                user.choose = 0
            elif choose == "simple":
                user.choose = 1
            elif choose == "minimal":
                user.choose = 2
            else:   # unicast
                user.choose = 3
            user.save()

            # 查询所有scene对象的sid
            sids = scene.objects.all().values_list('sid', flat=True)
            usernames = User.objects.all().values_list('username', flat=True)
            uspsids = UserSceneParams.objects.all().values_list('sid', flat=True)
            uspusernames = UserSceneParams.objects.all().values_list('username', flat=True)
            # 设置默认的usparams
            params = {
                "GPT4": {
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "frequency_penalty": 1.0,
                    "presence_penalty": 1.0,
                    "max_tokens": 1024,
                    "n": 1
                },
                "Mixtral": {
                    "temperature": 1.0,
                    "top_p": 0.95,
                    "top_k": 30,
                    "max_length": 1024,
                    "do_sample": 1,
                    "num_beams": 2,
                    "num_beam_groups": 2,
                    "num_return_sequences": 1,
                    "repetition_penalty": 1.5,
                    "max_new_tokens": 1024,
                    "diversity_penalty": 1.1,
                    "length_penalty": 0.5
                },
                "Kimi": {
                    "temperature": 0.5,
                    "top_p": 0.95,
                    "frequency_penalty": 1.0,
                    "presence_penalty": 0.7,
                    "max_tokens": 1024,
                    "n": 1
                },
                "llama3": {
                    "temperature": 0.5,
                    "top_p": 0.95,
                    "frequency_penalty": 0.8,
                    "presence_penalty": 0.8,
                    "max_tokens": 1024
                },
                "Claude": {
                    "temperature": 0.5,
                    "top_p": 0.95,
                    "top_k": 30,
                    "max_tokens": 1024
                },
                "deepseek": {
                    "temperature": 0.5,
                    "top_p": 0.95,
                    "frequency_penalty": 0.8,
                    "presence_penalty": 0.8,
                    "max_tokens": 1024
                }
            }
            # 为每个sid创建UserSceneParams实例
            # for sid in sids:
            #     UserSceneParams.objects.create(
            #         username=request.GET.get('username'),
            #         sid=sid,
            #         usparams=params
            #     )
            # 找出不存在的usernames
            missing_usernames = usernames.exclude(username__in=set(uspusernames))
            missing_sids = sids.exclude(sid__in=set(uspsids))
            print(missing_usernames)
            for missing_username in missing_usernames:
                for sid in sids:
                    UserSceneParams.objects.create(
                        username=missing_username,
                        sid=sid,
                        usparams=params
                    )
            for missing_sid in missing_sids:
                for usernamesingle in usernames:
                    UserSceneParams.objects.create(
                        username=usernamesingle,
                        sid=missing_sid,
                        usparams=params
                    )

            establish_user_session(request, user)
            response['msg'] = 'success'
            response['error_num'] = 0
            response['name'] = username
            response['coacherName'] = user.coacher
            response['level'] = user.level
        else:
            response['msg'] = 'Invalid password'
            response['error_num'] = 0
            response['name'] = '0'
    except User.DoesNotExist:
        response['msg'] = 'User does not exist'
        response['error_num'] = 0
        response['name'] = '0'
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
        response['name'] = '0'

    return JsonResponse(response)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def ban_user(request):
    data = json.loads(request.body)
    username = data["username"]
    try:
        User.objects.filter(username=username).update(allowed=0)

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except scene.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=404)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def open_user(request):
    data = json.loads(request.body)
    username = data["username"]
    try:
        User.objects.filter(username=username).update(allowed=1)

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except scene.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=404)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def user_exit(request):
    data = json.loads(request.body)
    username = data["username"]
    try:
        print(username + ":------------------------------------- \n")
        print(online_users)
        if username in online_users:
            online_users.remove(username)
        print(online_users)

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=404)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def get_onlineNum(request):
    data = json.loads(request.body)
    username = data["username"]
    print(username)
    onlineNum = len(online_users)

    online_user_username = []
    online_user_bookName = []

    for element in online_users:
        parts = element.split('_')
        for i in range(1, len(parts)):
            username = '_'.join(parts[:i])
            book_name = '_'.join(parts[i:])
            try:
                user_notebook = UserNotebook.objects.get(username=username, bookName=book_name)
                online_user_username.append(username)
                online_user_bookName.append(book_name)
                break
            except UserNotebook.DoesNotExist:
                continue

    return JsonResponse({
        'onlineNum': onlineNum,
        'onlineUsername': online_user_username,
        'onlineUserBookName': online_user_bookName,
        'status': 'success',
        'error_num': 0,
    }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def get_userChosen(request):
    data = json.loads(request.body)
    username = data["username"]
    print(username)

    try:
        user = User.objects.get(username=username)
        choose = user.choose
    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'message': '用户不存在'
        }, status=201)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error_num': 2,
            'message': str(e)
        }, status=201)

    return JsonResponse({
        'choose': choose,
        'status': 'success',
        'error_num': 0,
    }, status=201)


@csrf_exempt  # 仅在开发时使用，生产环境应该去掉
def get_userUpDownLevelInfo(request):
    data = json.loads(request.body)
    username = data["username"]
    print(username)

    try:
        user = User.objects.get(username=username)
        coacher = user.coacher
        level = user.level
    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'message': '用户不存在'
        }, status=201)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error_num': 2,
            'message': str(e)
        }, status=201)

    return JsonResponse({
        'coacher': coacher,
        'level': level,
        'status': 'success',
        'error_num': 0,
    }, status=201)


@csrf_exempt
def get_system_choice(request):
    """获取用户的system选择（0=system2慢思考，1=system1快思考）"""
    try:
        data = json.loads(request.body)
        username = data.get('username')

        user = User.objects.get(username=username)
        return JsonResponse({
            'error_num': 0,
            'choose': user.system_mode,  # 🔥 使用system_mode字段
            'msg': 'success'
        })
    except User.DoesNotExist:
        return JsonResponse({
            'error_num': 1,
            'msg': '用户不存在'
        })
    except Exception as e:
        return JsonResponse({
            'error_num': 1,
            'msg': str(e)
        })


@csrf_exempt
def set_system_choice(request):
    """设置用户的system选择（0=system2慢思考，1=system1快思考）"""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        choose = data.get('choose', 0)

        user = User.objects.get(username=username)
        user.system_mode = choose  # 🔥 使用system_mode字段
        user.save()

        return JsonResponse({
            'error_num': 0,
            'choose': user.system_mode,  # 🔥 使用system_mode字段
            'msg': 'success'
        })
    except User.DoesNotExist:
        return JsonResponse({
            'error_num': 1,
            'msg': '用户不存在'
        })
    except Exception as e:
        return JsonResponse({
            'error_num': 1,
            'msg': str(e)
        })
