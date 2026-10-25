import uuid

from django.shortcuts import render, HttpResponse, redirect

# Create your views here.
# def login(request):
#     return HttpResponse("欢迎使用")
from app1.models import User, UserSceneParams
from zym.models import UserNotebook, scene
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from django.core import serializers
from django.db.models import Q
from django.db.models import Max

import json
import base64
import os
import re
import random
import time
from llm_langchain import get_crad_text
from app_chat.models import Card

from llm_langchain import parse_input, normal_qa, get_suma, get_rel_que, global_var, red_bule_rate
from llm_langchain.parse_input import *
from llm_langchain import init
from django.views.decorators.csrf import csrf_exempt
from llm_langchain import util
from llm_langchain.red_bule_rate import extract_number_SFT, extract_color_SFT, extract_reason_SFT, extract_number, extract_color, extract_reason
from zym import util, React
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404
from app_chat.views import global_lock, chat_count, chat_history, chat_history_used, speech_history, auto_safe_count, chat_content
# from app_chat.global_state import GLOBAL_STATE
import shutil
from app_chat.utils import read_xlsx_to_binary, read_prompt_from_file, read_prompt_from_bytes, prompt_to_ghp, resolve_prompt_storage_key
import pandas as pd
import openpyxl
from app_chat import gpt4_api, kimi_api
from app1.views import online_users
import tempfile
import threading

scene_lock = {}

_PROGRESS_DIR = os.path.join(tempfile.gettempdir(), 'nkcn_load_progress')
_progress_file_lock = threading.Lock()


class _ProgressRow(dict):
    """原地改进度时同时写到临时文件，避免 Django 热重载双进程各记一份内存。"""

    def __init__(self, owner, pid, data):
        super().__init__(data)
        self._owner = owner
        self._pid = pid

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        self._owner.flush(self._pid, dict(self))

    def update(self, *args, **kwargs):
        super().update(*args, **kwargs)
        self._owner.flush(self._pid, dict(self))


class ProgressStore:
    def __init__(self):
        self._mem = {}
        try:
            os.makedirs(_PROGRESS_DIR, exist_ok=True)
        except OSError:
            pass

    def _path(self, pid):
        text = str(pid or '')
        if not re.match(r'^[a-zA-Z0-9-]{8,80}$', text):
            raise KeyError(pid)
        return os.path.join(_PROGRESS_DIR, text + '.json')

    def flush(self, pid, data):
        try:
            path = self._path(pid)
            tmp = path + '.tmp'
            with _progress_file_lock:
                with open(tmp, 'w', encoding='utf-8') as handle:
                    json.dump(data, handle, ensure_ascii=False)
                os.replace(tmp, path)
        except (OSError, KeyError):
            pass

    def _read_file(self, pid):
        try:
            with open(self._path(pid), 'r', encoding='utf-8') as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except (OSError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def __contains__(self, pid):
        if pid in self._mem:
            return True
        try:
            return os.path.isfile(self._path(pid))
        except KeyError:
            return False

    def __getitem__(self, pid):
        row = self._mem.get(pid)
        if row is not None:
            disk = self._read_file(pid)
            if disk and (disk.get('progress', 0) > row.get('progress', 0) or disk.get('status') != row.get('status')):
                row.clear()
                row.update(disk)
            return row
        data = self._read_file(pid)
        if data is None:
            raise KeyError(pid)
        row = _ProgressRow(self, pid, data)
        self._mem[pid] = row
        return row

    def __setitem__(self, pid, value):
        data = dict(value or {})
        row = _ProgressRow(self, pid, data)
        self._mem[pid] = row
        self.flush(pid, data)

    def ensure(self, pid, **fields):
        if pid not in self:
            payload = {'status': 'started', 'progress': 0, 'message': '准备加载用户数据...'}
            payload.update(fields)
            self[pid] = payload
            return self[pid]
        row = self[pid]
        for key, value in fields.items():
            row[key] = value
        return row


progress_data = ProgressStore()

# RANDOM_USER_NAME = 'gkjbkjbubuobklnbuibuyfyudsaihefowiilcnsiancioxzdozwqeflzddsfgvb'
RANDOM_USER_NAME = 'gkjbkjbubuobklnb'


# @require_http_methods(["GET"])
# def addBook(request):
#     response = {}
#     try:
#         notebook = UserNotebook(
#             username=request.GET.get('username'),
#             bookId=request.GET.get('id'),
#             bookName=request.GET.get('bookName'),
#             bookdescription=request.GET.get('description'),
#             sid=request.GET.get('sid')
#         )
#         notebook.save()
#
#         uname = request.GET.get('username') + '_' + request.GET.get('bookName')
#         directory = "./received_dir/user_raw_file/" + request.GET.get('username') + '_' + request.GET.get('bookName')
#         if not os.path.exists(directory):
#             os.makedirs(directory)
#
#         sceneName = request.GET.get('sname')
#         sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
#         entries = os.listdir(sceneDirPath)
#         # 使用 os.path.isdir() 检查每个条目是否为目录
#         subSceneNameList = [entry for entry in entries if os.path.isdir(os.path.join(sceneDirPath, entry))]
#
#         if not os.path.exists(directory):
#             os.makedirs(directory)
#
#         parse_input.load_user(uname)
#         global_lock[uname] = RLock()
#         chat_history[uname] = []
#         chat_count[uname] = 0
#
#
#         secenExcelPath = './received_dir/' + 'scene_excel/' + sceneName + '/prompt.xlsx'
#         finalExcelPath = './received_dir/' + 'scene_excel/' + sceneName+ '/'+subSceneNameList[0]+'/prompt.xlsx'
#         secenExcelPath = finalExcelPath
#         print(secenExcelPath)
#
#
#         if os.path.exists(secenExcelPath):
#             res = read_prompt_from_file(secenExcelPath)
#             # res = read_prompt_from_bytes(binary_data)
#             print(res)
#             res2 = prompt_to_ghp(res)
#             print(res2)
#             parse_input.set_user_prompt(user_name=uname, prompt=res2[0])
#             parse_input.set_user_params(user_name=uname, params=res2[1])
#
#         secenDirPath = './received_dir/' + 'scene_excel/' + sceneName
#         # bookList=[]
#         if os.path.exists(secenDirPath):
#             filesList = []
#             files_and_dirs = os.listdir(secenDirPath)
#             for file in files_and_dirs:
#                 if os.path.isfile(os.path.join(secenDirPath, file)):
#                     if file.endswith(".xlsx"):
#                         continue
#                     filesList.append(file)
#                     # filesList = [file for file in files_and_dirs if os.path.isfile(os.path.join(secenDirPath, file))]
#
#             for file in filesList:
#                 tar_path = directory + '/' + file
#                 src_path = secenDirPath + '/' + file
#                 shutil.copy(src_path, tar_path)
#                 parse_input.get_split_docs_vectors(request.GET.get('username') + '_' + request.GET.get('bookName'), file)
#
#         response['msg'] = 'success'
#         response['error_num'] = 0
#     except Exception as e:
#         print(e)
#         response['msg'] = str(e)
#         response['error_num'] = 1
#
#     return JsonResponse(response)


@require_http_methods(["GET"])
def addBook(request):
    username = request.GET.get('username')
    sceneName = request.GET.get('sname')
    bookName = request.GET.get('bookName')
    newName = username + '_' + bookName

    response = {}

    # 用户本子（demo/普通）名不能有重复（所有场景下），避免文件夹存的内容重叠，不仅不能与用户已有的
    # 本子重复，还要考虑到用户之后可能加载其他场景demo，也不能与已有的random_demo有重复
    # 存储所有已存在的本子名称（统一转换为小写）
    book_names_set = set()

    # 获取用户已有的本子名称（转换为小写）
    userBookItems = UserNotebook.objects.filter(username=username)
    if userBookItems.exists():
        for userBookItem in userBookItems:
            book_names_set.add(userBookItem.bookName.lower())

    # 获取系统demo本子名称（转换为小写）
    demoBookItems = UserNotebook.objects.filter(username=RANDOM_USER_NAME)
    if demoBookItems.exists():
        for demoBookItem in demoBookItems:
            book_names_set.add(demoBookItem.bookName.lower())

    # 检查当前bookName是否已存在（不可以重复，也不可以只改大小写）
    if bookName.lower() in book_names_set:
        response['msg'] = 'repeat'
        response['error_num'] = 2
        return JsonResponse(response)

    try:
        notebook = UserNotebook(
            username=username,
            bookId=request.GET.get('id'),
            bookName=request.GET.get('bookName'),
            bookdescription=request.GET.get('description'),
            sid=request.GET.get('sid'),
            writer=username
        )
        notebook.save()

        sceneName = request.GET.get('sname')
        sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
        entries = os.listdir(sceneDirPath)
        # 使用 os.path.isdir() 检查每个条目是否为目录
        subSceneNameList = [
            entry for entry in entries
            if os.path.isdir(os.path.join(sceneDirPath, entry))
               and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
        sheetName = 'LUI1'
        secenExcelPath = './received_dir/' + 'scene_excel/' + sceneName + '/prompt.xlsx'
        data = pd.read_excel(secenExcelPath, sheet_name=sheetName)
        subSceneCol = 1
        firstSubSceneColName = data.columns[subSceneCol]
        subSceneNameListOrder = data.iloc[:, 1].dropna().tolist()
        subSceneNameListOrder.insert(0, firstSubSceneColName)
        if len(subSceneNameListOrder) == len(subSceneNameList):
            subSceneNameList = subSceneNameListOrder
            print("cnmcnm--------------------------------")
            print(subSceneNameList)

        finalExcelPath = './received_dir/' + 'scene_excel/' + \
                         sceneName + '/' + subSceneNameList[0] + '/prompt.xlsx'
        secenExcelPath = finalExcelPath

        parse_input.split_scene_to_user(
            scene_name=sceneName, user_name=newName)
        parse_input.load_user(newName)
        if os.path.exists(secenExcelPath):
            res = read_prompt_from_file(secenExcelPath)
            res2 = prompt_to_ghp(res)
            parse_input.set_user_prompt(user_name=newName, prompt=res2[0])
            parse_input.set_user_params(user_name=newName, params=res2[1])
        global_lock[newName] = RLock()
        chat_history[newName] = []
        chat_history_used[newName] = []
        speech_history[newName] = ""
        chat_count[newName] = 0
        auto_safe_count[newName] = 0

        response['subSceneList'] = subSceneNameList
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        print(e)
        response['subSceneList'] = []
        response['msg'] = str(e)
        response['error_num'] = 1

    return JsonResponse(response)


@require_http_methods(["GET"])
def uploadDemoNotebook(request):
    # 数据库存了'0'的笔记本，点击发布，更新为1，同时把笔记本的文件和卡片都存起来
    # 1.笔记本文件夹位于scene_excel 2.笔记本数据库记录不变(已经插入)，只需要修改为1 3.卡片记录不变，查询方式更改即可
    username = request.GET.get('username')
    bookName = request.GET.get('bookName')
    sceneId = request.GET.get('sid')
    sceneName = request.GET.get('sname')
    newName = username + '_' + bookName
    print('[zym views]:' + username + '分享了demo book:' + bookName)

    response = {}
    try:
        oldDirPath = './received_dir/' + 'user_raw_file/' + username + '_' + bookName
        sceneDirPath = './received_dir/' + 'scene_excel/' + \
                       sceneName + '/' + RANDOM_USER_NAME
        newDirPath = './received_dir/' + 'user_raw_file/' + \
                     RANDOM_USER_NAME + '_' + bookName
        if not os.path.exists(oldDirPath):
            os.makedirs(oldDirPath)
        if not os.path.exists(sceneDirPath):
            os.makedirs(sceneDirPath)
        if not os.path.exists(newDirPath):
            os.makedirs(newDirPath)
        for file in os.listdir(oldDirPath):
            print(file)
            tar_path = sceneDirPath + '/' + file
            src_path = oldDirPath + '/' + file
            if not os.path.isdir(src_path):
                shutil.copy(src_path, tar_path)
            else:
                tar_dir = tar_path
                if os.path.exists(tar_dir):
                    shutil.rmtree(tar_dir)
                shutil.copytree(src_path, tar_dir)
        for file in os.listdir(oldDirPath):
            print(file)
            tar_path = newDirPath + '/' + file
            src_path = oldDirPath + '/' + file
            if not os.path.isdir(src_path):
                shutil.copy(src_path, tar_path)
            else:
                tar_dir = tar_path
                if os.path.exists(tar_dir):
                    shutil.rmtree(tar_dir)
                shutil.copytree(src_path, tar_dir)

        # 这里发布时username变为虚拟用户了，但writer没变，正好符合需求！本子和卡片都是
        UserNotebook.objects.filter(username=username).filter(
            bookName=bookName).filter(sid=sceneId).update(username=RANDOM_USER_NAME)
        Card.objects.filter(
            username=username + '_' + bookName).update(username=RANDOM_USER_NAME + '_' + bookName)

        print(sceneId)
        scene.objects.filter(sid=sceneId).update(username='1')
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        print(e)
        response['msg'] = str(e)
        response['error_num'] = 1

    return JsonResponse(response)


@require_http_methods(["GET"])
def addScene(request):
    response = {}
    try:
        username = request.GET.get('username')
        description = request.GET.get('description')

        if scene.objects.filter(sceneDescription=description).exists():
            response['msg'] = 'success'
            response['error_num'] = 2  # 表示数据重复了
        else:
            s = scene(
                username='0',
                sceneDescription=description,
                uploader=username,
            )
            s.save()
            scene_item = scene.objects.get(sceneDescription=description)
            sid = scene_item.sid
            usernames = User.objects.all().values_list('username', flat=True)
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
                }
            }
            # 为每个sid创建UserSceneParams实例
            # for sid in sids:
            #     UserSceneParams.objects.create(
            #         username=request.GET.get('username'),
            #         sid=sid,
            #         usparams=params
            #     )
            for usernamesingle in usernames:
                UserSceneParams.objects.create(
                    username=usernamesingle,
                    sid=sid,
                    usparams=params
                )

            response['msg'] = 'success'
            response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1

    return JsonResponse(response)


# 后端 views.py 中添加新的接口
@csrf_exempt
def get_same_level_users(request):
    """获取与当前用户相同层级的用户列表 (作者！)"""
    data = json.loads(request.body)
    try:
        current_username = data['username']
        sync_users_str = data['syncUsers']

        if not current_username or not sync_users_str:
            return JsonResponse({
                'error_num': 1,
                'msg': '参数不完整'
            })

        # 获取用户（作者）的层级和coacher
        try:
            current_user = User.objects.get(username=current_username)
            current_level = current_user.level
            user_coacher = current_user.coacher
        except User.DoesNotExist:
            return JsonResponse({
                'error_num': 1,
                'msg': '用户不存在'
            })

        # 解析syncUsers字符串
        sync_users_list = [user.strip() for user in sync_users_str.split(',') if user.strip()]

        # 查找相同层级的用户
        same_level_users = []
        for username in sync_users_list:
            try:
                user = User.objects.get(username=username)
                if user.level == current_level:
                    same_level_users.append(username)
            except User.DoesNotExist:
                # 如果用户不存在，跳过
                continue

        return JsonResponse({
            'error_num': 0,
            'msg': '获取成功',
            'same_level_users': same_level_users,
            'current_level': current_level,
            'user_coacher': user_coacher
        })

    except Exception as e:
        return JsonResponse({
            'error_num': 1,
            'msg': f'服务器错误: {str(e)}'
        })


# 添加新的接口来查询进度
@require_http_methods(["GET"])
def check_load_progress(request):
    progress_id = request.GET.get('progress_id')
    if progress_id in progress_data:
        print(f"[check_load_progress]: 文件数和进度{progress_data[progress_id]['message']}{progress_data[progress_id]['progress']}")
        return JsonResponse(progress_data[progress_id])
    else:
        return JsonResponse({
            'status': 'not_found',
            'progress': 0,
            'message': '找不到进度信息'
        })


@require_http_methods(["GET"])
def makeAndGetProgressId(request):
    response = {}
    # 创建一个进度跟踪 ID
    progress_id = str(uuid.uuid4())

    # 初始化进度信息
    progress_data[progress_id] = {
        'status': 'started',
        'progress': 0,
        'message': '准备加载用户数据...'
    }
    response['progress_id'] = progress_id
    return JsonResponse(response)


# FIXME
@require_http_methods(["GET"])
def loadUser(request):
    response = {}
    try:
        originRealName = request.GET.get('originRealName')
        username = request.GET.get('username')
        sceneName = request.GET.get('sceneName')
        progress_id = request.GET.get('progressId')
        if progress_id and progress_id in progress_data:
            progress_data[progress_id]['progress'] = 4
            progress_data[progress_id]['message'] = '正在读取场景配置…'
            print(f"[zym loadUser] 已接到请求 progress_id={progress_id} user={username}")

        secenExcelPath = './received_dir/' + 'scene_excel/' + sceneName + '/prompt.xlsx'
        # binary_data = read_xlsx_to_binary(secenExcelPath)

        sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
        entries = os.listdir(sceneDirPath)
        # 使用 os.path.isdir() 检查每个条目是否为目录
        subSceneNameList = [
            entry for entry in entries
            if os.path.isdir(os.path.join(sceneDirPath, entry))
               and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
        print(subSceneNameList)
        sheetName = 'LUI1'
        data = pd.read_excel(secenExcelPath, sheet_name=sheetName)
        subSceneCol = 1
        firstSubSceneColName = data.columns[subSceneCol]
        subSceneNameListOrder = data.iloc[:, 1].dropna().tolist()
        subSceneNameListOrder.insert(0, firstSubSceneColName)
        if len(subSceneNameListOrder) == len(subSceneNameList):
            subSceneNameList = subSceneNameListOrder
            print("cnmcnm--------------------------------")
            print(subSceneNameList)

        finalExcelPath = './received_dir/' + 'scene_excel/' + \
                         sceneName + '/' + subSceneNameList[0] + '/prompt.xlsx'

        secenExcelPath = finalExcelPath

        print("[zym loadUser] kaishi")

        # 进入本子时，重置小模型ID为3003
        from app_chat.global_state import GLOBAL_STATE
        GLOBAL_STATE.user_little_model_id[username] = "3003"

        # 先后台灌向量（进度条靠它往前走），scene prompt 另写短锁，避免热重载后读 Excel 把进度卡在 0%
        parse_input.load_user(username, progress_id=progress_id)

        if os.path.exists(secenExcelPath):
            res = read_prompt_from_file(secenExcelPath)
            res2 = prompt_to_ghp(res)
            prompt_mem_key = resolve_prompt_storage_key(username, originRealName)
            parse_input.set_user_prompt(user_name=prompt_mem_key, prompt=res2[0])
            parse_input.set_user_params(user_name=prompt_mem_key, params=res2[1])
        if originRealName == username:
            global_lock[username] = RLock()
            chat_history[username] = []
            chat_history_used[username] = []
            speech_history[username] = ""
            chat_content[username] = {}
            chat_count[username] = 0
            auto_safe_count[username] = 0
        else:
            global_lock[originRealName] = RLock()
            chat_history[originRealName] = []
            chat_history_used[originRealName] = []
            speech_history[originRealName] = ""
            chat_content[originRealName] = {}
            chat_count[originRealName] = 0
            auto_safe_count[originRealName] = 0
        print('[zym loadUser] wancheng')

        # 用户登录，添加到全局列表
        if username not in online_users:
            online_users.append(username)
        # 返回进度ID和其他信息
        response['progress_id'] = progress_id
        response['subSceneList'] = subSceneNameList
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        if 'progress_id' in locals():
            progress_data[progress_id]['status'] = 'error'
            progress_data[progress_id]['message'] = str(e)

        response['subSceneList'] = []
        response['msg'] = str(e)
        response['error_num'] = 1
    return JsonResponse(response)


@require_http_methods(["GET"])
def loadUserSimplify(request):
    response = {}
    try:
        username = request.GET.get('username')

        print("[zym loadUserSimplify] kaishi")
        global_lock[username] = RLock()
        chat_history[username] = []
        chat_history_used[username] = []
        chat_content[username] = {}
        speech_history[username] = ""
        print('[zym loadUserSimplify] wancheng')

        # 用户登录，添加到全局列表
        online_users.append(username)
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
    return JsonResponse(response)


@require_http_methods(["GET"])
def getBookListByName(request):
    username = request.GET.get('username')
    sid = request.GET.get('sid')
    limit = request.GET.get('limit')  # 新增：获取限制数量参数
    print('[zym views]getBookListByName:', username, sid)
    response = {}
    try:
        # 如果demo book没有加载,那么从scene目录下复制并分割给当前用户
        demobookItems = UserNotebook.objects.filter(
            username=RANDOM_USER_NAME, sid=sid)
        if demobookItems.exists():
            demobook = demobookItems[0]
        else:
            demobook = None  # 或者设置为其他默认值
        if demobook is None:
            print('[zym views]getbooklistbyname:' + 'demobook is None')
            # res = UserNotebook.objects.filter(
            #     username=username,
            #     sid=sid
            # ).order_by('-bookId')
            # syncUsers不为空，且包含username，匹配的是:
            # 字符串开头的用户名/ 逗号后面的用户名/ 用户名后面跟着逗号/ 用户名在字符串结尾
            res = UserNotebook.objects.filter(
                Q(username=username, sid=sid) |
                Q(syncUsers__regex=r'(^|,\s*)' + username + r'(\s*,|$)', sid=sid)
            ).defer('context_data').order_by('-bookId')
            # 如果有limit参数，则限制数量
            total_count = res.count()
            if limit and limit.isdigit():
                res = res[:int(limit)]

            serialized_res = json.loads(serializers.serialize("json", res))
            # 遍历序列化后的结果，增加 cardNum 字段
            for item in serialized_res:
                fields = item['fields']
                fields.pop('context_data', None)  # 删除context_data字段

                fullName = f"{fields['username']}_{fields['bookName']}"
                card_count = Card.objects.filter(username=fullName).count()
                fields['cardNum'] = card_count

            response['list'] = serialized_res
            response['totalCount'] = total_count
            # response['list'] = json.loads(serializers.serialize("json", res))
            response['msg'] = 'success'
            response['demoBookName'] = ''
            response['error_num'] = 0
            return JsonResponse(response)
        userdemoItems = UserNotebook.objects.filter(
            username=username, bookName=demobook.bookName, sid=sid)
        if userdemoItems.exists():
            userdemo = userdemoItems[0]
        else:
            userdemo = None  # 或者设置为其他默认值
        print(demobook, userdemo)

        sceneItem = scene.objects.filter(sid=sid)
        sceneName = sceneItem[0].sceneDescription
        bookName = demobook.bookName
        print(sceneName, bookName)
        if userdemo is None:
            print('[zym views]getbooklistbyname:' + 'userdemo is None')
            sceneDirPath = './received_dir/' + 'scene_excel/' + \
                           sceneName + '/' + RANDOM_USER_NAME
            userDirPath = './received_dir/' + 'user_raw_file/' + username + '_' + bookName

            if not os.path.exists(userDirPath):
                os.makedirs(userDirPath)
            if not os.path.exists(sceneDirPath):
                os.makedirs(sceneDirPath)
            for file in os.listdir(sceneDirPath):
                print(file)
                tar_path = userDirPath + '/' + file
                src_path = sceneDirPath + '/' + file
                if not os.path.isdir(src_path):
                    shutil.copy(src_path, tar_path)
                else:
                    tar_dir = tar_path
                    if os.path.exists(tar_dir):
                        shutil.rmtree(tar_dir)
                    shutil.copytree(src_path, tar_dir)
            # 创建数据库条目,并分割给用户
            new_item = UserNotebook(
                username=username,
                bookName=bookName,
                bookId=int(datetime.now().timestamp() * 1000),
                bookdescription=demobook.bookdescription,
                sid=demobook.sid,
                comments=demobook.comments,
                context_data=demobook.context_data,
                writer=demobook.writer
            )
            new_item.save()
            uploader = scene.objects.get(sid=sid).uploader
            cardSrcItems = Card.objects.filter(username=uploader + '_' + bookName)
            cardItems = Card.objects.filter(username=RANDOM_USER_NAME + '_' + bookName)
            if cardSrcItems.exists():
                contents_to_exclude = set(cardItems.values_list('content', flat=True))
                # 包含了在cardSrcItems中但不在cardItems中具有相同content的记录
                cardSrcItems = cardSrcItems.exclude(content__in=contents_to_exclude)
                if cardSrcItems.exists():
                    cardItems = [item for item in cardItems] + [item for item in cardSrcItems]
                    cardItems = Card.objects.filter(pk__in=[card.pk for card in cardItems])
            cardUserItems = Card.objects.filter(username=username + '_' + bookName)
            if cardUserItems.exists():
                user_contents_to_exclude = set(cardUserItems.values_list('content', flat=True))
                # 包含了在cardItems中但不在cardUserItems中具有相同content的记录
                cardItems = cardItems.exclude(content__in=user_contents_to_exclude)
            for item in cardItems:
                new_card = Card(
                    username=username + "_" + bookName,
                    model_id=item.model_id,
                    status=item.status,
                    content=item.content,
                    title=item.title,
                    score=item.score,
                    time_params=item.time_params,
                    history=item.history,
                    seed=item.seed,
                    color=item.color,
                    reason=item.reason,
                    keyWords=item.keyWords,
                    contentTitle=item.contentTitle,
                    scoreSFT=item.scoreSFT,
                    colorSFT=item.colorSFT,
                    reasonSFT=item.reasonSFT,
                    type=item.type,
                    preIndex=item.preIndex,
                    postIndex=item.postIndex,
                    lastContent=item.lastContent,
                    writer=item.writer
                )
                new_card.save()

            # 正则表达式，用于匹配“卡片”后跟一个或多个数字，直到遇到非数字字符
            title_pattern = re.compile(r'卡片(\d+(?:,\d+)*)')
            username_condition = username + "_" + bookName
            cardItemsTarget = Card.objects.filter(username=username_condition)

            for item in cardItemsTarget:
                # 使用正则表达式搜索匹配的数字
                match = title_pattern.search(item.title)
                if match:
                    # 提取数字字符串，然后将其分割为数字列表
                    numbers_str = match.group(1)
                    numbers = [int(num) for num in numbers_str.split(',')]

                    # 对于每个数字，查找匹配的 Card 对象
                    for number in numbers:
                        # 查找 cid 等于 number 的 Card 对象
                        original_card = Card.objects.filter(cid=number).first()
                        if original_card and original_card.content:
                            # 确保 content 包含数字，如果包含，则找到对应的 Card 对象
                            matching_cards = Card.objects.filter(
                                username=username_condition,
                                content=original_card.content
                            )
                            if matching_cards.exists():
                                # 替换原标题中的数字为找到的 Card 的 cid
                                new_title = item.title.replace(str(number), str(matching_cards[0].cid))
                                item.title = new_title
                                item.save()

            # 场景预置文档,demo文档分割
            # parse_input.split_scene_to_user(
            #     sceneName, username + "_" + bookName)
            # uploader = scene.objects.get(sid=sid).uploader
            # print('[zym views]getbooknamelist, uploader=', uploader)
            # parse_input.split_user_to_user(
            #     uploader + "_" + bookName, username + "_" + bookName)
            from concurrent.futures import ThreadPoolExecutor
            uploader = scene.objects.get(sid=sid).uploader
            print('[zym views]getbooknamelist, uploader=', uploader)

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = []
                # 提交两个并行任务
                future1 = executor.submit(parse_input.split_scene_to_user,
                                          scene_name=sceneName, user_name=username + "_" + bookName)
                future2 = executor.submit(parse_input.split_user_to_user,
                                          user_from_name=uploader + "_" + bookName,
                                          user_name=username + "_" + bookName)
                futures.extend([future1, future2])

                # 等待所有任务完成
                for future in futures:
                    try:
                        future.result()
                    except Exception as e:
                        print(f'[getBookListByName] 并行处理时出错: {e}')

        res = UserNotebook.objects.filter(
            Q(username=username, sid=request.GET.get('sid')) |
            Q(syncUsers__regex=r'(^|,\s*)' + username + r'(\s*,|$)', sid=request.GET.get('sid'))
        ).defer('context_data').order_by('-bookId')
        # 如果有limit参数，则限制数量
        total_count = res.count()
        if limit and limit.isdigit():
            res = res[:int(limit)]

        # print(res)
        serialized_res = json.loads(serializers.serialize("json", res))
        # 遍历序列化后的结果，增加 cardNum 字段
        for item in serialized_res:
            # 查询 Card 中 username == fullName 的记录数
            fields = item['fields']
            fields.pop('context_data', None)  # 删除context_data字段

            fullName = f"{fields['username']}_{fields['bookName']}"
            card_count = Card.objects.filter(username=fullName).count()

            # 在字段中加入 cardNum
            fields['cardNum'] = card_count

        # 保持 response['list'] 类型不变，直接将序列化后的结果传递给 response['list']
        response['list'] = serialized_res
        response['totalCount'] = total_count    # 新增，用户在此场景的本子数量
        # response['list'] = json.loads(serializers.serialize("json", res))
        response['msg'] = 'success'
        response['demoBookName'] = bookName
        response['error_num'] = 0
    except Exception as e:
        print(str(e))
        response['list'] = []
        response['msg'] = str(e)
        response['error_num'] = 1
    #     print("t4")
    return JsonResponse(response)


@require_http_methods(["GET"])
def getSceneByName(request):
    response = {}
    try:
        username = request.GET.get('username')
        res = scene.objects.filter(username='1')
        # 创建一个列表来存储 (scene, maxbookId) 元组
        scene_with_maxbookid = []

        for s in res:
            # 查找 UserNotebook 表中与 scene 的 sid 相同的记录，并找出 bookId 最大的
            # max_book = UserNotebook.objects.filter(sid=s.sid, username=username).aggregate(max_bookId=Max('bookId'))['max_bookId']
            max_book = UserNotebook.objects.filter(
                Q(username=username, sid=s.sid) |
                Q(syncUsers__regex=r'(^|,\s*)' + username + r'(\s*,|$)', sid=s.sid)
            ).aggregate(max_bookId=Max('bookId'))['max_bookId']

            # 如果找到了对应的 bookId，则将 scene 和 maxbookId 作为元组加入列表
            if max_book is not None:
                max_book = int(max_book)  # 确保 max_book 是整数类型
                scene_with_maxbookid.append((s, max_book))
            else:
                # 如果找不到对应的 maxbookId，可以将其设置为某个最小值（如 -1）
                scene_with_maxbookid.append((s, -1))

        # 按 maxbookId 从大到小排序 scene
        ordered_scene = sorted(scene_with_maxbookid, key=lambda x: x[1], reverse=False)

        # 提取排序后的 scene 对象
        ordered_res = [s[0] for s in ordered_scene]

        scenes_wihout_demo = scene.objects.filter(username='0').filter(uploader=username)
        response['list'] = json.loads(serializers.serialize("json", ordered_res))
        response['scene_without_demo'] = json.loads(serializers.serialize("json", scenes_wihout_demo))
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        print(str(e))
        response['list'] = []
        response['msg'] = str(e)
        response['error_num'] = 1
    return JsonResponse(response)


@csrf_exempt
def getSceneSummary(request):
    data = json.loads(request.body)
    scene = data["scene"]
    subScene = data["subScene"]
    response = {}
    try:
        # 读取summary.json文件
        with open('./received_dir/summary.json', 'r', encoding='utf-8') as f:
            all_summaries = json.load(f)

        # 寻找匹配的场景和子场景
        scene_match = None
        subscene_match = None

        # 寻找精确匹配的场景
        for s in all_summaries:
            if s["scene"] == scene:
                scene_match = s
                break

        # 如果找不到精确匹配的场景，寻找最相似的场景
        if scene_match is None:
            max_similarity = 0
            for s in all_summaries:
                similarity = util.calculate_similarity(scene, s["scene"])
                if similarity > max_similarity:
                    max_similarity = similarity
                    scene_match = s

        # 如果找到了场景，寻找匹配的子场景
        if scene_match:
            # 寻找精确匹配的子场景
            for sub in scene_match.get("subscenes", []):
                if sub["subscene"] == subScene:
                    subscene_match = sub
                    break

            # 如果找不到精确匹配的子场景，寻找最相似的子场景
            if subscene_match is None and scene_match.get("subscenes"):
                max_similarity = 0
                for sub in scene_match["subscenes"]:
                    similarity = util.calculate_similarity(subScene, sub["subscene"])
                    if similarity > max_similarity:
                        max_similarity = similarity
                        subscene_match = sub

        # 返回匹配结果
        if subscene_match:
            response['summary'] = subscene_match["summary"]
        elif scene_match:
            # 如果没有匹配的子场景但有匹配的场景，返回场景的摘要
            response['summary'] = scene_match["summary"]
        else:
            # 如果什么都没找到
            response['summary'] = "仔细考虑当前场景和子场景阶段特征。"

        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['summary'] = "仔细考虑当前场景和子场景阶段特征。"
        response['msg'] = str(e)
        response['error_num'] = 1
    return JsonResponse(response)


@csrf_exempt
def saveSceneExcel(request):
    data = json.loads(request.body)
    response = {}
    try:
        base64_encoded_file = data["file"]
        binary_data = base64.b64decode(base64_encoded_file)
        # print(data['sid'])
        # print(type(data['sid']))sname

        scene_excel_path = './received_dir/' + \
                           'scene_excel/' + data["sname"] + '/prompt.xlsx'
        print('Writing scene excel file')
        directory = os.path.dirname(scene_excel_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(scene_excel_path, 'wb') as file:
            # 写入二进制数据
            file.write(binary_data)

        response['subSceneList'] = processSubScene(
            scene_excel_path, './received_dir/' + 'scene_excel/' + data["sname"])
        # 这里把总excel分为多个子excel
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        print(f"[saveSceneExcel] Error: {str(e)}")
        response['subSceneList'] = []
        response['msg'] = str(e)
        response['error_num'] = 1
    return JsonResponse(response)


@csrf_exempt
def saveSceneDoc(request):
    print('[saveSceneDoc]', datetime.now())
    data = json.loads(request.body)
    response = {}
    try:
        base64_encoded_file = data["file"]
        binary_data = base64.b64decode(base64_encoded_file)
        # print(data['sid'])
        # print(type(data['sid']))sname

        scene_excel_path = './received_dir/' + 'scene_excel/' + \
                           data["sname"] + '/' + data['filename']
        print('Writing scene pdf file', data['filename'])
        directory = os.path.dirname(scene_excel_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(scene_excel_path, 'wb') as file:
            # 写入二进制数据
            file.write(binary_data)

        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
    #     print("t4")
    return JsonResponse(response)


@csrf_exempt
def saveSceneDocOK(request):
    print('[saveSceneDocOK]', datetime.now())
    data = json.loads(request.body)
    sceneName = data["sceneName"]
    haveFile = int(data["havefile"])

    try:
        response = {}
        if haveFile == 0:
            # scene.objects.filter(
            #     sceneDescription=sceneName).update(username='1')
            response['msg'] = 'success'
            response['error_num'] = 0
            return JsonResponse(response)
    except Exception as e:
        print(e)
        response['msg'] = str(e)
        response['error_num'] = 1
        return JsonResponse(response)

    global scene_lock
    scene_lock[sceneName] = RLock()
    scene_lock[sceneName].acquire()

    secenDirPath = './received_dir/' + 'scene_excel/' + sceneName
    # bookList=[]
    filesList = []
    if os.path.exists(secenDirPath):
        files_and_dirs = os.listdir(secenDirPath)
        for file in files_and_dirs:
            if os.path.isfile(os.path.join(secenDirPath, file)):
                if file.endswith(".xlsx"):
                    continue
                filesList.append(file)
    print('[saveSceneDocOK]:filesList', filesList)
    print('[saveSceneDocOK]:开始分割场景文档', datetime.now())

    # for file in filesList:
    #     parse_input.get_split_docs_vectors_scene(
    #         scene_name=sceneName, docs_name=file)
    # 使用线程池并行处理文件
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for file in filesList:
            future = executor.submit(parse_input.get_split_docs_vectors_scene,
                                     scene_name=sceneName, docs_name=file)
            futures.append(future)

        # 等待所有任务完成
        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f'[saveSceneDocOK] 处理文件时出错: {e}')

    print('[saveSceneDocOK]:分割场景文档结束', datetime.now())
    scene_lock[sceneName].release()

    # scene.objects.filter(sceneDescription=sceneName).update(username='1')

    response = {}
    try:
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        print(e)
        response['msg'] = str(e)
        response['error_num'] = 1
    return JsonResponse(response)


@csrf_exempt
def chageContent(request):
    data = json.loads(request.body)
    response = {}
    try:
        from app_chat.views_generate_output_article import _fix_directory_numbering

        card = Card.objects.get(cid=data['cid'])  # some_cid 是你要更新的记录的 ID

        # 🔥 如果是目录卡，检查并修正目录部分的序号
        new_content = data['newContent']
        if card.title == "本子输出目录卡":
            # 提取目录部分（第一个"# "之前的内容）
            lines = new_content.split('\n')
            directory_end_idx = len(lines)
            for i, line in enumerate(lines):
                if line.strip().startswith('# ') and i > 0:
                    directory_end_idx = i
                    break

            directory_part = '\n'.join(lines[:directory_end_idx])
            article_part = '\n'.join(lines[directory_end_idx:])

            # 修正目录部分的序号
            fixed_directory = _fix_directory_numbering(directory_part)
            if fixed_directory != directory_part:
                print(f"[chageContent] 检测到目录卡序号错误，已自动修正")
                new_content = fixed_directory + ('\n' + article_part if article_part.strip() else '')

        card.content = new_content
        card.contentTitle = data['newContentTitle']
        card.keyWords = data['newKeyWords']
        card.save()
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
    #     print("t4")
    return JsonResponse(response)


# 作者更新整个共生区内容
@csrf_exempt
def changeInterGrowth(request):
    data = json.loads(request.body)
    response = {}
    try:
        card = Card.objects.get(cid=data['cid'])
        card.interGrowthTA2GL = data['newInterGrowth']
        card.subareaAndHLAndSugTA2GL = data['subareaAndHLAndSugTA2GL']
        card.save()

        # 获取原始内容进行分析
        username = data.get('username')
        book_name = data.get('bookName')

        # 检查所有需要回复的用户
        if username and book_name:
            try:
                # 获取当前用户的notebook
                notebook = UserNotebook.objects.get(username=username, bookName=book_name)

                # 获取同步用户列表
                sync_users_str = notebook.syncUsers
                if sync_users_str:
                    # 解析同步用户列表
                    sync_users = [user.strip() for user in sync_users_str.split(',') if user.strip()]

                    # 排除当前用户的coacher
                    try:
                        user_obj = User.objects.get(username=username)
                        current_level = user_obj.level  # 获取当前用户的等级
                        coacher = user_obj.coacher
                        if coacher in sync_users:
                            sync_users.remove(coacher)
                    except User.DoesNotExist:
                        current_level = None  # 如果当前用户不存在，设置为None
                        pass  # 用户不存在，不排除coacher

                    # 排除同级用户
                    if current_level is not None:
                        users_to_remove = []
                        for sync_username in sync_users:
                            try:
                                sync_user_obj = User.objects.get(username=sync_username)
                                if sync_user_obj.level == current_level:
                                    users_to_remove.append(sync_username)
                            except User.DoesNotExist:
                                # 如果同步用户不存在，跳过
                                continue

                        # 从sync_users中移除同级用户
                        for user_to_remove in users_to_remove:
                            sync_users.remove(user_to_remove)

                    # 获取该本子中所有有TA2GL共生问答的卡片
                    card_username = username + "_" + book_name
                    all_cards = Card.objects.filter(username=card_username)
                    intergrowthTA2GL_cards = [card for card in all_cards if card.interGrowthTA2GL.strip()]

                    # 用于跟踪每个用户在所有卡片中的未完成区域
                    all_incomplete_users = {}

                    # 检查每张卡片
                    for card in intergrowthTA2GL_cards:
                        card_content = card.interGrowthTA2GL

                        # 解析区域 - 找出所有问题序号的位置
                        section_positions = []
                        section_pattern = re.compile(r'(\d+)\.')
                        for match in section_pattern.finditer(card_content):
                            section_positions.append((int(match.group(1)), match.start()))

                        # 如果没有找到任何序号，跳过此卡片
                        if not section_positions:
                            continue

                        # 添加结尾位置
                        section_positions.append((float('inf'), len(card_content)))

                        # 排序区域（按序号位置）
                        section_positions.sort(key=lambda x: x[0])

                        # 检查每个区域内的用户回复
                        completed_sections = {}  # 记录每个区域已完成回复的用户

                        for i in range(len(section_positions) - 1):
                            start_idx = section_positions[i][1]
                            end_idx = section_positions[i + 1][1]
                            section_content = card_content[start_idx:end_idx]
                            section_number = section_positions[i][0]

                            # 找出该区域内所有的用户回复
                            user_pattern = re.compile(r'<([^>]+)>')
                            replied_users = user_pattern.findall(section_content)

                            # 记录已回复的用户
                            completed_sections[section_number] = replied_users

                        # 检查哪些用户没有在所有区域回复
                        all_sections = [pos[0] for pos in section_positions[:-1]]  # 除去末尾的无限大

                        for user in sync_users:
                            # 如果用户不在all_incomplete_users中，初始化
                            if user not in all_incomplete_users:
                                all_incomplete_users[user] = []

                            # 检查该用户在当前卡片中的未完成区域
                            for section_num in all_sections:
                                if user not in completed_sections.get(section_num, []):
                                    # 记录未完成的项目 (卡片ID, 区域号)
                                    all_incomplete_users[user].append((card.cid, section_num))

                    # 确定哪些用户有未完成的回复
                    todo_users = [user for user, incomplete_items in all_incomplete_users.items()
                                  if incomplete_items]  # 如果有任何未完成项，则加入todo列表

                    # 更新syncTodo字段
                    if todo_users:
                        notebook.syncTodo = ", ".join(todo_users)
                    else:
                        notebook.syncTodo = ""  # 如果所有用户都完成了所有卡片的所有回复，清空syncTodo

                    # 保存notebook
                    notebook.save()

                    # 添加到响应中
                    # response['incomplete_users'] = incomplete_users
                    # response['syncTodo'] = notebook.syncTodo
            except UserNotebook.DoesNotExist:
                pass  # notebook不存在，忽略检查

        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
    return JsonResponse(response)


# 非作者用户更新特定区域内容
@csrf_exempt
def changeInterGrowthForUser(request):
    data = json.loads(request.body)
    response = {}
    try:
        card = Card.objects.get(cid=data['cid'])

        # 获取当前内容
        current_content = card.interGrowthTA2GL
        section_number = data['sectionNumber']  # 例如 "1"
        user_name = data['userName']  # 用户名
        user_content = data['userContent']  # 用户输入的内容

        writer_name = data.get('writerName')  # 作者用户名
        book_name = data.get('bookName')  # 本子名称

        # 插入用户内容
        # 构建要插入的格式
        # user_reply = f"<{user_name}>{user_content}\n"
        user_reply = f"\n<{user_name}>{user_content}"

        # 构建正则表达式模式来找到正确的位置
        all_sections = re.findall(r'(\d+)\.', card.interGrowthTA2GL)
        if section_number == all_sections[-1]:  # 如果是最后一个区域
            pattern = f"({section_number}\\..*?)$"
        else:
            pattern = f"({section_number}\\..*?)(?=\\n\\d+\\.|$)"

        # 使用正则表达式替换
        updated_content = re.sub(
            pattern,
            f"\\1{user_reply}",
            current_content,
            flags=re.DOTALL
        )

        # 更新卡片内容
        card.interGrowthTA2GL = updated_content
        card.save()

        # 检查此用户是否完成了所有卡片的所有问题
        if writer_name and book_name:
            try:
                # 获取作者的notebook
                notebook = UserNotebook.objects.get(username=writer_name, bookName=book_name)

                # 获取同步用户列表
                sync_users_str = notebook.syncUsers
                if sync_users_str and user_name in sync_users_str:
                    # 解析同步用户列表
                    sync_users = [user.strip() for user in sync_users_str.split(',') if user.strip()]

                    # 只检查当前用户
                    if user_name in sync_users:
                        # 获取该本子中所有有共生问答的卡片
                        card_username = writer_name + "_" + book_name
                        all_cards = Card.objects.filter(username=card_username)
                        intergrowth_cards = [c for c in all_cards if c.interGrowthTA2GL.strip()]

                        # 检查用户是否有未完成的问题
                        has_incomplete_sections = False

                        # 检查每张卡片
                        for c in intergrowth_cards:
                            card_content = c.interGrowthTA2GL

                            # 解析区域 - 找出所有问题序号的位置
                            section_positions = []
                            section_pattern = re.compile(r'(\d+)\.')
                            for match in section_pattern.finditer(card_content):
                                section_positions.append((int(match.group(1)), match.start()))

                            # 如果没有找到任何序号，跳过此卡片
                            if not section_positions:
                                continue

                            # 添加结尾位置
                            section_positions.append((float('inf'), len(card_content)))

                            # 排序区域（按序号位置）
                            section_positions.sort(key=lambda x: x[0])

                            # 检查每个区域内的用户回复
                            for i in range(len(section_positions) - 1):
                                start_idx = section_positions[i][1]
                                end_idx = section_positions[i + 1][1]
                                section_content = card_content[start_idx:end_idx]

                                # 找出该区域内所有的用户回复
                                user_pattern = re.compile(r'<([^>]+)>')
                                replied_users = user_pattern.findall(section_content)

                                # 如果当前用户没有在此区域回复，标记为未完成
                                if user_name not in replied_users:
                                    has_incomplete_sections = True
                                    break

                            # 如果在当前卡片发现未完成区域，无需继续检查其他卡片
                            if has_incomplete_sections:
                                break

                        # 更新syncTodo字段
                        if not has_incomplete_sections:
                            # 当前用户完成了所有卡片的所有问题
                            # 从syncTodo中移除
                            sync_todo = notebook.syncTodo
                            if sync_todo:
                                todo_users = [u.strip() for u in sync_todo.split(',') if u.strip()]
                                if user_name in todo_users:
                                    todo_users.remove(user_name)
                                    notebook.syncTodo = ", ".join(todo_users)
                                    notebook.save()

                        # response['all_completed'] = not has_incomplete_sections
            except UserNotebook.DoesNotExist:
                pass  # notebook不存在，忽略检查

        response['msg'] = 'success'
        response['error_num'] = 0
        response['updated_content'] = updated_content
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1

    return JsonResponse(response)


def get_ai_evaluation(section_number, section_question, content, card_content):
    """
    使用大模型评估回答并生成建议
    实际中需要调用大模型API
    """
    promptHL = """你是对文本问答内容进行打分的专家，首先注意，下面的红蓝融合不仅是军事政工领域，也能用于教育和群组学习等领域，如果文本问答不涉及下面的红蓝融合理念第一层，但与认知、教育、群组学习等有关，请你依据下面红蓝融合理念第二至五层（可以越过第一层直接打2至5分）、是否有利于认知水平提升、是否有利于实现目标等来给分！

    若与红蓝融合有关，则你需要对文本问答内容进行红蓝融合度评估打分，红蓝融合度打分规则如下:
    1.红蓝融合五层理念是你打分需要参考的最主要标准，具体如下：
    第一层：人文<红>和科技<蓝>的融合（传统方式与新兴技术的结合）；
    第二层：认知<红>和行动<蓝>的融合（认知与行动需要一致，认知为行动提供理论基础，行动实践为认知提供真实验证，知行合一，行动不用非常具体但要有此意识）；
    第三层：自上而下贯彻带领<红>+自下而上创造示范<蓝>的融合（如组织中领导层向下进行示范牵引、基层成员执行及发挥创造，或其他协作形式）；
    第四层：先进组织认知中，目标<红>和任务<蓝>的融合（如目标的分解、放大、击穿，任务能够指向目标，为目标服务）；
    第五层：静态边界堤坝<红>和动态筛分洪流<蓝>的融合（静态堤坝指一些边界性限制，动态筛分洪流指运用第二层、第三层、第四层中的一些理念，如知行是否合一、组织不同层级成员上下是否联通、是否分清目标和任务等，来筛选出最优质的内容并扩散共生）
    2.（1）上面的红蓝融合理念由浅到深呈金字塔型，由底层基础到上层升维共分为5层，得分对应着由低到高的1-5分，
    （2）如果文本问答内容能体现出前面的红蓝融合五层理念中任意一层，则最低从1分开始，体现出红蓝融合五层理念的层次越高，得分越高，否则得分越低。
    例如：文本问答内容能够体现人文和科技的融合（第一层），则从1分开始；在1分基础上若还能达到行和知的融合，有"怎么做"的意识（第二层），则加到2分；在2分基础上若不能达到自上而下和自下而上的融合（第三层），如仅体现了自上而下没有体现自下而上或两个都有体现但达不到融合，则不能达到3分，得2.5分
    补充说明：前面说的"体现"，只要有一定体现的意识即可，不必过于严苛、死板，请把握好程度
    注意：1-5分范围内，若给小数分值，只考虑按0.5的步长调整。
    （3）由于不能达到红蓝融合（红蓝分离）的情况也存在，所以除了上面的1-5分以外，你还需要注意0-1分的含义，文本问答内容若只体现了<红>或<蓝>的内涵，体现不出红蓝的"融合"，则不超过1分。
    小数分值参考标准：文本问答内容体现低级红高级黑（使用庸俗夸张的方式赞扬或抹黑），按程度给0分或0.2分；体现仅红或仅蓝（只谈其中一个），给0.4分；体现以蓝表红（认为<蓝>就是<红>），给0.6分；体现红蓝组合（简单组合，并不融合），给0.8分
    （4）你还需要考虑文本问答内容与红蓝融合的相关性，与认知无关的内容给0分
    （5）另外请注意：当你想要打高于3分时，即3-5分，需要稍多做些考虑。科技+人文\行+知（第一二层，即1-2分），都偏向于个人，有一些组织意识；而更深入的第三四五层需要能够很好地体现群组视角，且逐层深入
    具体标准：你在判别是否达到第三层（即是否能打到3分）时，判据之一：需要体现群组视角；判别是否达到第四层（即是否能打到4分）时，判据之一：需要体现先进组织（目标任务意识清晰，有助于成员共生）；判别是否达到第五层（即是否能打到5分）时，判据之一：需要体现熵减生态（是否包含：a.面向成长、b.真实目标驱动、c.群组共生）
    （6）文本如果是问答内容，回答如果很好地、有针对性地回复了问题，包含想法、看法和做法，且对实际执行具有一些指导意义，则可以视程度提高0.5分或1分
    3.注意，你只需且必须要按"分值_颜色_改进建议"格式输出！
    分值方面，是你综合以上规则对给出的图文信息做出的打分；
    颜色方面，只要大于或等于1分直接输出紫色，若小于1分，图文信息过<红>输出红色，过<蓝>输出蓝色，注意小于1分只能输出红色或蓝色，不能是紫色或其他！
    改进建议方面，请你提出的改进点≤3个，对于每个改进点，分别提出<20字左右>的改进策略和建议，依据包括：
    （1）是否体现对应的红蓝融合五层理念，为什么；
    （2）文本问答内容是否具有针对性，是否具体、可操作、可实施；
    （3）文本问答内容是否有能深入扩展、探究、优化提升的潜力
    注意你给出改进建议一定要和问答及参照文本的内容高度相关，对涉及到的想法做法等给出改进建议，且角色针对性强，以这个为主！然后以红蓝打分理由中导致得分下降的因素、思维模式的可能调整为辅。给出的想法、做法建议尽可能具体，有真实行动上能够立即执行的清晰明确的指导。格式模板为"改进点1：xxx\n改进点2：xxx..."。
    整体格式例如：0.4分_蓝色_具体改进点建议
    2.5分_紫色_具体改进点建议
    4.0分_紫色_具体改进点建议
    ...（其他分值，但一定要按以上要求，额外要注意并不是短文本得分就低、长文本得分就高，请按照上述打分标准进行，不要有这种偏见，做到公正准确）"""

    print("共生问题及用户回答：" + section_question + '\n回答：' + content)
    prompt_use = promptHL + '\n\n问答参照的文字内容：\n' + card_content + '\n\n需要你打分及给出改进建议的文本问答内容：\n' + '\n问题：' + section_question + '\n回答：' + content
    gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt_use)

    # 生成0-5分，保留一位小数
    score = float(extract_number(gpt4_response))
    color = extract_color(gpt4_response)
    suggestion = extract_reason(gpt4_response)

    # 根据分数生成标题
    if score < 1:
        title = "回答缺乏具体分工细节和协作机制"
    elif score < 3:
        title = "回答基本满足要求但缺乏深度"
    elif score < 4:
        title = "回答内容良好但可以更加系统"
    else:
        title = "回答非常全面且有深度"

    # 生成建议内容
    # if score < 1:
    #     suggestion = "改进点1：需要明确每个成员的具体负责模块和协作接口\n改进点2：缺少公私份比例的具体数字和理由说明"
    # elif score < 3:
    #     suggestion = "改进点1：可以增加更多细节来丰富您的回答\n改进点2：考虑将理论与实践结合起来"
    # elif score < 4:
    #     suggestion = "改进点1：尝试提供更深入的思考\n改进点2：可以增加一些创新性的见解"
    # else:
    #     suggestion = "改进点1：回答已经很好，可以考虑添加更多前沿观点"

    # 在返回前等待3秒
    # time.sleep(3)

    return score, title, suggestion


def get_ai_modification(original_content, suggestion, card_content, section_question):
    """
    根据建议修改内容
    实际中需要调用大模型API
    """
    # 提取建议点
    print("共生回答修改建议：" + suggestion)
    # suggestions = re.findall(r'改进点\d+：(.*?)(?=\n|$)', suggestion)

    # 构建提示词
    prompt = f"""
    请你作为思维引导师，为用户提供启发性的建议，引导他们自主改进回答内容。

    ## 原始卡片内容
    {card_content}

    ## 当前问题
    {section_question}

    ## 用户当前回答
    {original_content}

    ## 已有的改进建议
    {suggestion}

    ## 任务
    请生成一些简短但有启发性的引导内容，穿插在用户当前回答的文本内容之间（穿插在合适的位置，不要改变用户当前回答内容），用"TODO:"来标识，帮助用户改进自己的回答。不要直接给出完整答案，而是通过提问、引导和思考框架帮助用户自己发现改进点，牵引用户思考后完善自己的回答。

    你的引导应该:
    1. 与问题"{section_question}"本身高度相关
    2. 保持用户原有观点和主要内容
    3. 提供宏观和微观层面的思考视角
    4. 包含一些引导性问题或思考点
    5. 适当留白，让用户填补思考空间
    6. 指出关键概念但不完全展开
    7. 可适当参考已有的改进建议中指出的不足
    8. 仍保持简短精炼（让用户几十字左右就能完整回答问题），保持自然连贯的表达
    
    引导方式可以是:
    - 引导性问题："考虑一下...是否可以...?"
    - 思考框架："尝试从...和...两个维度思考"
    - 概念挖空："___是解决此问题的关键因素"
    - 反思性提示："回顾你提到的...，如何更深入地展开?"

    请直接给出基于用户当前回答穿插引导后的文本内容，确保像是一个思考伙伴而非权威指导者。内容应当自然流畅，起到"熵减"作用，帮助用户更聚焦地思考问题。
    篇幅要求保持简短精炼，引导点不超过2个，整体几十字左右，不要做任何额外说明。
    """

    modified_content = gpt4_api.make_gpt4o_text_requests(prompt)

    # 构建修改后的内容
    # modified_content = original_content + "\n\n"
    # modified_content += "根据建议，我补充以下内容：\n"
    # for i, sug in enumerate(suggestions):
    #     modified_content += f"- {sug}\n"

    # # 在返回前等待3秒
    # time.sleep(3)

    return modified_content


def update_card_ratings(card, user_name, section_number, score, suggestion):
    """更新卡片的评分与建议数据"""
    try:
        if card.subareaAndHLAndSugTA2GL:
            subarea_data = json.loads(card.subareaAndHLAndSugTA2GL)
        else:
            subarea_data = {"areas": {}, "ratings": {}, "comprehensive": {}}

        # 初始化ratings数据结构
        if "ratings" not in subarea_data:
            subarea_data["ratings"] = {}
        if user_name not in subarea_data["ratings"]:
            subarea_data["ratings"][user_name] = {}

        # 保存评分和建议
        subarea_data["ratings"][user_name][section_number] = {
            "score": score,
            "suggestion": suggestion
        }
        newData = json.dumps(subarea_data, ensure_ascii=False)

        # 保存更新后的数据
        card.subareaAndHLAndSugTA2GL = newData
        card.save()
        return newData
    except Exception as e:
        print(f"更新评分数据失败: {str(e)}")
        return None


@csrf_exempt
def getAIFeedback(request):
    """获取AI评分与建议"""
    data = json.loads(request.body)
    response = {}

    try:
        cid = data.get('cid')
        card_content = data.get('cardContent')
        section_number = data.get('sectionNumber')
        section_question = data.get('sectionQuestion')
        content = data.get('content')
        user_name = data.get('userName')

        # 获取卡片
        card = Card.objects.get(cid=cid)

        # 调用AI评分与建议 (这里简化实现，实际需要调用大模型)
        score, title, suggestion = get_ai_evaluation(section_number, section_question, content, card_content)

        # 更新卡片的subareaAndHLAndSugTA2GL字段
        updated_data = update_card_ratings(card, user_name, section_number, score, suggestion)

        response['error_num'] = 0
        response['score'] = score
        response['title'] = title
        response['suggestion'] = suggestion
        response['updated_subareaData'] = updated_data  # 返回更新后的完整数据

    except Exception as e:
        response['error_num'] = 1
        response['msg'] = str(e)

    return JsonResponse(response)


@csrf_exempt
def getAIModification(request):
    """获取AI修改建议"""
    data = json.loads(request.body)
    response = {}

    try:
        card_content = data.get('cardContent')
        section_question = data.get('sectionQuestion')
        original_content = data.get('originalContent')
        suggestion = data.get('suggestion')

        # 调用AI修改内容 (这里简化实现，实际需要调用大模型)
        modified_content = get_ai_modification(original_content, suggestion, card_content, section_question)

        response['error_num'] = 0
        response['modified_content'] = modified_content

    except Exception as e:
        response['error_num'] = 1
        response['msg'] = str(e)

    return JsonResponse(response)


@csrf_exempt
def generateComprehensiveAdvice(request):
    """生成综合建议"""
    data = json.loads(request.body)
    response = {}

    try:
        # 获取请求参数
        cid = data.get('cid')
        content = data.get('content')
        interGrowthTA2GL = data.get('interGrowthTA2GL')
        username = data.get('username')
        subareaAndHLAndSugTA2GL = data.get('subareaAndHLAndSugTA2GL')

        # 查询Card
        card = Card.objects.get(cid=cid)

        # 解析现有的subareaAndHLAndSugTA2GL数据
        try:
            subarea_data = json.loads(subareaAndHLAndSugTA2GL) if subareaAndHLAndSugTA2GL else {
                "areas": {},
                "ratings": {},
                "comprehensive": {}
            }
        except json.JSONDecodeError:
            subarea_data = {
                "areas": {},
                "ratings": {},
                "comprehensive": {}
            }

        # 提取当前用户的回答
        user_responses = extract_user_responses(content, interGrowthTA2GL, username)

        # 调用大模型生成综合建议
        comprehensive_advice = get_comprehensive_advice(user_responses, username)

        # 更新数据
        if "comprehensive" not in subarea_data:
            subarea_data["comprehensive"] = {}

        subarea_data["comprehensive"][username] = comprehensive_advice

        # 更新Card
        card.subareaAndHLAndSugTA2GL = json.dumps(subarea_data, ensure_ascii=False)
        card.save()

        response['error_num'] = 0
        response['msg'] = "生成综合建议成功"
        response['updated_data'] = card.subareaAndHLAndSugTA2GL

    except Card.DoesNotExist:
        response['error_num'] = 1
        response['msg'] = "卡片不存在"
    except Exception as e:
        response['error_num'] = 2
        response['msg'] = str(e)

    return JsonResponse(response)


def extract_user_responses(content, interGrowthTA2GL, username):
    """提取卡片内容和用户的回答"""
    # 解析interGrowthTA2GL，提取用户回答
    user_responses = []

    # 添加卡片主要内容
    user_responses.append({
        'type': 'main_content',
        'content': content
    })

    # 解析共生区内容
    if interGrowthTA2GL:
        # 匹配数字序号开头的部分
        import re
        sections = []
        current_section = None

        for line in interGrowthTA2GL.split('\n'):
            # 如果是序号开头，创建新部分
            match = re.match(r'(\d+)\.(.*)', line)
            if match:
                if current_section:
                    sections.append(current_section)
                section_num = match.group(1)
                section_title = match.group(2).strip()
                current_section = {
                    'number': section_num,
                    'title': section_title,
                    'content': '',
                    'user_responses': []
                }
            elif current_section is not None:
                # 检查是否是当前用户的回答
                user_match = re.match(r'<([^>]+)>(.*)', line)
                if user_match:
                    user = user_match.group(1)
                    response = user_match.group(2).strip()
                    if user == username:
                        current_section['user_responses'].append(response)

                current_section['content'] += line + '\n'

        # 添加最后一部分
        if current_section:
            sections.append(current_section)

        # 将解析结果添加到用户回答中
        for section in sections:
            if section['user_responses']:
                user_responses.append({
                    'type': 'section',
                    'number': section['number'],
                    'title': section['title'],
                    'responses': section['user_responses']
                })

    return user_responses


def get_comprehensive_advice(user_responses, username):
    """
    使用大模型生成综合建议
    """
    # 构建提示
    prompt = f"""
    根据以下综合内容，为用户'{username}'生成五个方面的精准建议，以帮助团队更好地协作和完成项目，包括理解提升、目标锁定、双领分工、issue协同和对齐验收：
    
    ## 用户提供的信息:
    """

    # 添加主要内容
    for item in user_responses:
        if item['type'] == 'main_content':
            prompt += f"【卡片素材的主要内容】：\n{item['content']}\n\n"
        elif item['type'] == 'section':
            prompt += f"【问题{item['number']}】：{item['title']}\n"
            prompt += f"【回答】：\n" + "\n".join(item['responses']) + "\n\n"

    prompt += """
    ## 请分析上述内容，组长用户仔细理解了卡片素材内容，并认真回答了几个相关问题，现在请你辅助组长用户思考，基于卡片素材内容，以及用户对问题的回答，帮助组长形成具有他们小组特色的相关方案，从以下五个关键维度提供具体、可执行的建议，每个维度用100字左右简要点题，直击要害，要求：
    1. 这条非常重要：一定不要直接给出完整方案，而是以建议、牵引、发问引导思考的口吻，通过向用户提问、引导和思考框架等帮助用户自己思考清晰如何落地实施本组方案，并稍加引导思考如果出现异常了该怎么办，而不是直接给用户一个方案便于偷懒省时！
    2. 每个维度控制在30-50字
    3. 直接给出可执行的具体建议，不要笼统表述
    4. 针对实际卡片内容、用户实际情况提供定制化建议
    5. 使用行动导向的语言，通过建议或发问的口吻引导用户思考清晰自己的小组本周要"做什么"、并简要想想如果节奏出现异常应该怎么办
    
    五个关键维度如下，这只是最简单的描述，你需要根据实际卡片内容、用户回答情况，对此进行修改和扩展，以建议、提问引导的口吻让用户思考如何细化自己组的落地方案：
    - <理解提升>：针对用户对卡片素材的理解深度，对如何更全面理解作为种子、火种的卡片素材内容提供建议。指出概念理解的盲点、可能被忽略的重要信息，以及如何建立更系统的知识框架。
    - <目标锁定>：明确小组应达到的具体目标，包括明确的量化指标（如"代码注释共120+行"、"小组编码真实参与人数3人及以上"等），工作内容的边界，以及难度梯度的设置，确保目标既有挑战性又可实现。
    - <双领分工>：合适的任务分配建议，使组长能有效分配任务并便于整合成果。对能力差异的团队成员提供合理安排（如让能力较弱的成员参与重复性任务以提升能力），确保组长、需求员、周志员、优裁员、展示员等5位组内成员都有成长空间。
    - <issue协同>：提供使用GitLab中issue、board、tag等协作工具的具体策略，以辅助项目管理。建议应简洁实用，工具作为辅助手段而非复杂障碍，重点是提高团队协作效率。
    - <对齐验收>：建议团队如何验证工作成果，包括如何确保达成小组共识、如何确保项目可自治完成、如何验证最终成果与主题需求的一致性，以及设置哪些关键检查点。
    
    请确保建议简洁明了、具体可行，每个标签下不超过100字简要阐明即可，不要冗长，但要精准，并直接使用上述五个标签格式输出，格式按照：<理解提升>xxx\n<目标锁定>xxx\n<双领分工>xxx\n<issue协同>xxx\n<对齐验收>xxx
    """

    ai_advice = generate_ai_advice(prompt)
    # time.sleep(3)  # 模拟API调用延迟

    return ai_advice


def generate_ai_advice(prompt):
    """
    模拟大模型API生成建议
    实际中应该调用真实的API
    """
    # 示例建议
#     advice = """<理解提升>建议进一步深化对核心概念的理解，形成更系统的认知框架
# <目标锁定>建议增加更具体的时间节点和可衡量的成功标准
# <双领分工>建议在关键任务上设置备份角色，增强团队韧性
# <issue协同>建议建立更结构化的问题跟踪机制
# <对齐验收>建议在项目中期增加一次对齐检查点"""
    advice = gpt4_api.make_gpt4o_text_requests(prompt)

    return advice


@require_http_methods(["GET"])
def deleteChoosedCard(request):
    #     print("t3")
    response = {}
    try:
        cid = request.GET.get('cid')
        card = Card.objects.filter(cid=cid).first()
        username = None
        keyword = None
        if card and card.title == "关键词神经元永久卡":
            username = card.username
            keyword = (card.keyWords or '').strip()
        Card.objects.filter(cid=cid).delete()
        if username and keyword:
            from app_chat.views_generate_permanent_card import _cleanup_keyword_from_notebook_if_orphan
            _cleanup_keyword_from_notebook_if_orphan(username, keyword, exclude_cids=[])

        # print(json.loads(serializers.serialize("json", res)))
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
    #     print("t4")
    return JsonResponse(response)


@require_http_methods(["GET"])
def deleteBook(request):
    response = {}
    try:
        # res=UserNotebook.objects.filter(username=request.GET.get('username'))
        # response['list']=json.loads(serializers.serialize("json", res))
        username = request.GET.get('username')
        bookId = request.GET.get('bookId')

        user_notebooks = UserNotebook.objects.filter(
            username=username,
            bookId=bookId
        )

        # 检查是否只有一个记录
        if user_notebooks.count() == 1:
            # 获取唯一的记录
            user_notebook = user_notebooks.first()
            bookName = user_notebook.bookName

            # 构建卡片的 username 格式
            card_username = username + "_" + bookName

            # 1. 删除对应的卡片
            Card.objects.filter(username=card_username).delete()

            # 2. 删除向量库数据 (使用基于文件路径的函数)
            try:
                print(f"=== 开始删除向量数据: {username}_{bookName} ===")
                parse_input.delete_notebook_vectors_simple(username, bookName)
            except Exception as e:
                print(f"删除向量库时出错，但继续删除本子: {e}")

            # 3. 删除 UserNotebook
            user_notebooks.delete()

            print(f"成功删除本子: {username}_{bookName}")
        else:
            # 如果没有记录或有多个记录，只进行原来的删除操作
            user_notebooks.delete()

        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['list'] = []
        response['msg'] = str(e)
        response['error_num'] = 1

    return JsonResponse(response)


@csrf_exempt
def mergeCardBackend(request):
    data = json.loads(request.body)
    #     print("asd")
    response = {}
    CardContentList = []
    CardIndexList = data['cardIndexList'].split(',')
    finalContent = ''
    minStatus = 9999
    minModel_idSum = 0
    try:
        for i, id_str in enumerate(CardIndexList):  # cradlist中存的是字符串形式的index
            id = int(id_str)
            card = Card.objects.get(cid=id)
            # content = str(i) + '.' + card.content
            cardContent = card.content
            index = cardContent.find("回答：")
            # 去掉 "回答：" 之前的内容，包括 "回答：" 本身
            if index != -1:
                cardContent = cardContent[index + len("回答："):]
            content = '[文本' + str(i+1) + ']:\n' + cardContent
            CardContentList.append(content)

            model_id = int(card.model_id)
            if model_id >= 0:
                model_id = -1
            minModel_idSum = minModel_idSum + model_id

            status = int(card.status)
            if status >= 0:
                status = -1
            minStatus = min(minStatus, status - 1)

        username = data['username']
        originRealName = data['originRealName']
        datetime = data["datetime"]
        model_id = data["model_id"]
        status = data['status']
        sceneName = data['sceneName']
        subSceneName = data['subSceneName']
        func = int(data['func'])
        prompt = ""
        text = data['text']
        s = ""
        contentTotal = ""

        if func == 0:  # 这里写产生内容的逻辑
            s = "总结"
            prompt = global_var.store_memory[username]["prompt"]["LUI3"]["multi_summarize"]
            # prompt="我现在有如下几段文本，我需要你将这几段文本进行"+"总结"+"并输出其结果"
            CardContentList.insert(0, prompt)
            finalContent = get_crad_text.get_card_texts(
                CardContentList, username)
        elif func == 1:
            s = "建议"
            prompt = global_var.store_memory[username]["prompt"]["LUI3"]["multi_suggestions"]
            # prompt="我现在有如下几段文本，我需要你对这几段文本提出"+"建议"+"并输出其结果"
            CardContentList.insert(0, prompt)
            finalContent = get_crad_text.get_card_texts(
                CardContentList, username)
        elif func == 2:
            # prompt="我现在有如下几段文本，我需要你对这几段文本给出"+"学习指导"+"并输出其结果"
            prompt = global_var.store_memory[username]["prompt"]["LUI3"]["multi_study_guide"]
            CardContentList.insert(0, prompt)
            s = "指导"
            finalContent = get_crad_text.get_card_texts(
                CardContentList, username)
        elif func == 3:
            s = "合并"
            mergeRequest = "您是综合多段文本进行融合的专家，下面是几段待融合文本，几段文本内容涉及的话题、格式、风格可能类似也可能不同，你需要" \
                           "首先分析它们的异同点、优缺点等，然后用中文进行融合\n\n注意事项及细节：\n1.进行内容融合时，内容来源比例、话题、风格、" \
                           "格式等均需要考虑合适，融合不能太生硬，需要连接、过渡、关联得当\n2.以[文本1]为主要内容来源，其他为辅助内容来源，必要时" \
                           "你也可以自己进行一些合理的补充，最好标识好来源"
            prompt = mergeRequest + "\n请确保融合后的内容符合以上任务说明及注意事项的要求，几段待融合文本如下："
            CardContentList.insert(0, prompt)
            finalContent = get_crad_text.get_card_texts(
                CardContentList, username)
            # for c in CardContentList:
            #     finalContent += c
        elif func == 4:
            s = "理解"
            # prompt = "我现在有如下这一段文本，请你给出对这段文本的简要理解，" + "并输出其结果"
            prompt = global_var.store_memory[username]["prompt"]["LUI3"]["single_understand"]
            CardContentList.insert(0, prompt)
            finalContent = get_crad_text.get_card_texts(
                CardContentList, username)
        elif func == 5:
            s = "批判"
            prompt = global_var.store_memory[username]["prompt"]["LUI3"]["single_critique"]
            # prompt = "我现在有如下这一段文本，请你对这段文本进行批判，并给出改正建议，" + "并输出其结果"
            CardContentList.insert(0, prompt)
            finalContent = get_crad_text.get_card_texts(
                CardContentList, username)
        elif func == 6:
            s = "大纲"
            # prompt = "我现在有如下这一段文本，请你给出这段文本的大纲" + "并输出其结果"
            prompt = global_var.store_memory[username]["prompt"]["LUI3"]["single_outline"]
            CardContentList.insert(0, prompt)
            finalContent = get_crad_text.get_card_texts(
                CardContentList, username)
        elif func == 10:
            s = "自定义功能"
            # prompt = global_var.store_memory[username]["prompt"]["LUI3"]["user_define"]
            prompt = text + "\n请确保迭代后的内容符合以上任务及注意事项的要求，文本如下："
            CardContentList.insert(0, prompt)
            finalContent = get_crad_text.get_card_texts(
                CardContentList, username)

        title = "卡片" + data['cardIndexList'] + s + "结果"

        score, color, reason = red_bule_rate.get_rate(username, finalContent)

        card_params = None
        model_num = global_var.store_memory[username]["model_num"]
        if model_num == 0:
            card_params = global_var.config
        elif model_num == 1:
            card_params = global_var.mixtralConfig
        elif model_num == 2:
            card_params = global_var.llama3Config
        elif model_num == 3:
            card_params = global_var.kimiConfig
        elif model_num == 4:
            card_params = global_var.claudeConfig
        elif model_num == 5:
            card_params = global_var.deepseekConfig
        elif model_num == 6:
            card_params = global_var.deepseekConfig
        else:
            card_params = global_var.config  # 或者其他默认配置

        keyTopics = data.get('keyTopics', '[]')
        # 将 keyTopics 字符串解析为列表
        keyTopicsList = json.loads(keyTopics)

        system_prompt = (
            '你是擅长阅读理解文本并总结关键词的专家。'
            '你接下来将得到一段文本和已有的关键词备选集合，你需要阅读理解这段文本，总结出1到3个关键词。'
            '如果备选集合中有合适的关键词，请直接选取；如果没有合适的，再自行总结。共需得出1到3个关键词，请尽量先在备选集合里选取相对合适的，实在没有再新加。'
            '输出格式如“关键词1，关键词2，关键词3”，无其他多余内容！'
        )
        prompt = (
            f"{system_prompt}\n"
            f"已有的关键词备选集合：{', '.join(keyTopicsList)}\n"
            f"需要你总结1到3个关键词的文本：\n{finalContent}"
        )
        kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)  # 获取kimi的回答
        keyWords = kimi_response.choices[0].message.content
        # gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt)
        # keyWords = gpt4_response

        system_prompt_title = '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，' \
                              '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，同样' \
                              '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + finalContent
        kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)  # 获取kimi的回答
        # contentTitle = kimi_response_title.choices[0].message.content
        # gpt4_response_title = gpt4_api.make_gpt4o_text_requests(prompt_title)
        gpt4_response_title = kimi_response_title.choices[0].message.content
        # 判断当前是哪一个子场景做卡片
        sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
        entries = os.listdir(sceneDirPath)
        # 检查每个条目是否为目录
        subSceneNameList = [
            entry for entry in entries
            if os.path.isdir(os.path.join(sceneDirPath, entry))
               and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
        secenExcelPath = './received_dir/' + 'scene_excel/' + sceneName + '/prompt.xlsx'
        sheetName = 'LUI1'
        data = pd.read_excel(secenExcelPath, sheet_name=sheetName)
        subSceneCol = 1
        firstSubSceneColName = data.columns[subSceneCol]
        subSceneNameListOrder = data.iloc[:, 1].dropna().tolist()
        subSceneNameListOrder.insert(0, firstSubSceneColName)
        if len(subSceneNameListOrder) == len(subSceneNameList):
            subSceneNameList = subSceneNameListOrder
        try:
            index = subSceneNameList.index(subSceneName)
            # 索引从0开始，但我们需要从1开始，所以加1
            subSceneOrder = "S" + str(index + 1) + ":"
            gpt4_response_title = subSceneOrder + gpt4_response_title
        except ValueError:
            # 处理subSceneName不在列表中的情况
            print(f"警告：{subSceneName}不在子场景列表中")
            subSceneOrder = "S0:"  # 或设置其他默认值
            gpt4_response_title = subSceneOrder + gpt4_response_title
        contentTitle = gpt4_response_title

        # 🔥 判定四色和DMT属性
        from app_chat.card_analyzer import analyze_four_color_type, analyze_dmt_level, analyze_four_color_type_with_llm, analyze_dmt_level_with_llm
        card_content = "迭代追问：\n" + text + "\n\n回答：\n" + finalContent
        four_color_type = analyze_four_color_type(card_content)
        dmt_level = analyze_dmt_level(card_content)
        # print(f"[mergeCardBackend] 卡片四色类型: {four_color_type}, DMT层次: {dmt_level}")

        # 🔥 如果关键词判定为空，调用kimi LLM进行精准判定
        if not four_color_type:
            print(f"[mergeCardBackend] 关键词判定四色类型为空，调用kimi LLM进行判定...")
            four_color_type = analyze_four_color_type_with_llm(card_content)
        if not dmt_level:
            print(f"[mergeCardBackend] 关键词判定DMT层次为空，调用kimi LLM进行判定...")
            dmt_level = analyze_dmt_level_with_llm(card_content)

        print(f"[mergeCardBackend] 最终判定结果 - 四色类型: {four_color_type}, DMT层次: {dmt_level}")

        if originRealName != "":
            card = Card.objects.create(
                status=minStatus,  # 参与的迭代的次数
                content="迭代追问：\n" + text + "\n\n回答：\n" + finalContent,
                title=title,
                model_id=minModel_idSum,  # 参与融合的卡片个数
                username=username,
                score=score,
                color=color,
                reason=reason,
                time_params=card_params,
                keyWords=keyWords,
                contentTitle=contentTitle,
                writer=originRealName,
                four_color_type=four_color_type,  # 🔥 四色类型
                dmt_level=dmt_level  # 🔥 DMT层次
            )
            card.save()
        else:
            card = Card.objects.create(
                status=minStatus,  # 参与的迭代的次数
                content="迭代追问：\n" + text + "\n\n回答：\n" + finalContent,
                title=title,
                model_id=minModel_idSum,  # 参与融合的卡片个数
                username=username,
                score=score,
                color=color,
                reason=reason,
                time_params=card_params,
                keyWords=keyWords,
                contentTitle=contentTitle,
                four_color_type=four_color_type,  # 🔥 四色类型
                dmt_level=dmt_level  # 🔥 DMT层次
            )
            card.save()

        # rel=这里要获得相关问题
        response['finalContent'] = finalContent
        response['cardId'] = card.cid
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        # response['finalContent']=''
        print("my output error")
        print(e)
        response['msg'] = str(e)
        response['error_num'] = 1

    return JsonResponse(response)


@csrf_exempt
def saveAndReloadSceneExcel(request):
    data = json.loads(request.body)
    response = {}
    try:
        base64_encoded_file = data["file"]
        binary_data = base64.b64decode(base64_encoded_file)
        # print(data['sid'])
        # print(type(data['sid']))sname

        scene_excel_path = './received_dir/' + \
                           'scene_excel/' + data["sname"] + '/prompt.xlsx'
        print('Writing scene excel file')
        directory = os.path.dirname(scene_excel_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
        with open(scene_excel_path, 'wb') as file:
            # 写入二进制数据
            file.write(binary_data)

        sceneDirPath = './received_dir/' + 'scene_excel/' + data["sname"]
        # 遍历目录中的所有项
        for item in os.listdir(sceneDirPath):
            # 获取项的完整路径
            path = os.path.join(sceneDirPath, item)

            # 检查这个路径是否确实是一个文件夹
            if os.path.isdir(path):
                # 检查文件夹名称是否以'_image'结尾
                if not item.endswith('_image') and item != "cardImage":
                    # 如果不以'_image'结尾，删除这个文件夹及其内容
                    shutil.rmtree(path)

        processSubScene(scene_excel_path, sceneDirPath)
        entries = os.listdir(sceneDirPath)
        # 使用 os.path.isdir() 检查每个条目是否为目录
        subSceneNameList = [
            entry for entry in entries
            if os.path.isdir(os.path.join(sceneDirPath, entry))
               and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
        sheetName = 'LUI1'
        secenExcelPath = './received_dir/' + 'scene_excel/' + data["sname"] + '/prompt.xlsx'
        data = pd.read_excel(secenExcelPath, sheet_name=sheetName)
        subSceneCol = 1
        firstSubSceneColName = data.columns[subSceneCol]
        subSceneNameListOrder = data.iloc[:, 1].dropna().tolist()
        subSceneNameListOrder.insert(0, firstSubSceneColName)
        if len(subSceneNameListOrder) == len(subSceneNameList):
            subSceneNameList = subSceneNameListOrder
            print("cnmcnm--------------------------------")
            print(subSceneNameList)

        finalSubScencPath = sceneDirPath + '/' + \
                            subSceneNameList[0] + '/prompt.xlsx'
        scene_excel_path = finalSubScencPath
        username = data['username']
        # sceneName=data['sname']

        res = read_prompt_from_file(scene_excel_path)
        print(res)
        res2 = prompt_to_ghp(res)
        print(res2)
        parse_input.set_user_prompt(user_name=username, prompt=res2[0])
        parse_input.set_user_params(user_name=username, params=res2[1])

        response['subSceneList'] = subSceneNameList
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['subSceneList'] = []
        response['msg'] = str(e)
        response['error_num'] = 1
    #     print("t4")
    return JsonResponse(response)


@csrf_exempt
def getSubScene(request):
    print("1")
    data = json.loads(request.body)
    response = {}
    try:
        sceneName = data['secneName']
        sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
        entries = os.listdir(sceneDirPath)

        # 使用 os.path.isdir() 检查每个条目是否为目录
        subSceneNameList = [
            entry for entry in entries
            if os.path.isdir(os.path.join(sceneDirPath, entry))
               and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
        print("*************", subSceneNameList)
        response['subSceneList'] = subSceneNameList
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['subSceneList'] = []
        response['msg'] = str(e)
        response['error_num'] = 1
    #     print("t4")
    print("2")
    return JsonResponse(response)


@csrf_exempt
def changeText(request):
    data = json.loads(request.body)
    response = {}
    try:
        # card = Card.objects.get(cid=data['cid'])  # some_cid 是你要更新的记录的 ID
        minStatus = 9999
        minModel_idSum = 0
        card = Card.objects.get(cid=data['cid'])

        model_id = int(card.model_id)
        if model_id >= 0:
            model_id = -1
        minModel_idSum = minModel_idSum + model_id

        status = int(card.status)
        if status >= 0:
            status = -1
        minStatus = min(minStatus, status - 1)

        cid = data['cid']
        content = data['content']
        username = data['username']
        sceneName = data['sceneName']
        subSceneName = data['subSceneName']
        tarLen = (data['tarLen'])

        CardContentList = []
        title = ""
        prompt = ""
        cardPrompt = ""
        if len(content) < int(tarLen):
            title = "卡片" + cid + "扩写结果"
            prompt = "请你将下面这段文本在不改变核心内容原意的前提下，扩写至" + tarLen + "字左右："
            cardPrompt = "请你将原文在不改变核心内容原意的前提下，扩写至" + tarLen + "字左右"
        else:
            title = "卡片" + cid + "缩写结果"
            prompt = "请你将下面这段文本在不改变整体原意的前提下，缩写至" + tarLen + "字左右："
            cardPrompt = "请你将原文在不改变整体原意的前提下，缩写至" + tarLen + "字左右"
        CardContentList.append(prompt)
        CardContentList.append(content)
        # card.content = get_crad_text.get_card_texts(CardContentList, username)
        # card.save()
        finalContent = get_crad_text.get_card_texts(CardContentList, username)

        score, color, reason = red_bule_rate.get_rate(username, finalContent)

        card_params = None
        model_num = global_var.store_memory[username]["model_num"]
        if model_num == 0:
            card_params = global_var.config
        elif model_num == 1:
            card_params = global_var.mixtralConfig
        elif model_num == 2:
            card_params = global_var.llama3Config
        elif model_num == 3:
            card_params = global_var.kimiConfig
        elif model_num == 4:
            card_params = global_var.claudeConfig
        elif model_num == 5:
            card_params = global_var.deepseekConfig
        elif model_num == 6:
            card_params = global_var.deepseekConfig
        else:
            card_params = global_var.config  # 或者其他默认配置

        keyTopics = data.get('keyTopics', '[]')
        # 将 keyTopics 字符串解析为列表
        keyTopicsList = json.loads(keyTopics)

        system_prompt = (
            '你是擅长阅读理解文本并总结关键词的专家。'
            '你接下来将得到一段文本和已有的关键词备选集合，你需要阅读理解这段文本，总结出1到3个关键词。'
            '如果备选集合中有合适的关键词，请直接选取；如果没有合适的，再自行总结。共需得出1到3个关键词，请尽量先在备选集合里选取相对合适的，实在没有再新加。'
            '输出格式如“关键词1，关键词2，关键词3”，无其他多余内容！'
        )
        prompt = (
            f"{system_prompt}\n"
            f"已有的关键词备选集合：{', '.join(keyTopicsList)}\n"
            f"需要你总结1到3个关键词的文本：\n{finalContent}"
        )
        # kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)  # 获取kimi的回答
        # keyWords = kimi_response.choices[0].message.content
        gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt)
        keyWords = gpt4_response

        system_prompt_title = '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，' \
                              '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，同样' \
                              '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + finalContent
        # kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)  # 获取kimi的回答
        # contentTitle = kimi_response_title.choices[0].message.content
        gpt4_response_title = gpt4_api.make_gpt4o_text_requests(prompt_title)
        # 判断当前是哪一个子场景做卡片
        sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
        entries = os.listdir(sceneDirPath)
        # 检查每个条目是否为目录
        subSceneNameList = [
            entry for entry in entries
            if os.path.isdir(os.path.join(sceneDirPath, entry))
               and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
        secenExcelPath = './received_dir/' + 'scene_excel/' + sceneName + '/prompt.xlsx'
        sheetName = 'LUI1'
        data = pd.read_excel(secenExcelPath, sheet_name=sheetName)
        subSceneCol = 1
        firstSubSceneColName = data.columns[subSceneCol]
        subSceneNameListOrder = data.iloc[:, 1].dropna().tolist()
        subSceneNameListOrder.insert(0, firstSubSceneColName)
        if len(subSceneNameListOrder) == len(subSceneNameList):
            subSceneNameList = subSceneNameListOrder
        try:
            index = subSceneNameList.index(subSceneName)
            # 索引从0开始，但我们需要从1开始，所以加1
            subSceneOrder = "S" + str(index + 1) + ":"
            gpt4_response_title = subSceneOrder + gpt4_response_title
        except ValueError:
            # 处理subSceneName不在列表中的情况
            print(f"警告：{subSceneName}不在子场景列表中")
            subSceneOrder = "S0:"  # 或设置其他默认值
            gpt4_response_title = subSceneOrder + gpt4_response_title
        contentTitle = gpt4_response_title

        newCard = Card.objects.create(
            status=minStatus,  # 参与的迭代的次数
            content="字数调整迭代：\n" + cardPrompt + "\n\n\n回答：\n" + finalContent,
            title=title,
            model_id=minModel_idSum,  # 参与融合的卡片个数
            username=username,
            score=score,
            color=color,
            reason=reason,
            time_params=card_params,
            keyWords=keyWords,
            contentTitle=contentTitle
        )

        newCard.save()

        response['finalContent'] = finalContent
        response['cardId'] = newCard.cid
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
    #     print("t4")
    return JsonResponse(response)


@csrf_exempt
def setNewSubExcel(request):
    # print('begin change subExcel0')
    data = json.loads(request.body)
    response = {}
    try:
        username = data['username']
        sceneName = data['sceneName']
        subSceneName = data['subSceneName']
        origin_real = data.get('originRealName')

        scene_excel_path = './received_dir/' + 'scene_excel/' + \
                           sceneName + '/' + subSceneName + '/prompt.xlsx'
        print('begin change subExcel')

        res = read_prompt_from_file(scene_excel_path)
        print(res)
        res2 = prompt_to_ghp(res)
        print(res2)
        # parse_input.set_user_prompt(user_name=username, prompt=res2[0])
        # parse_input.set_user_params(user_name=username, params=res2[1])
        prompt_mem_key = resolve_prompt_storage_key(username, origin_real)
        if prompt_mem_key not in parse_input.lock:
            parse_input.lock[prompt_mem_key] = RLock()
        parse_input.set_user_prompt(user_name=prompt_mem_key, prompt=res2[0])
        parse_input.set_user_params(user_name=prompt_mem_key, params=res2[1])
        print('finish change subExcel')
        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
        print(e)
    return JsonResponse(response)


def processSubScene(excelPath, sceneDirPath):
    print("start process subScene!")
    subSceneNameList = []
    LUI1dfList = []
    LUI2dfList = []
    LUI3dfList = []
    LUI4dfList = []
    print(1)
    for j in range(4):
        sheetName = 'LUI' + str(j + 1)
        # print("1.0",excelPath)
        # fuuuuuuuuuuuck     为什么python不报包不存在的错误！！！！！！fuuuuuuuuuuuuuuuuuuuuuck
        data = pd.read_excel(excelPath, sheet_name=sheetName)
        # print("1.1")
        # subSceneNameList = []
        subSceneCol = 1
        firstSubSceneColName = data.columns[subSceneCol]

        subSceneCount = data[firstSubSceneColName].count() + 1

        excelFuncCol = 2
        excelRowCount = data[data.columns[excelFuncCol]].count() + 1
        sceneFuncCount = excelRowCount / subSceneCount  # 每个子场景的功能数

        if j == 0:
            subSceneNameList = data.iloc[:, 1].dropna().tolist()
            subSceneNameList.insert(0, firstSubSceneColName)
            print(subSceneNameList)
        # print(2)
        for i in range(subSceneCount):
            startRow = int(sceneFuncCount * i)
            endRow = int(sceneFuncCount * (i + 1) - 1)
            df = data.iloc[startRow:endRow].drop(columns=data.columns[1])
            if j == 0:
                LUI1dfList.append(df)
            elif j == 1:
                LUI2dfList.append(df)
            elif j == 2:
                LUI3dfList.append(df)
            elif j == 3:
                LUI4dfList.append(df)

    # print(3)
    for i, name in enumerate(subSceneNameList):

        directory = sceneDirPath + '/' + name
        if not os.path.exists(directory):
            os.makedirs(directory)
        print(directory)
        try:
            with pd.ExcelWriter(directory + '/prompt.xlsx', engine='xlsxwriter') as writer:
                LUI1dfList[i].to_excel(writer, sheet_name='LUI1', index=False)
                LUI2dfList[i].to_excel(writer, sheet_name='LUI2', index=False)
                LUI3dfList[i].to_excel(writer, sheet_name='LUI3', index=False)
                LUI4dfList[i].to_excel(writer, sheet_name='LUI4', index=False)
        except Exception as e:
            print(e)
    print("end process subScene!")
    return subSceneNameList


@csrf_exempt
def shareBook(request):
    data = json.loads(request.body)
    response = {}
    try:
        sharedUser = data['sharedUser']
        user = data['user']
        sharedBookName = data['sharedBookName']
        sceneName = data['sceneName']
        util.copy(sharedUser, user, sharedBookName, sceneName)

        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
        print(e)
    return JsonResponse(response)


@csrf_exempt
def updateBookTime(request):
    data = json.loads(request.body)
    response = {}
    try:
        userName = data['userName']
        bookName = data['bookName']
        newTime = data['newTime']

        userNotebook = UserNotebook.objects.get(username=userName, bookName=bookName)

        # 更新datetime字段为当前时间,保存更改
        userNotebook.bookId = newTime
        userNotebook.save(update_fields=['bookId'])

        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
        print(e)
    return JsonResponse(response)


@csrf_exempt
def react(request):
    data = json.loads(request.body)
    response = {}
    CardIndexList = data['cardIndexList'].split(',')
    content = ""
    ID = 0
    for i, id_str in enumerate(CardIndexList):  # cardList中存的是字符串形式的index
        id = int(id_str)
        ID = id
        card = Card.objects.get(cid=id)
        content = card.content

    try:
        text, score = React.react(content)

        # 更新card对象的content和score属性
        card = Card.objects.get(cid=ID)
        card.content = text
        card.score = score
        card.save()  # 保存更改到数据库

        response['msg'] = 'success'
        response['error_num'] = 0
    except Exception as e:
        response['msg'] = str(e)
        response['error_num'] = 1
        print(e)
    return JsonResponse(response)


@csrf_exempt
def updateBookDescri(request):
    data = json.loads(request.body)
    username = data["username"]
    bookname = data["bookname"]
    editedDescription = data["editedDescription"]

    try:
        user_notebook = UserNotebook.objects.get(username=username, bookName=bookname)
        user_notebook.bookdescription = editedDescription
        user_notebook.save()

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def updateBookSyncUsers(request):
    data = json.loads(request.body)
    username = data["username"]
    bookname = data["bookname"]
    editedSyncUsers = data["editedSyncUsers"]

    try:
        user_notebook = UserNotebook.objects.get(username=username, bookName=bookname)
        user_notebook.syncUsers = editedSyncUsers
        user_notebook.save()

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def updateBookSyncTodo(request):
    data = json.loads(request.body)
    username = data["username"]
    bookname = data["bookname"]
    syncTodo = data["syncTodo"]

    try:
        user_notebook = UserNotebook.objects.get(username=username, bookName=bookname)
        user_notebook.syncTodo = syncTodo
        user_notebook.save()

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def getFirstBookByName(request):
    data = json.loads(request.body)
    username = data["username"]

    try:
        user_notebooks = UserNotebook.objects.filter(
            Q(username=username)
        ).order_by('-bookId')
        first_notebook = user_notebooks.first()  # 获取第一个对象
        print(first_notebook.context_data)

        return JsonResponse({
            'status': 'success',
            'error_num': 0,
            'firstBook': {
                'username': first_notebook.username,
                'bookId': first_notebook.bookId,
                'bookName': first_notebook.bookName,
                'bookdescription': first_notebook.bookdescription,
                'comments': first_notebook.comments,
                'isShared': first_notebook.isShared,
                'sid': first_notebook.sid,
                'context_data': first_notebook.context_data,
            }
        }, status=201)
    except:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def merge2Responses(request):
    data = json.loads(request.body)
    username = data["username"]
    sourceResponse = data["sourceResponse"]
    targetResponse = data["targetResponse"]
    sourceModel = data["sourceModel"]
    targetModel = data["targetModel"]
    sceneName = data["sceneName"]
    subSceneName = data["subSceneName"]

    try:
        prompt = (
            f"您是将两段文本进行融合的专家，这两段文本是对同一个提出的问题或要求，两个不同模型给出的回答。\n"
            f"如果文本较长，你需要分模块、分段落找出两个回答的共识部分，对于其他部分则对比两个回答的优缺点并扩长化短，融合二者的优点进行互补。\n"
            f"注意事项：\n"
            f"1.第一段文本整体质量更高，在融合中需要占主要地位；第二段文本在一些方面上有优点，在融合中起辅助作用。\n"
            f"2.首先，你需要给出两个回答的共识、各自优缺点，用简单几句话说明你是如何做的融合；然后，给出融合后的内容。\n"
            f"下面是具体文本内容，请你按上述要求，对这两段文本进行融合，用中文完成：\n"
            f"第一段文本（主要）：\n{sourceResponse}"
            f"第二段文本（辅助）：\n{targetResponse}"
        )
        gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt)
        mergeContent = gpt4_response

        title = "来自模型2000的问答"
        score, color, reason = red_bule_rate.get_rate(username, mergeContent)
        card_params = global_var.config

        keyTopics = data.get('keyTopics', '[]')
        # 将 keyTopics 字符串解析为列表
        keyTopicsList = json.loads(keyTopics)

        system_prompt = (
            '你是擅长阅读理解文本并总结关键词的专家。'
            '你接下来将得到一段文本和已有的关键词备选集合，你需要阅读理解这段文本，总结出1到3个关键词。'
            '如果备选集合中有合适的关键词，请直接选取；如果没有合适的，再自行总结。共需得出1到3个关键词，请尽量先在备选集合里选取相对合适的，实在没有再新加。'
            '输出格式如“关键词1，关键词2”，无其他多余内容！'
        )
        prompt = (
            f"{system_prompt}\n"
            f"已有的关键词备选集合：{', '.join(keyTopicsList)}\n"
            f"需要你总结1到3个关键词的文本：\n{mergeContent}"
        )
        # kimi_response = kimi_api.make_requests(prompt, None, False, 0.8)  # 获取kimi的回答
        # keyWords = kimi_response.choices[0].message.content
        gpt4_response = gpt4_api.make_gpt4o_text_requests(prompt)
        keyWords = gpt4_response

        system_prompt_title = '你是擅长阅读理解文本并摘取或总结出一条标题的专家，你接下来将得到一段文本，你需要阅读理解这段文本，如果文中已有一些标题信息，' \
                              '请你摘取出来（取其中最高一级的、最有代表性的标题），超出10个字的，请你凝练到10个字左右；如果没有，请你自己总结出一个标题，同样' \
                              '不超过10个字。你只需要给出标题，除此之外，你不需要给出任何其他多余的内容！'
        prompt_title = system_prompt_title + '\n需要你摘取或总结出一条标题的文本：\n' + mergeContent
        # kimi_response_title = kimi_api.make_requests(prompt_title, None, False, 0.8)  # 获取kimi的回答
        # contentTitle = kimi_response_title.choices[0].message.content
        gpt4_response_title = gpt4_api.make_gpt4o_text_requests(prompt_title)
        # 判断当前是哪一个子场景做卡片
        sceneDirPath = './received_dir/' + 'scene_excel/' + sceneName
        entries = os.listdir(sceneDirPath)
        # 检查每个条目是否为目录
        subSceneNameList = [
            entry for entry in entries
            if os.path.isdir(os.path.join(sceneDirPath, entry))
               and not entry.endswith('_image') and entry != RANDOM_USER_NAME and entry != "cardImage"]
        secenExcelPath = './received_dir/' + 'scene_excel/' + sceneName + '/prompt.xlsx'
        sheetName = 'LUI1'
        data = pd.read_excel(secenExcelPath, sheet_name=sheetName)
        subSceneCol = 1
        firstSubSceneColName = data.columns[subSceneCol]
        subSceneNameListOrder = data.iloc[:, 1].dropna().tolist()
        subSceneNameListOrder.insert(0, firstSubSceneColName)
        if len(subSceneNameListOrder) == len(subSceneNameList):
            subSceneNameList = subSceneNameListOrder
        try:
            index = subSceneNameList.index(subSceneName)
            # 索引从0开始，但我们需要从1开始，所以加1
            subSceneOrder = "S" + str(index + 1) + ":"
            gpt4_response_title = subSceneOrder + gpt4_response_title
        except ValueError:
            # 处理subSceneName不在列表中的情况
            print(f"警告：{subSceneName}不在子场景列表中")
            subSceneOrder = "S0:"  # 或设置其他默认值
            gpt4_response_title = subSceneOrder + gpt4_response_title
        contentTitle = gpt4_response_title

        card = Card.objects.create(
            status=-2,  # 参与的迭代的次数
            content="主" + sourceModel + "辅" + targetModel + "融合回答：\n" + mergeContent,
            title=title,
            model_id=-2,  # 参与融合的卡片个数
            username=username,
            score=score,
            color=color,
            reason=reason,
            time_params=card_params,
            keyWords=keyWords,
            contentTitle=contentTitle
        )

        card.save()

        return JsonResponse({
            'mergeContent': mergeContent,
            'cardId': card.cid,
            'status': 'success',
            'error_num': 0,
        }, status=201)
    except Exception as e:
        print(e)
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
        }, status=201)


@csrf_exempt
def getSubordinatesList(request):
    data = json.loads(request.body)
    username = data["username"]

    try:
        # 获取所有以此用户为领航员的用户
        subordinates = User.objects.filter(coacher=username).values_list('username', flat=True)
        return JsonResponse({
            'status': 'success',
            'error_num': 0,
            'subordinates': list(subordinates)
        }, status=201)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'msg': str(e)
        }, status=201)


@csrf_exempt
def updateUserLevel(request):
    data = json.loads(request.body)
    username = data["username"]
    new_level = data["new_level"]

    try:
        user = User.objects.get(username=username)
        user.level = new_level
        user.save()
        return JsonResponse({
            'status': 'success',
            'error_num': 0
        }, status=201)
    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'msg': '用户不存在'
        }, status=201)


@csrf_exempt
def updateUserCoacher(request):
    data = json.loads(request.body)
    username = data["username"]
    new_coacher = data["new_coacher"]

    try:
        # 验证新的领航员是否存在
        coacher = User.objects.get(username=new_coacher)

        # 验证层级关系
        user = User.objects.get(username=username)
        level_hierarchy = {
            'GM': 'GL',
            'GL': 'TA',
            'TA': 'T',
            'T': 'S',
            'S': None
        }

        if coacher.level != level_hierarchy.get(user.level):
            return JsonResponse({
                'status': 'error',
                'error_num': 1,
                'msg': '领航员层级关系不符合要求'
            }, status=201)

        user.coacher = new_coacher
        user.save()
        return JsonResponse({
            'status': 'success',
            'error_num': 0
        }, status=201)
    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'error_num': 1,
            'msg': '用户或领航员不存在'
        }, status=201)