import re
import threading
import time
import json
import os
import pandas as pd
import asyncio
import uuid  # 添加uuid导入

# 🔥 新增：异步支持
from concurrent.futures import ThreadPoolExecutor
import nest_asyncio

nest_asyncio.apply()  # 允许在已有事件循环中运行

import traceback  # 添加traceback导入
import logging  # 添加logging导入

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from threading import RLock, Semaphore, Condition  # 添加Semaphore和Condition导入

import app_chat
from app_chat.global_state import GLOBAL_STATE
from app_chat.models import AutomationRecord, AutomationTask, Card
from app_chat import views
# from app_chat.views import chat_content
from llm_langchain import get_suma, get_topic, parse_input, global_var

# 配置日志(有点太乱)
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

# 添加全局任务映射
RUNNING_TASKS = {}  # {task_id: AutomationEngine实例}

# 🔥 新增：创建线程池用于异步执行
ASYNC_EXECUTOR = ThreadPoolExecutor(max_workers=20)

# 自动化「提问前智慧激发」：默认 False，与录制回放一致（不调用小模型包一层【智慧激发框架】）。
# 仅改本文件此常量即可；为 True 时会多跑一次提前 RAG 供小模型写深度建议。
AUTOMATION_DEPTH_SUGGESTION_ENABLED = False


# 🔥 新增：按用户分组的调度器，实现并发均衡
class UserScheduler:
    def __init__(self, username, max_concurrent_steps=4):
        self.username = username
        self.max_concurrent_steps = max_concurrent_steps
        self.semaphore = Semaphore(max_concurrent_steps)
        self.condition = Condition()
        self.waiting_tasks = []  # 等待执行的任务队列
        self.active_tasks = set()  # 正在执行的任务集合

    def acquire_step_slot(self, task_id):
        """获取步骤执行槽位"""
        with self.condition:
            if task_id not in self.waiting_tasks:
                self.waiting_tasks.append(task_id)

            while task_id not in self.active_tasks:
                # 检查是否能获取槽位
                if self.semaphore.acquire(blocking=False):
                    self.active_tasks.add(task_id)
                    if task_id in self.waiting_tasks:
                        self.waiting_tasks.remove(task_id)
                    print(f"[用户调度器] 用户 {self.username} 任务 {task_id} 获得执行槽位，当前活跃任务数：{len(self.active_tasks)}")
                    return True
                else:
                    print(
                        f"[用户调度器] 用户 {self.username} 任务 {task_id} 等待执行槽位，队列位置：{self.waiting_tasks.index(task_id) + 1}")
                    self.condition.wait(timeout=1)  # 等待1秒再试

    def release_step_slot(self, task_id):
        """释放步骤执行槽位"""
        with self.condition:
            if task_id in self.active_tasks:
                self.active_tasks.remove(task_id)
                self.semaphore.release()
                print(f"[用户调度器] 用户 {self.username} 任务 {task_id} 释放执行槽位，当前活跃任务数：{len(self.active_tasks)}")
                self.condition.notify_all()  # 通知所有等待的任务


# 🔥 新增：全局调度器管理器，为每个用户创建独立的调度器
class GlobalSchedulerManager:
    def __init__(self):
        self.user_schedulers = {}  # {username: UserScheduler}
        self.lock = RLock()

    def get_user_scheduler(self, username, max_concurrent_steps=4):
        """获取或创建用户的调度器"""
        with self.lock:
            if username not in self.user_schedulers:
                self.user_schedulers[username] = UserScheduler(username, max_concurrent_steps)
                print(f"[调度器管理器] 为用户 {username} 创建新的调度器，最大并发数：{max_concurrent_steps}")
            return self.user_schedulers[username]

    def cleanup_user_scheduler(self, username):
        """清理用户的调度器（当用户没有活跃任务时）"""
        with self.lock:
            if username in self.user_schedulers:
                scheduler = self.user_schedulers[username]
                # 只有当没有活跃任务时才清理
                if len(scheduler.active_tasks) == 0 and len(scheduler.waiting_tasks) == 0:
                    del self.user_schedulers[username]
                    print(f"[调度器管理器] 清理用户 {username} 的调度器")


# 全局调度器管理器实例
GLOBAL_SCHEDULER_MANAGER = GlobalSchedulerManager()


class AutomationEngine:
    def __init__(self, notebook_id, target_file, current_user=None, scene_name=None):
        self.notebook_id = notebook_id
        self.target_file = target_file
        self.scene_name = scene_name
        self.original_target_file = None  # 添加原始目标文件
        self.username = notebook_id.split('_')[0]  # 提取本子所有者名
        self._resolved_record_times = None  # NK2026 按主题解析后的录制批次 times

        # 🔥 新增：当前操作用户（用于卡片writer字段）
        self.current_user = current_user if current_user else self.username

        # 🔥 构造用于RAG和chat_content的用户ID：当前登录用户_本子名
        book_name = notebook_id.split('_', 1)[1] if '_' in notebook_id else 'default'
        self.rag_chat_user_id = f"{self.current_user}_{book_name}"

        # 🔥 关键修改：为每个自动化任务生成唯一的用户标识符
        # self.unique_user_id = f"{self.username}_{uuid.uuid4().hex[:8]}"  # 生成唯一用户ID
        self.unique_user_id = f"{self.current_user}_{uuid.uuid4().hex[:8]}"  # 使用current_user生成

        # 🔥 初始化唯一用户ID对应的全局变量，避免KeyError
        self._init_unique_user_globals()

        self.task = None
        self.stop_flag = False
        self.created_card_ids = []  # 记录创建的卡片ID
        self.last_qa_content = {}  # 记录最近的问答内容
        self.step_card_mapping = {}  # 记录每个步骤创建的卡片

        self.step_to_card_mapping = {}  # 记录每个步骤创建的卡片 {step_number: [card_ids]}
        self.card_selection_pattern = {}  # {step_number: {flow_created_steps, existing_cards} 或历史 list}

        # 🔥 简化超时机制
        self.step_start_time = None
        self.step_timeout_seconds = 240  # 4分钟超时

        print(f"[AutomationEngine] 创建实例: notebook_id={notebook_id}, unique_user_id={self.unique_user_id}, current_user={self.current_user}, scene_name={scene_name}")

    def _is_nk2026(self):
        from app_chat.automation_nk2026 import is_nk2026_ladder_scene
        return is_nk2026_ladder_scene(getattr(self, "scene_name", None))

    def _resolve_select_lists(self, action_data, file_list):
        """NK2026 场景强制按文件名矫正检索方式，其它场景沿用录制列表。"""
        from app_chat.automation_nk2026 import nk2026_retrieval_lists
        if self._is_nk2026():
            return nk2026_retrieval_lists(file_list)
        return adjust_lists_to_match(
            file_list,
            action_data.get("leftSelectList", [1]),
            action_data.get("rightSelectList", [3]),
        )

    def _init_unique_user_globals(self):
        """初始化唯一用户ID对应的全局变量，避免KeyError"""
        try:
            from app_chat.views import global_lock, chat_count, chat_history, chat_history_used, speech_history, \
                auto_safe_count, chat_content  # 导入全局变量

            # 初始化全局锁和相关变量
            global_lock[self.unique_user_id] = RLock()
            chat_history[self.unique_user_id] = []
            chat_history_used[self.unique_user_id] = []
            speech_history[self.unique_user_id] = ""
            chat_content[self.unique_user_id] = {}
            chat_count[self.unique_user_id] = 0
            auto_safe_count[self.unique_user_id] = 0

            print(f"[_init_unique_user_globals] 已初始化 {self.unique_user_id} 的全局变量")
        except Exception as e:
            print(f"[_init_unique_user_globals] 初始化失败: {str(e)}")

    def _seed_automation_prompt_slot(self):
        """启动时将本子 rag 键上的场景 prompt 复制到 automation 隔离槽（unique_user_id）。

        setNewSubExcel 与 construct_data 均通过 resolve_prompt_storage_key 读写该槽；
        第 1 步 send_message 若尚未 change_subscene，也需要此处种子，避免 KeyError。
        """
        import copy
        from threading import RLock
        from llm_langchain import global_var, parse_input

        src = self.rag_chat_user_id
        dst = self.unique_user_id
        dst_mem = global_var.store_memory.get(dst) or {}
        if dst_mem.get("prompt"):
            print(f"[_seed_automation_prompt_slot] {dst} 已有 prompt，跳过（恢复任务或已切换子场景）")
            return
        src_mem = global_var.store_memory.get(src) or {}
        prompt = src_mem.get("prompt")
        if not prompt:
            print(f"[_seed_automation_prompt_slot] 源键 {src} 无 prompt，跳过")
            return
        if dst not in parse_input.lock:
            parse_input.lock[dst] = RLock()
        parse_input.set_user_prompt(user_name=dst, prompt=copy.deepcopy(prompt))
        params = src_mem.get("params")
        if params is not None:
            parse_input.set_user_params(user_name=dst, params=copy.deepcopy(params))
        print(f"[_seed_automation_prompt_slot] 已从 {src} 复制 prompt 到 {dst}")

    def _save_execution_state(self):
        """保存当前执行状态"""
        if self.task:
            execution_state = {
                'created_card_ids': self.created_card_ids,
                'step_card_mapping': self.step_card_mapping,
                'last_qa_content': self.last_qa_content,
                'step_to_card_mapping': self.step_to_card_mapping,
                'card_selection_pattern': self.card_selection_pattern,
                'unique_user_id': self.unique_user_id  # 保存唯一用户ID以便恢复
            }
            self.task.execution_state = execution_state
            self.task.save()
            print(f"[保存状态] 第 {self.task.current_step} 步执行状态已保存")

    def _restore_execution_state(self):
        """恢复执行状态"""
        try:
            if self.task and self.task.execution_state:
                state = self.task.execution_state
                self.created_card_ids = state.get('created_card_ids', [])
                # 确保字典键为整型（JSON序列化会将int键转为str）
                self.step_card_mapping = {int(k): v for k, v in state.get('step_card_mapping', {}).items()}
                self.last_qa_content = state.get('last_qa_content', {})
                self.step_to_card_mapping = {int(k): v for k, v in state.get('step_to_card_mapping', {}).items()}
                self.card_selection_pattern = {int(k): v for k, v in state.get('card_selection_pattern', {}).items()}

                # 恢复唯一用户ID（如果之前保存过的话）
                saved_unique_id = state.get('unique_user_id')
                if saved_unique_id:
                    self.unique_user_id = saved_unique_id
                    # 重新初始化全局变量（可能程序重启后内存中的变量被清空）
                    self._init_unique_user_globals()

                print(f"[恢复状态] 已恢复 {len(self.created_card_ids)} 个卡片记录")
                print(f"[恢复状态] 恢复的unique_user_id: {self.unique_user_id}")
        except Exception as e:
            print(f"[恢复状态失败] {str(e)}")
            # 如果恢复失败，继续使用当前状态，不影响任务执行

    def _cleanup_unique_user_state(self):
        """清理唯一用户ID的状态数据，避免内存泄漏"""
        try:
            from app_chat.views import global_lock, chat_count, chat_history, chat_history_used, speech_history, \
                auto_safe_count, chat_content  # 导入全局变量

            # 清理所有全局变量中的数据
            if self.unique_user_id in global_lock:
                del global_lock[self.unique_user_id]
                print(f"[_cleanup_unique_user_state] 清理了 {self.unique_user_id} 的global_lock")

            if self.unique_user_id in chat_history:
                del chat_history[self.unique_user_id]
                print(f"[_cleanup_unique_user_state] 清理了 {self.unique_user_id} 的chat_history")

            if self.unique_user_id in chat_history_used:
                del chat_history_used[self.unique_user_id]
                print(f"[_cleanup_unique_user_state] 清理了 {self.unique_user_id} 的chat_history_used")

            if self.unique_user_id in speech_history:
                del speech_history[self.unique_user_id]
                print(f"[_cleanup_unique_user_state] 清理了 {self.unique_user_id} 的speech_history")

            if self.unique_user_id in chat_content:
                del chat_content[self.unique_user_id]
                print(f"[_cleanup_unique_user_state] 清理了 {self.unique_user_id} 的chat_content")

            if self.unique_user_id in chat_count:
                del chat_count[self.unique_user_id]
                print(f"[_cleanup_unique_user_state] 清理了 {self.unique_user_id} 的chat_count")

            if self.unique_user_id in auto_safe_count:
                del auto_safe_count[self.unique_user_id]
                print(f"[_cleanup_unique_user_state] 清理了 {self.unique_user_id} 的auto_safe_count")

            # 清理GLOBAL_STATE中的conversation_manager数据
            if hasattr(GLOBAL_STATE, 'conversation_manager'):
                # 这里可以添加具体的清理逻辑，如果conversation_manager支持的话
                print(f"[_cleanup_unique_user_state] 清理了 {self.unique_user_id} 的conversation状态")

            # 🔥 清理用户调度器（如果没有其他活跃任务）
            GLOBAL_SCHEDULER_MANAGER.cleanup_user_scheduler(self.username)

            print(f"[_cleanup_unique_user_state] 已完成 {self.unique_user_id} 的所有状态清理")

        except Exception as e:
            print(f"[_cleanup_unique_user_state] 清理状态时出错: {str(e)}")

    def start_automation(self, restart_from_beginning=False):
        """启动自动化任务"""
        if restart_from_beginning:
            # 强制从头开始：清除所有相关的任务状态
            AutomationTask.objects.filter(
                notebook_id=self.notebook_id,
                target_file=self.target_file
            ).delete()
            print("[强制从头开始] 已清除所有相关任务状态")

        # 🔥 检查是否有未完成的任务可以恢复
        existing_task = AutomationTask.objects.filter(
            notebook_id=self.notebook_id,
            target_file=self.target_file,
            status__in=['failed', 'running']
        ).order_by('-created_at').first()

        if existing_task and existing_task.status == 'failed' and existing_task.current_step > 0 and not restart_from_beginning:
            # 恢复现有任务
            self.task = existing_task
            self.task.status = 'running'
            self.task.error_message = ''
            self.task.save()

            # 恢复执行状态
            self._restore_execution_state()
            print(f"[恢复任务] 从第 {self.task.current_step} 步开始继续执行")
        else:
            # 创建新任务记录
            self.task = AutomationTask.objects.create(
                notebook_id=self.notebook_id,
                target_file=self.target_file,
                status='running'
            )

        # 将自己加入全局映射
        RUNNING_TASKS[self.task.id] = self

        # 在新线程中执行
        thread = threading.Thread(target=self._run_automation)
        thread.daemon = True
        thread.start()

        return self.task.id

    def _run_automation(self):
        """执行自动化流程"""
        try:
            # # 获取操作记录
            # records = AutomationRecord.objects.filter(
            #     notebook_id=self.notebook_id
            # ).order_by('step_number')

            # 获取录制批次：NK2026 按 target_file 主题取最近一次；其它场景取全局最新 times
            from app_chat.automation_nk2026 import is_nk2026_ladder_scene, latest_times_for_theme

            if is_nk2026_ladder_scene(getattr(self, "scene_name", None)):
                max_times = latest_times_for_theme(self.notebook_id, self.target_file)
            else:
                max_times = AutomationRecord.objects.filter(
                    notebook_id=self.notebook_id
                ).aggregate(Max('times'))['times__max']

            self._resolved_record_times = max_times

            if max_times is None:
                raise Exception("没有找到操作记录")

            # 获取最新批次的记录
            records = AutomationRecord.objects.filter(
                notebook_id=self.notebook_id,
                times=max_times
            ).order_by('step_number')

            # 先分析卡片选择模式
            self._analyze_card_selection_pattern(records)

            self.task.total_steps = records.count()
            self.task.save()

            self._seed_automation_prompt_slot()

            # 🔥 支持从中断处继续：跳过已完成的步骤
            start_step = self.task.current_step
            for record in records:
                if record.step_number < start_step:
                    print(f"[跳过步骤] 第 {record.step_number} 步已完成，跳过")
                    continue

                # 🔥 增强停止检查：每个步骤开始前都检查
                self.task.refresh_from_db()
                if self.task.status == 'failed' and self.task.error_message == '手动终止':
                    print(f"[主循环] 任务 {self.task.id} 被手动终止")
                    break

                if self.stop_flag:
                    print(f"[主循环] 检测到stop_flag，停止执行")
                    break

                # 🔥 新增：获取用户调度器执行槽位，实现单用户并发均衡
                user_scheduler = GLOBAL_SCHEDULER_MANAGER.get_user_scheduler(self.username)
                user_scheduler.acquire_step_slot(self.task.id)

                try:
                    # 更新进度
                    self.task.current_step = record.step_number
                    self.task.save()

                    # 🔥 简化超时机制：记录开始时间
                    print(f"[主循环] 开始执行第 {record.step_number} 步: {record.action_type}")
                    self.step_start_time = time.time()
                    success = self._execute_action(record)

                    # 🔥 执行操作后再次检查停止状态
                    self.task.refresh_from_db()
                    if self.task.status == 'failed' and self.task.error_message == '手动终止':
                        print(f"[主循环] 操作后检测到任务被手动终止")
                        break

                    if not success:
                        print(f"[主循环] 第 {record.step_number} 步执行失败，准备重试")
                        # 重试前检查停止状态
                        self.task.refresh_from_db()
                        if self.task.status == 'failed' and self.task.error_message == '手动终止':
                            print(f"[主循环] 重试前检测到任务被手动终止")
                            break

                        # 在重试延迟期间也检查手动中止状态
                        for i in range(4):  # 4秒分割为4个1秒检查点
                            time.sleep(1.0)
                            self.task.refresh_from_db()
                            if self.task.status == 'failed' and self.task.error_message == '手动终止':
                                print(f"[主循环] 重试延迟期间检测到任务被手动终止")
                                return  # 直接退出方法

                        # 🔥 重试时重新记录开始时间
                        self.step_start_time = time.time()
                        success = self._execute_action(record)

                        if not success:
                            raise Exception(f"操作失败：{record.action_type}")

                    # 🔥 每完成一个步骤保存执行状态
                    self._save_execution_state()

                    # 适当延迟，模拟人工操作（期间也检查停止状态）
                    for i in range(4):  # 分割4秒延迟为4个1秒检查点
                        time.sleep(1.0)
                        self.task.refresh_from_db()
                        if self.task.status == 'failed' and self.task.error_message == '手动终止':
                            print(f"[主循环] 延迟期间检测到任务被手动终止")
                            return  # 直接退出方法

                finally:
                    # 🔥 无论如何都要释放用户调度器槽位
                    user_scheduler.release_step_slot(self.task.id)

            # self.task.status = 'success'
            # self.task.save()
            # 完成后再次检查状态
            self.task.refresh_from_db()
            if self.task.status != 'failed':
                self.task.status = 'success'
                self.task.save()

        except Exception as e:
            self.task.status = 'failed'
            if self.task.error_message != '手动终止':  # 保留特殊的终止信息
                self.task.error_message = str(e)
            self.task.save()

        finally:
            # 从全局映射中移除
            if self.task.id in RUNNING_TASKS:
                del RUNNING_TASKS[self.task.id]

            # 🔥 清理唯一用户ID的状态数据，避免内存泄漏
            self._cleanup_unique_user_state()

    def _is_step_timeout(self):
        """检查当前步骤是否超时"""
        if self.step_start_time is None:
            return False

        elapsed_time = time.time() - self.step_start_time
        if elapsed_time > self.step_timeout_seconds:
            print(f"[超时检查] 步骤执行超时，已用时: {elapsed_time:.1f}秒 (限制: {self.step_timeout_seconds}秒)")
            return True
        return False

    def _execute_action(self, record):
        """执行单个操作"""
        try:
            # 🔥 在操作开始前就检查停止状态
            self.task.refresh_from_db()
            if self.task.status == 'failed' and self.task.error_message == '手动终止':
                print(f"[_execute_action] 任务 {self.task.id} 被手动终止，停止执行")
                return False

            if self.stop_flag:
                print(f"[_execute_action] 检测到stop_flag，停止执行")
                return False

            action_data = record.action_data

            if record.action_type == 'select_file':
                # 文件选择操作（主要用于记录）
                return True

            elif record.action_type == 'get_file_summary':
                # 获取文档摘要和主题
                return self._get_file_summary(action_data)

            elif record.action_type == 'topic_click':
                # 点击topic获取相关问题
                return self._handle_topic_click(action_data)

            elif record.action_type == 'send_message':
                # 发送消息
                return self._send_message(action_data)

            elif record.action_type == 'create_card':
                # 创建卡片
                return self._create_card(action_data)

            elif record.action_type == 'click_question':
                # 点击导问
                return self._click_question(action_data)

            elif record.action_type == 'enhance_question':
                # 增强导问
                return self._enhance_question(action_data)

            elif record.action_type == 'card_operation':
                # 卡片操作（融合、总结等）
                return self._card_operation(action_data)

            elif record.action_type == 'select_cards':
                # 勾选卡片
                return self._select_cards(action_data)

            elif record.action_type == 'change_subscene':
                # 切换子场景
                return self._change_subscene(action_data)

            elif record.action_type == 'direct_card':
                # 直接生成卡片
                return self._create_direct_card(action_data)

            elif record.action_type == 'wait':
                # 等待操作，期间检查超时
                wait_seconds = action_data.get('seconds', 5)
                wait_start = time.time()

                while time.time() - wait_start < wait_seconds:
                    if self._is_step_timeout():
                        print(f"[等待操作] 等待期间检测到超时")
                        return False

                    self.task.refresh_from_db()
                    if self.task.status == 'failed' and self.task.error_message == '手动终止':
                        print(f"[等待操作] 等待期间检测到手动终止")
                        return False

                    time.sleep(0.5)  # 每0.5秒检查一次

                return True

            else:
                print(f"未知操作类型: {record.action_type}")
                return True

        except Exception as e:
            print(f"执行操作失败: {record.action_type}, 错误: {str(e)}")
            return False

    def _get_file_summary(self, action_data):
        """获取文档摘要 - 优化版本"""
        try:
            # 🆕 使用统一的文件列表处理逻辑
            processed_file_list = self._prepare_file_list(action_data)

            # 构造请求数据
            left_list, right_list = self._resolve_select_lists(action_data, processed_file_list)

            request_data_summary = {
                'username': self.notebook_id,  # 📝 文件操作保持使用原始用户ID确保数据兼容性
                'filename': self.target_file,  # 使用新的目标文件
                # 'fileNameList': ','.join([self.target_file] + action_data.get('otherFiles', [])),
                'fileNameList': ','.join(processed_file_list),  # 使用处理后的文件列表
                'leftSelectList': ','.join(map(str, left_list)),
                'rightSelectList': ','.join(map(str, right_list))
                # 'leftSelectList': ','.join(map(str, action_data.get('leftSelectList', [1]))),
                # 'rightSelectList': ','.join(map(str, action_data.get('rightSelectList', [3])))
            }

            # 🔥 检查超时
            if self._is_step_timeout():
                print(f"[_get_file_summary] 获取文档摘要前检测到超时")
                return False

            # 调用后端函数
            resultSummary = self._call_backend_function(views.card_getFileByName, request_data_summary)

            if resultSummary.get('error_num') == 0:
                # 🔥 准备并发任务
                async def concurrent_operations():
                    tasks = []

                    # 1. 创建卡片任务
                    request_data = {
                        'username': self.notebook_id,  # 📝 卡片创建保持使用原始用户ID确保数据归属正确
                        'content': resultSummary.get('content'),
                        'sceneName': action_data.get('sceneName', ''),
                        'subSceneName': action_data.get('subSceneName', ''),
                        'keyTopics': json.dumps(action_data.get('keyTopics', []))
                    }
                    tasks.append(self._call_backend_function_async(views.add_card_directly, request_data))

                    # 2. 红蓝评测任务（不依赖卡片创建）
                    request_data_HL = {
                        'username': self.notebook_id,  # 📝 红蓝评测保持使用原始用户ID确保数据归属正确
                        'text': self._replace_names(action_data.get('content', ''))
                    }
                    tasks.append(self._call_backend_function_async(views.execute_commands, request_data_HL))

                    # 并发执行
                    return await asyncio.gather(*tasks, return_exceptions=True)

                # 执行并发操作
                loop = asyncio.new_event_loop()
                results = loop.run_until_complete(concurrent_operations())
                loop.close()

                # 处理结果
                result = results[0] if not isinstance(results[0], Exception) else {'error_num': 1}
                result_HL = results[1] if not isinstance(results[1], Exception) else {'error_num': 1}

                if result.get('error_num') == 0:
                    card_id = result.get('cardId')
                    self.created_card_ids.append(card_id)

                    # 自动打分（异步执行，不等待结果）
                    score_data = {
                        'username': self.notebook_id,
                        'content': resultSummary.get('content'),
                        'cid': card_id
                    }
                    # 在后台执行打分，不阻塞主流程
                    asyncio.run(self._call_backend_function_async(views.card_score, score_data))

                    # 处理红蓝评测结果
                    if result_HL.get('error_num') == 0:
                        try:
                            # 获取并处理数据
                            data_str = result_HL.get('data', '').strip()
                            print(f"红蓝测试结果1: {data_str}, 长度: {len(data_str)}")

                            # 去掉首尾引号
                            if data_str.startswith('"') and data_str.endswith('"'):
                                data_str = data_str[1:-1]
                            print(f"处理1：{data_str}, 长度: {len(data_str)}")

                            # 替换转义字符
                            data_str = data_str.replace('\\"', '"').replace('\\\\', '\\')
                            print(f"处理2：{data_str}, 长度: {len(data_str)}")

                            # 解析JSON
                            result_object = json.loads(data_str)
                            decoded_result = self._decode_result(result_object.get('result', ''))
                            print(f"红蓝测试结果2：{decoded_result}")

                            # 保存红蓝评测结果
                            if decoded_result and decoded_result != "fail":
                                eval_data = {
                                    'content': decoded_result,
                                    'cid': str(card_id)
                                }
                                eval_result = self._call_backend_function(views.card_evalSFT, eval_data)

                                if eval_result.get('error_num') == 0:
                                    print(f"卡片 {card_id} 红蓝评测保存成功")
                                    return True
                                else:
                                    print(f"卡片 {card_id} 红蓝评测保存失败")
                                    # 卡片已创建，评测失败不影响整体流程
                                    return True
                            else:
                                print("红蓝评测结果为fail")
                                # 卡片已创建，评测失败不影响整体流程
                                return True

                        except Exception as e:
                            print(f"处理红蓝评测结果失败: {str(e)}")
                            # 卡片已创建，评测失败不影响整体流程
                            return True
                    else:
                        print(f"红蓝评测执行失败: {result_HL}")
                        # 卡片已创建，评测失败不影响整体流程
                        return True

                return False

            return False

        except Exception as e:
            print(f"获取文档摘要失败: {str(e)}")
            print(f"[_get_file_summary] 错误类型: {type(e).__name__}")
            print(f"[_get_file_summary] 详细错误栈:\n{traceback.format_exc()}")
            return False

    def _handle_topic_click(self, action_data):
        """处理topic点击"""
        try:
            request_data = {
                'username': self.notebook_id,
                'topicRelText': action_data.get('topicRelText', ''),
                'topicClicked': action_data.get('topicClicked', '')
            }

            result = self._call_backend_function(views.topic_getRelQuestions, request_data)
            return result.get('error_num') == 0

        except Exception as e:
            print(f"处理topic失败: {str(e)}")
            print(f"[_handle_topic_click] 错误类型: {type(e).__name__}")
            print(f"[_handle_topic_click] 详细错误栈:\n{traceback.format_exc()}")
            return False

    def _send_message(self, action_data):
        """发送消息"""
        try:
            # 🔥 新增：发送消息前检查是否需要停止
            self.task.refresh_from_db()
            if self.task.status == 'failed' and self.task.error_message == '手动终止':
                print(f"[_send_message] 任务 {self.task.id} 被终止，停止发送消息")
                return False

            # 替换消息中的人名（保存原始消息供后续使用）
            original_message = self._replace_names(action_data['message'])
            message = original_message

            # 准备文件列表 - 使用新的目标文件
            file_list = self._prepare_file_list(action_data)

            # 处理勾选的卡片列表
            chosen_card_ids = self._get_current_card_ids(action_data)

            # 🔥 如果有选择的卡片，先获取卡片内容并拼接到消息中
            if chosen_card_ids:
                cards_data = {
                    'username': self.notebook_id,
                    'choosedCardIdList': ','.join(map(str, chosen_card_ids))
                }
                cards_result = self._call_backend_function(views.getCardsContentByIds, cards_data)

                if cards_result.get('error_num') == 0:
                    cards_content = cards_result.get('content', '')
                    # 按照前端逻辑拼接：卡片内容 + 提示文本 + 用户输入
                    message = cards_content + "上面的重要素材文本是你完成下面的问题或请求需要参考的重点内容，也可能含有待修改的目标内容，请你回答：\n" + message
                    print(f"[_send_message] 已拼接卡片内容，最终消息长度: {len(message)}")
                else:
                    print(f"[_send_message] 获取卡片内容失败: {cards_result}")
            else:
                print(f"[_send_message] 没有选择的卡片，直接使用原始消息")

            # 提前执行 RAG：仅在为「智慧激发」小模型准备摘录时需要（默认关闭则跳过，与录制一致且省一次检索）
            all_segments = None
            left_list, right_list = self._resolve_select_lists(action_data, file_list)

            _depth_on = AUTOMATION_DEPTH_SUGGESTION_ENABLED
            if file_list and _depth_on:
                try:
                    from llm_langchain import util
                    print(f"[_send_message] 提前执行RAG检索（智慧激发已开启），文件数: {len(file_list)}")
                    all_segments = util.get_docs_all_split(
                        user_name=self.notebook_id,
                        docs_name_list=file_list,
                        segment_get_way_list=right_list,
                        text_for_search=message
                    )
                    print(f"[_send_message] RAG检索完成，获取到{len(all_segments)}个文档的片段")
                except Exception as e:
                    print(f"[_send_message] RAG检索失败: {e}，继续执行")
                    import traceback
                    traceback.print_exc()

            # 小模型「智慧激发」深度建议：由 AUTOMATION_DEPTH_SUGGESTION_ENABLED 控制，默认关
            if _depth_on:
                depth_suggestion = ""
                try:
                    depth_suggestion = self._get_automation_depth_suggestion(message, file_list, all_segments)
                    if depth_suggestion:
                        print(f"[_send_message] 深度建议获取成功，长度: {len(depth_suggestion)}")
                        message = (
                            f"【智慧激发框架】（深度建议，供你生成回答时作为重要参考）：\n"
                            f"{depth_suggestion}\n\n【用户问题】\n{message}"
                        )
                    else:
                        print(f"[_send_message] 深度建议获取失败或为空，直接回答")
                except Exception as e:
                    print(f"[_send_message] 深度建议获取异常: {e}，直接回答")

            # NK2026 Gxx.md 注入见 views.construct_data / core.construct.construct_data（流式请求须带 sceneName、filenamelist；自动化已追加 target_file）

            # 获取模型参数
            # model_id = action_data.get('modelId', '1002')
            # 调整增强：获取正确的模型参数 - 查找后续create_card步骤的modelId
            current_step = getattr(self.task, 'current_step', 0)
            model_id = self._get_actual_model_id(current_step, action_data.get('modelId', '1002'))
            print(f"尝试获取实际模型ID: {model_id}")

            # 第一步：先调用 chat_sendParams 设置参数
            from app_chat.views import config_manager, model_manager
            params_dict = {}
            model_names = model_manager.get_all_model_names()
            for model_name in model_names:
                model_config = config_manager.get_model_config(model_name)
                if model_config:
                    hyper_para = model_config.get_hyper_para()
                    if hyper_para:
                        params_dict[model_name] = hyper_para.to_dict()

            # left_list, right_list = adjust_lists_to_match(
            #     file_list,
            #     action_data.get('leftSelectList', [1]),
            #     action_data.get('rightSelectList', [3])
            # )

            params_data = {
                'username': self.notebook_id,  # 保持原始用户名用于数据存储获取
                'originRealName': self.unique_user_id,  # 与 setNewSubExcel / construct_data 共用 prompt 槽，使用唯一用户ID，群组本多用户隔离/自动化不同目标文档隔离本质上是一样的
                'modelID': model_id,
                'windowId': 'left',  # 默认使用左窗口
                'params': json.dumps(params_dict),
                'message': message,
                'filenamelist': ','.join(file_list),
                'rightSelectList': ','.join(map(str, right_list)),
                # 'rightSelectList': ','.join(map(str, action_data.get('rightSelectList', [3]))),
                'isHistoryUsed': str(action_data.get('isHistoryUsed', True)).lower(),
                # 'isHistoryUsed': str(False).lower(),
                'rounds': str(action_data.get('rounds', 3)),
                'choosedCardIdList': ','.join(map(str, chosen_card_ids)),
                'mode': 'normal'  # 🔥 添加mode字段，避免KeyError
            }
            params_result = self._call_backend_function(views.chat_sendParams, params_data)
            print(f"[_send_message] chat_sendParams 结果: {params_result}")

            if params_result.get('error_num') != 0:
                print(f"[_send_message] chat_sendParams 失败: {params_result}")
                return False

            # 构造请求数据
            request_data = {
                'username': self.notebook_id,  # 保持原始用户名用于数据存储
                'originRealName': self.unique_user_id,  # construct_data 经 resolve 读同槽 prompt，使用唯一用户ID，群组本多用户隔离/自动化不同目标文档隔离本质上是一样的
                'model_id': model_id,
                'message': message,
                'filenamelist': file_list,
                'summary': action_data.get('summary', 'false'),
                'leftSelectList': left_list,
                'rightSelectList': right_list,
                # 'leftSelectList': action_data.get('leftSelectList', [1]),
                # 'rightSelectList': action_data.get('rightSelectList', [3]),
                'choosedCardIdList': chosen_card_ids,
                'isHistoryUsed': str(action_data.get('isHistoryUsed', True)).lower(),
                # 'isHistoryUsed': str(False).lower(),
                'isSummaryUsed': str(action_data.get('isSummaryUsed', False)).lower(),
                'rounds': str(action_data.get('rounds', 3)),
                'sceneName': action_data.get('sceneName', ''),
                'subSceneName': action_data.get('subSceneName', ''),
                'target_file': getattr(self, 'target_file', None) or '',
                'modelStates': json.dumps(action_data.get('modelStates', {})),
                'realName': self.username,
                'userbookName': self.notebook_id,
                'seed': '0'
            }

            # 转换为FormData格式
            form_data = self._create_form_data(request_data)

            # 🔥 检查超时
            if self._is_step_timeout():
                print(f"[_send_message] 执行流式调用前检测到超时")
                return False

            # 执行流式调用（带重试）
            full_response = self._execute_stream_call(form_data)

            # 保存问答内容供后续使用（记录原始用户输入，不包含卡片内容）
            self.last_qa_content = {
                'question': original_message,
                'answer': full_response,
                'model_id': model_id
            }

            model_name = config_manager.get_model_name_by_id(model_id)

            from app_chat.views import chat_content
            # 流式写入 chat_content 的顶层键与 construct_data 的 user_name 一致，即 originRealName（unique_user_id）
            cc_user = self.unique_user_id
            cc_bucket = chat_content.get(cc_user) or {}
            if model_name in cc_bucket:
                print(f'[DEBUG:_send_message] Updating interaction for {cc_user} with model {model_name}')
                GLOBAL_STATE.conversation_manager.add_interaction(
                    username=cc_user,
                    model_name=model_name,
                    question=original_message,
                    response=cc_bucket[model_name],
                )
                GLOBAL_STATE.conversation_manager.update_file_list(
                    username=cc_user,
                    model_name=model_name,
                    file_list=file_list,
                )
            else:
                print(
                    f'[Warn] {model_name} not in chat_content[{cc_user}] '
                    f'(keys: {list(cc_bucket.keys())[:12]}…), using streamed answer for history'
                )
                if full_response:
                    GLOBAL_STATE.conversation_manager.add_interaction(
                        username=cc_user,
                        model_name=model_name,
                        question=original_message,
                        response=full_response,
                    )
                    GLOBAL_STATE.conversation_manager.update_file_list(
                        username=cc_user,
                        model_name=model_name,
                        file_list=file_list,
                    )

            # 如果有响应内容，认为成功
            return len(full_response) > 0

        except Exception as e:
            print(f"[_send_message] 发送消息失败: {str(e)}")
            print(f"[_send_message] 错误类型: {type(e).__name__}")
            print(f"[_send_message] 详细错误栈:\n{traceback.format_exc()}")

            # 打印更多调试信息
            print(f"[_send_message] notebook_id: {self.notebook_id}")
            print(f"[_send_message] unique_user_id: {self.unique_user_id}")
            print(f"[_send_message] target_file: {self.target_file}")
            print(f"[_send_message] username: {self.username}")
            return False

    def _get_actual_model_id(self, current_step, default_model_id):
        """获取实际用于创建卡片的模型ID"""
        try:
            # 获取当前批次的最大times
            max_times = AutomationRecord.objects.filter(
                notebook_id=self.notebook_id
            ).aggregate(Max('times'))['times__max']

            if not max_times:
                return default_model_id

            # 查找当前步骤之后的第一个create_card步骤
            next_create_card = AutomationRecord.objects.filter(
                notebook_id=self.notebook_id,
                times=max_times,
                step_number__gt=current_step,  # 大于当前步骤
                action_type='create_card'
            ).order_by('step_number').first()

            if next_create_card:
                # 返回create_card步骤使用的modelId
                return next_create_card.action_data.get('modelId', default_model_id)
            else:
                # 如果没有后续的create_card步骤，使用默认值
                return default_model_id

        except Exception as e:
            print(f"获取实际模型ID失败: {str(e)}")
            return default_model_id

    def _execute_stream_call(self, form_data, retry_count=0):
        """执行流式调用，带重试逻辑"""
        max_retries = 1  # 最多重试1次

        # 🔥 新增：调用前检查是否需要停止
        self.task.refresh_from_db()
        if self.task.status == 'failed' and self.task.error_message == '手动终止':
            print(f"[_execute_stream_call] 任务 {self.task.id} 被终止，停止流式调用")
            return ""

        # 🔥 检查超时
        if self._is_step_timeout():
            print(f"[_execute_stream_call] 流式调用开始前检测到超时")
            return ""

        # 调用实际的聊天函数
        print(f"[_execute_stream_call] 准备调用 stream_generator_sync (尝试 {retry_count + 1}/{max_retries + 1})")
        response = views.stream_generator_sync(form_data)
        print("[_execute_stream_call] stream_generator_sync 调用成功")

        # 收集完整响应
        full_response = ""
        for chunk in response:
            # 🔥 新增：处理每个chunk时检查是否需要停止
            self.task.refresh_from_db()
            if self.task.status == 'failed' and self.task.error_message == '手动终止':
                print(f"[_execute_stream_call] 任务 {self.task.id} 被终止，停止处理流式响应")
                return full_response  # 返回已接收的部分响应

            # 🔥 新增：检查是否超时
            if self._is_step_timeout():
                print(f"[_execute_stream_call] 检测到超时，停止处理流式响应")
                return full_response  # 返回已接收的部分响应

            try:
                chunk_data = json.loads(chunk)
                if 'content' in chunk_data:
                    full_response += chunk_data['content']
            except Exception as chunk_error:
                print(f"[_execute_stream_call] 处理chunk失败: {chunk_error}")
                print(f"[_execute_stream_call] 原始chunk: {chunk}")
                continue

        # 检查是否需要重试
        # 🔥 清理回答末尾的API错误信息（完整回答后的错误不应重试，只需清理）
        import re
        api_error_patterns = [
            r'claude-[^\s]+ API调用出错$',
            r'gemini-[^\s]+ API调用出错$',
            r'gpt-[^\s]+ API调用出错$',
            r'deepseek-[^\s]+ API调用出错$',
            r'kimi API调用出错$',
            r'API调用出错$'
        ]

        cleaned_response = full_response
        for pattern in api_error_patterns:
            cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.MULTILINE)

        # 如果清理后内容变化，说明末尾有API错误
        if cleaned_response != full_response:
            print(f"[_execute_stream_call] 清理了末尾的API错误信息")
            full_response = cleaned_response.rstrip()

        # 🔥 检查是否需要重试（扩展错误关键词）
        error_keywords = [
            "出错，参考文档内容偏多，或服务器繁忙",
            "调用超时",
            "API调用出错",
            "接口调用失败",
            "服务异常"
        ]

        # 检查是否为无效回答（只有错误信息或太短）
        stripped_response = full_response.strip()
        is_error_only = any(keyword in stripped_response for keyword in error_keywords)
        is_too_short = len(stripped_response) < 50  # 少于50字认为太短

        # 🔥 重试条件：
        # 1. 只有错误信息（无有效内容）
        # 2. 内容太短且包含错误关键词
        should_retry = retry_count < max_retries and (
                (is_error_only and is_too_short) or  # 纯错误或几乎纯错误
                (is_too_short and any(
                    kw in stripped_response for kw in ["API调用出错", "调用超时", "服务异常", "出错，参考文档内容偏多，或服务器繁忙"]))
        )

        if should_retry:
            print(f"[_execute_stream_call] 检测到无效响应（长度{len(stripped_response)}），准备重试: {full_response[:100]}...")
            time.sleep(3)  # 等待3秒后重试
            return self._execute_stream_call(form_data, retry_count + 1)

        return full_response

    def _decode_result(self, result):
        """解码红蓝评测结果 - 将Unicode转义序列转为中文字符"""
        try:
            # 使用正则表达式匹配 \uXXXX 格式的Unicode转义序列
            def unicode_replacer(match):
                # 获取16进制数字部分
                hex_str = match.group(1)
                # 转换为对应的字符
                return chr(int(hex_str, 16))

            # 替换所有 \uXXXX 格式的转义序列
            decoded_string = re.sub(r'\\u([\da-fA-F]{4})', unicode_replacer, result)

            return decoded_string

        except Exception as e:
            print(f"解码结果失败: {str(e)}")
            return "fail"

    def _create_card(self, action_data):
        """创建卡片 - 优化版本"""
        try:
            # 优先使用最近的问答内容
            if self.last_qa_content:
                qa_content = f"提问：{self.last_qa_content['question']}\n回答：{self.last_qa_content['answer']}"
                model_id = self.last_qa_content['model_id']
            else:
                # 降级使用记录的内容
                qa_content = action_data.get('content', '')
                model_id = action_data.get('modelId', '1002')

            # 实时获取keyTopics（调用AI生成）
            key_topics = self._generate_key_topics(qa_content, action_data.get('keyTopics', []))

            # 🔥 获取当前应该勾选的卡片ID列表（如果问答时有勾选卡片）
            chosen_card_ids = self._get_current_card_ids(action_data)
            file_list = self._prepare_file_list(action_data)

            request_data = {
                'username': self.notebook_id,  # 🔥 卡片创建时使用原始用户名，确保数据归属正确
                # 'originRealName': self.notebook_id,
                'originRealName': self.rag_chat_user_id,  # 🔥 使用当前操作用户作为writer
                'datetime': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                'model_id': str(model_id),
                'content': qa_content,
                'status': action_data.get('status', 'false'),
                'seed': str(action_data.get('seed', 0)),
                'sceneName': action_data.get('sceneName', ''),
                'subSceneName': action_data.get('subSceneName', ''),
                'keyTopics': json.dumps(action_data.get('keyTopics', [])),
                'timeParams': json.dumps(action_data.get('timeParams', {})),
                'file_list': file_list,
            }

            # 🔥 如果有勾选的卡片，将卡片ID列表传递给card_upload，用于设置新卡片的postIndex
            if chosen_card_ids and len(chosen_card_ids) > 0:
                request_data['choosedCardIdList'] = json.dumps(chosen_card_ids)
                print(f"[AutomationEngine._create_card] 设置新卡片的postIndex: {chosen_card_ids}")

            result = self._call_backend_function(views.card_upload, request_data)

            if result.get('error_num') == 0:
                card_id = result.get('card_id')
                self.created_card_ids.append(card_id)

                if self._is_nk2026():
                    try:
                        from app_chat.automation_nk2026 import nk2026_apply_automation_card_title
                        nk2026_apply_automation_card_title(
                            card_id,
                            file_list,
                            action_data.get('sceneName', '') or getattr(self, 'scene_name', ''),
                            existing_content_title='',
                        )
                    except Exception as nk_title_e:
                        print(f"[AutomationEngine._create_card] NK2026 标题矫正失败: {nk_title_e}")

                # 记录当前步骤创建的卡片
                current_step = getattr(self.task, 'current_step', 0)
                if current_step not in self.step_card_mapping:
                    self.step_card_mapping[current_step] = []
                self.step_card_mapping[current_step].append(card_id)

                # 🔥 并发执行打分和红蓝评测
                async def score_and_evaluate():
                    tasks = []

                    # 1. 打分任务
                    score_data = {
                        'username': self.notebook_id,
                        'content': qa_content,
                        'cid': card_id
                    }
                    tasks.append(self._call_backend_function_async(views.card_score, score_data))

                    # 2. 红蓝评测任务
                    request_data_HL = {
                        'username': self.notebook_id,
                        'text': qa_content
                    }
                    tasks.append(self._call_backend_function_async(views.execute_commands, request_data_HL))

                    # 并发执行
                    return await asyncio.gather(*tasks, return_exceptions=True)

                # 🔥 检查超时
                if self._is_step_timeout():
                    print(f"[_create_card] 打分和红蓝评测前检测到超时")
                    return True  # 卡片已创建，返回成功

                # 执行并发操作
                loop = asyncio.new_event_loop()
                results = loop.run_until_complete(score_and_evaluate())
                loop.close()

                score_result = results[0] if not isinstance(results[0], Exception) else {'error_num': 1}
                result_HL = results[1] if not isinstance(results[1], Exception) else {'error_num': 1}

                # 处理红蓝评测结果
                if result_HL.get('error_num') == 0:
                    try:
                        # 获取并处理数据
                        data_str = result_HL.get('data', '').strip()
                        print(f"红蓝测试结果1: {data_str}, 长度: {len(data_str)}")

                        # 去掉首尾引号
                        if data_str.startswith('"') and data_str.endswith('"'):
                            data_str = data_str[1:-1]
                        print(f"处理1：{data_str}, 长度: {len(data_str)}")

                        # 替换转义字符
                        data_str = data_str.replace('\\"', '"').replace('\\\\', '\\')
                        print(f"处理2：{data_str}, 长度: {len(data_str)}")

                        # 解析JSON
                        result_object = json.loads(data_str)
                        decoded_result = self._decode_result(result_object.get('result', ''))
                        print(f"红蓝测试结果2：{decoded_result}")

                        # 保存红蓝评测结果
                        if decoded_result and decoded_result != "fail":
                            eval_data = {
                                'content': decoded_result,
                                'cid': str(card_id)
                            }
                            eval_result = self._call_backend_function(views.card_evalSFT, eval_data)

                            if eval_result.get('error_num') == 0:
                                print(f"卡片 {card_id} 红蓝评测保存成功")
                            else:
                                print(f"卡片 {card_id} 红蓝评测保存失败")
                        else:
                            print("红蓝评测结果为fail")

                    except Exception as e:
                        print(f"处理红蓝评测结果失败: {str(e)}")
                else:
                    print(f"红蓝评测执行失败: {result_HL}")

                # 清空最近的问答内容
                self.last_qa_content = {}

                # 只要卡片创建成功就返回True
                return score_result.get('error_num') == 0

            return False

        except Exception as e:
            print(f"创建卡片失败: {str(e)}")
            print(f"[_create_card] 错误类型: {type(e).__name__}")
            print(f"[_create_card] 详细错误栈:\n{traceback.format_exc()}")
            return False

    def _click_question(self, action_data):
        """点击导问"""
        try:
            # 准备完整的 action_data
            file_list = self._prepare_file_list(action_data)  # 使用新的目标文件
            left_list, right_list = self._resolve_select_lists(action_data, file_list)

            new_action_data = {
                'message': action_data.get('question', ''),
                # 'fileNameList': self._prepare_file_list(action_data),
                # 'leftSelectList': action_data.get('leftSelectList', [1]),
                # 'rightSelectList': action_data.get('rightSelectList', [3]),
                'fileNameList': file_list,
                'leftSelectList': left_list,
                'rightSelectList': right_list,
                'choosedCardIdList': self._get_current_card_ids(action_data),
                'sceneName': action_data.get('sceneName', ''),
                'subSceneName': action_data.get('subSceneName', ''),
                # 添加缺失的字段，使用默认值
                'modelId': '1002',  # 默认使用模型1002: GPT4o
                'isHistoryUsed': True,
                # 'isHistoryUsed': False,
                'isSummaryUsed': False,
                'rounds': 3,
                'modelStates': {},
                'summary': 'false',
                'otherFiles': []  # 其他文件列表
            }

            return self._send_message(new_action_data)

        except Exception as e:
            print(f"点击导问失败: {str(e)}")
            print(f"[_click_question] 错误类型: {type(e).__name__}")
            print(f"[_click_question] 详细错误栈:\n{traceback.format_exc()}")
            return False

    def _enhance_question(self, action_data):
        """增强导问"""
        try:
            request_data = {
                'username': self.notebook_id,  # 📝 问题增强保持使用原始用户ID确保功能正常
                'notebook_name': self.notebook_id.split('_', 1)[1],
                'original_question': action_data.get('original_question', ''),
                'last_question': action_data.get('last_question', ''),
                'card_content': self._get_recent_card_content(),  # 获取最近的卡片内容
                'sceneName': action_data.get('sceneName', ''),
                'subSceneName': action_data.get('subSceneName', '')
            }

            result = self._call_backend_function(views.question_enhance, request_data)

            if result.get('error_num') == 0:
                # 使用增强后的问题发送消息
                enhanced_question = result.get('modified_question', '')

                file_list = self._prepare_file_list(action_data)
                left_list, right_list = self._resolve_select_lists(action_data, file_list)

                # 准备完整的 action_data
                new_action_data = {
                    'message': enhanced_question,
                    # 'fileNameList': self._prepare_file_list(action_data),
                    # 'leftSelectList': action_data.get('leftSelectList', [1]),
                    # 'rightSelectList': action_data.get('rightSelectList', [3]),
                    'fileNameList': file_list,
                    'leftSelectList': left_list,
                    'rightSelectList': right_list,
                    'choosedCardIdList': self._get_current_card_ids(action_data),
                    'sceneName': action_data.get('sceneName', ''),
                    'subSceneName': action_data.get('subSceneName', ''),
                    # 添加缺失的字段，使用默认值
                    'modelId': '1002',  # 默认使用模型1002: GPT4o
                    'isHistoryUsed': True,
                    # 'isHistoryUsed': False,
                    'isSummaryUsed': False,
                    'rounds': 3,
                    'modelStates': {},
                    'summary': 'false',
                    'otherFiles': []
                }

                return self._send_message(new_action_data)

            return False

        except Exception as e:
            print(f"增强导问失败: {str(e)}")
            print(f"[_enhance_question] 错误类型: {type(e).__name__}")
            print(f"[_enhance_question] 详细错误栈:\n{traceback.format_exc()}")
            return False

    def _card_operation(self, action_data):
        """卡片操作（融合、总结等）"""
        from zym import views
        try:
            operation_type = action_data.get('operationType', 'combine')
            card_ids = action_data.get('cardIdList', [])

            # 如果没有指定卡片ID，使用最近创建的卡片
            if not card_ids and self.created_card_ids:
                card_ids = self.created_card_ids[-2:]  # 使用最近的两张卡片

            request_data = {
                'cardIndexList': ','.join(map(str, card_ids)),
                'username': self.notebook_id,
                'datetime': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
                'model_id': '1003',
                'status': '-2',
                'func': self._get_func_code(operation_type),
                'sceneName': action_data.get('sceneName', ''),
                'subSceneName': action_data.get('subSceneName', ''),
                'keyTopics': json.dumps(action_data.get('keyTopics', [])),
                'text': action_data.get('text', '')
            }

            result = self._call_backend_function(views.mergeCardBackend, request_data)

            if result.get('error_num') == 0:
                card_id = result.get('cardId')
                final_content = result.get('finalContent', '')
                self.created_card_ids.append(card_id)

                # 红蓝评测
                if final_content:
                    request_data_HL = {
                        'username': self.notebook_id,  # 📝 红蓝评测保持使用原始用户ID确保数据归属正确
                        'text': final_content
                    }

                    result_HL = self._call_backend_function(app_chat.views.execute_commands, request_data_HL)

                    # 处理红蓝评测结果
                    if result_HL.get('error_num') == 0:
                        try:
                            # 获取并处理数据
                            data_str = result_HL.get('data', '').strip()
                            print(f"红蓝测试结果1: {data_str}, 长度: {len(data_str)}")

                            # 去掉首尾引号
                            if data_str.startswith('"') and data_str.endswith('"'):
                                data_str = data_str[1:-1]
                            print(f"处理1：{data_str}, 长度: {len(data_str)}")

                            # 替换转义字符
                            data_str = data_str.replace('\\"', '"').replace('\\\\', '\\')
                            print(f"处理2：{data_str}, 长度: {len(data_str)}")

                            # 解析JSON
                            result_object = json.loads(data_str)
                            decoded_result = self._decode_result(result_object.get('result', ''))
                            print(f"红蓝测试结果2：{decoded_result}")

                            # 保存红蓝评测结果
                            if decoded_result and decoded_result != "fail":
                                eval_data = {
                                    'content': decoded_result,
                                    'cid': str(card_id)
                                }
                                eval_result = self._call_backend_function(app_chat.views.card_evalSFT, eval_data)

                                if eval_result.get('error_num') == 0:
                                    print(f"卡片 {card_id} 红蓝评测保存成功")
                                else:
                                    print(f"卡片 {card_id} 红蓝评测保存失败")
                            else:
                                print("红蓝评测结果为fail")

                        except Exception as e:
                            print(f"处理红蓝评测结果失败: {str(e)}")
                    else:
                        print(f"红蓝评测执行失败: {result_HL}")

                return True

            return False

        except Exception as e:
            print(f"卡片操作失败: {str(e)}")
            print(f"[_card_operation] 错误类型: {type(e).__name__}")
            print(f"[_card_operation] 详细错误栈:\n{traceback.format_exc()}")
            return False

    def _select_cards(self, action_data):
        """勾选卡片（记录操作）"""
        # 这个操作主要是记录，实际执行时会在后续操作中使用
        return True

    def _change_subscene(self, action_data):
        """切换子场景"""
        from zym import views
        try:
            # 须与 _send_message 的 originRealName 一致（unique_user_id）；
            # construct_data 经 resolve_prompt_storage_key 读同槽，勿再传 promptStorageKey 覆盖到 rag 组键。
            request_data = {
                'username': self.notebook_id,
                'originRealName': self.unique_user_id,
                'sceneName': action_data.get('sceneName', ''),
                'subSceneName': action_data.get('subSceneName', '')
            }

            result = self._call_backend_function(views.setNewSubExcel, request_data)
            return result.get('error_num') == 0

        except Exception as e:
            print(f"切换子场景失败: {str(e)}")
            print(f"[_change_subscene] 错误类型: {type(e).__name__}")
            print(f"[_change_subscene] 详细错误栈:\n{traceback.format_exc()}")
            return False

    def _create_direct_card(self, action_data):
        """直接生成卡片 - 优化版本"""
        try:
            content = self._replace_names(action_data.get('content', ''))

            # 🔥 并发执行创建卡片和红蓝评测
            async def create_and_evaluate():
                tasks = []

                # 1. 创建卡片
                request_data = {
                    'username': self.notebook_id,
                    'content': content,
                    'sceneName': action_data.get('sceneName', ''),
                    'subSceneName': action_data.get('subSceneName', ''),
                    'keyTopics': json.dumps(action_data.get('keyTopics', []))
                }
                tasks.append(self._call_backend_function_async(views.add_card_directly, request_data))

                # 2. 同时进行红蓝评测
                request_data_HL = {
                    'username': self.notebook_id,
                    'text': content
                }
                tasks.append(self._call_backend_function_async(views.execute_commands, request_data_HL))

                # 并发执行
                return await asyncio.gather(*tasks, return_exceptions=True)

            # 执行并发操作
            loop = asyncio.new_event_loop()
            results = loop.run_until_complete(create_and_evaluate())
            loop.close()

            result = results[0] if not isinstance(results[0], Exception) else {'error_num': 1}
            result_HL = results[1] if not isinstance(results[1], Exception) else {'error_num': 1}

            if result.get('error_num') == 0:
                card_id = result.get('cardId')
                self.created_card_ids.append(card_id)

                # 异步自动打分（不等待结果）
                score_data = {
                    'username': self.notebook_id,
                    'content': content,
                    'cid': card_id
                }
                asyncio.run(self._call_backend_function_async(views.card_score, score_data))

                # 处理红蓝评测结果
                if result_HL.get('error_num') == 0:
                    try:
                        # 获取并处理数据
                        data_str = result_HL.get('data', '').strip()
                        print(f"红蓝测试结果1: {data_str}, 长度: {len(data_str)}")

                        # 去掉首尾引号
                        if data_str.startswith('"') and data_str.endswith('"'):
                            data_str = data_str[1:-1]
                        print(f"处理1：{data_str}, 长度: {len(data_str)}")

                        # 替换转义字符
                        data_str = data_str.replace('\\"', '"').replace('\\\\', '\\')
                        print(f"处理2：{data_str}, 长度: {len(data_str)}")

                        # 解析JSON
                        result_object = json.loads(data_str)
                        decoded_result = self._decode_result(result_object.get('result', ''))
                        print(f"红蓝测试结果2：{decoded_result}")

                        # 保存红蓝评测结果
                        if decoded_result and decoded_result != "fail":
                            eval_data = {
                                'content': decoded_result,
                                'cid': str(card_id)
                            }
                            eval_result = self._call_backend_function(views.card_evalSFT, eval_data)

                            if eval_result.get('error_num') == 0:
                                print(f"卡片 {card_id} 红蓝评测保存成功")
                                return True
                            else:
                                print(f"卡片 {card_id} 红蓝评测保存失败")
                                # 卡片已创建，评测失败不影响整体流程
                                return True
                        else:
                            print("红蓝评测结果为fail")
                            # 卡片已创建，评测失败不影响整体流程
                            return True

                    except Exception as e:
                        print(f"处理红蓝评测结果失败: {str(e)}")
                        # 卡片已创建，评测失败不影响整体流程
                        return True
                else:
                    print(f"红蓝评测执行失败: {result_HL}")
                    # 卡片已创建，评测失败不影响整体流程
                    return True

            return False

        except Exception as e:
            print(f"直接生成卡片失败: {str(e)}")
            print(f"[_create_direct_card] 错误类型: {type(e).__name__}")
            print(f"[_create_direct_card] 详细错误栈:\n{traceback.format_exc()}")
            return False

    # 🔥 新增：异步版本的 _call_backend_function
    async def _call_backend_function_async(self, func, data):
        """异步调用后端函数"""
        loop = asyncio.get_event_loop()

        # 在线程池中运行同步函数
        result = await loop.run_in_executor(
            ASYNC_EXECUTOR,
            self._call_backend_function,
            func,
            data
        )
        return result

    def _get_func_code(self, operation_type):
        """获取操作类型对应的功能码"""
        mapping = {
            'summarize': 0,
            'suggest': 1,
            'study_guide': 2,
            'combine': 3,
            'understand': 4,
            'critique': 5,
            'outline': 6,
            'user_define': 10
        }
        return mapping.get(operation_type, 3)

    def _replace_names(self, text):
        """替换文本中的人名等信息"""
        if self._is_nk2026():
            from app_chat.automation_nk2026 import nk2026_replace_names_in_question, parse_target_ladder_meta

            if parse_target_ladder_meta(self.target_file):
                return nk2026_replace_names_in_question(text, self.target_file)

        # 从目标文件名提取学生信息
        student_info = self.target_file.replace('.pdf', '').replace('.docx', '')
        parts = student_info.split('_')

        if len(parts) >= 2:
            student_name = parts[0]
            student_id = parts[1] if len(parts) > 1 else ''

            # 简单替换规则
            replacements = {
                '张三': student_name,
                '学生姓名': student_name,
                '2021000001': student_id,
                '学号': student_id,
                # 可以添加更多替换规则
            }

            for old, new in replacements.items():
                text = text.replace(old, new)

        return text

    def _prepare_file_list(self, action_data):
        """准备文件列表，确保使用新的目标文件并排除旧的目标文件"""
        original_files = action_data.get('fileNameList', [])
        print(f"[_prepare_file_list] 原始文件列表: {original_files}")

        if isinstance(original_files, str):
            original_files = [x.strip() for x in original_files.split(",") if x.strip()]

        # 独立引擎 / 未跑 _run_automation 时补齐 NK2026 录制批次
        if self._is_nk2026() and getattr(self, "_resolved_record_times", None) is None:
            from app_chat.automation_nk2026 import latest_times_for_theme

            self._resolved_record_times = latest_times_for_theme(self.notebook_id, self.target_file)

        # 如果还没有获取原始目标文件，从记录中获取（与当前自动化批次 times 一致）
        if not self.original_target_file:
            max_times = getattr(self, "_resolved_record_times", None)
            if max_times is None:
                max_times = AutomationRecord.objects.filter(
                    notebook_id=self.notebook_id
                ).aggregate(Max('times'))['times__max']

            if max_times:
                first_record = AutomationRecord.objects.filter(
                    notebook_id=self.notebook_id,
                    times=max_times
                ).order_by('step_number').first()

                if first_record:
                    self.original_target_file = first_record.target_file

        if self._is_nk2026():
            return self._prepare_file_list_nk2026(original_files)

        # 构建新的文件列表：替换原始目标文件为新的目标文件
        new_file_list = []
        for f in original_files:
            if f == self.original_target_file:
                # 替换为新的目标文件
                new_file_list.append(self.target_file)
            else:
                # 保留其他文件，但检查是否需要特殊替换
                processed_file = self._process_group_summary_file(f)
                new_file_list.append(processed_file)

        # 如果新目标文件不在列表中，添加它
        if self.target_file not in new_file_list:
            new_file_list.append(self.target_file)

        print(f"[_prepare_file_list] 处理后文件列表: {new_file_list}")
        return new_file_list

    def _prepare_file_list_nk2026(self, original_files):
        from app_chat.automation_nk2026 import (
            list_notebook_filenames,
            nk2026_merge_b_planning_xml_log_file,
            nk2026_merge_incentive_file,
            nk2026_process_8xml_summary_filename,
            nk2026_replace_group_markers_in_filename,
            parse_target_ladder_meta,
            theme_keyword_in_text,
        )

        meta = parse_target_ladder_meta(self.target_file)
        tk = meta["theme_kw"] if meta else theme_keyword_in_text(self.target_file)
        notebook_files = list_notebook_filenames(self.notebook_id)

        new_file_list = []
        for f in original_files:
            if self.original_target_file and f == self.original_target_file:
                new_file_list.append(self.target_file)
                continue
            t = nk2026_process_8xml_summary_filename(f, self.target_file)
            if tk:
                t = nk2026_replace_group_markers_in_filename(t, self.target_file, tk)
            new_file_list.append(t)

        if meta:
            new_file_list = nk2026_merge_incentive_file(new_file_list, notebook_files, meta)
            new_file_list = nk2026_merge_b_planning_xml_log_file(
                new_file_list, notebook_files, meta
            )

        if self.target_file not in new_file_list:
            new_file_list.append(self.target_file)

        print(f"[_prepare_file_list NK2026] 处理后文件列表: {new_file_list}")
        return new_file_list
        # # 始终将目标文件放在首位
        # file_list = [self.target_file]
        #
        # # 添加其他必要的文件（预置文档等）
        # other_files = action_data.get('otherFiles', [])
        # for f in other_files:
        #     if f != self.target_file and f not in file_list:
        #         file_list.append(f)
        #
        # return file_list

    def _process_group_summary_file(self, filename):
        """处理小组整体汇总文件的特殊替换逻辑"""
        import re

        # 检查文件名是否匹配小组整体汇总格式：NK2025-xx#-小组整体汇总
        group_summary_pattern = r'NK2025-(\d+)#-小组整体汇总'
        group_match = re.search(group_summary_pattern, filename)

        if group_match:
            # 检查新目标文件是否包含NK2025-xx#格式
            # target_pattern = r'NK2025-(\d+)#'
            target_pattern = r'(\d+)#'
            target_match = re.search(target_pattern, self.target_file)

            if target_match:
                # 提取新目标文件中的数字
                new_number = target_match.group(1)
                old_number = group_match.group(1)

                # 替换文件名中的数字
                new_filename = filename.replace(f'NK2025-{old_number}#', f'NK2025-{new_number}#')

                print(f"[文件名替换] {filename} -> {new_filename}")
                return new_filename

        # 如果不匹配特殊规则，返回原文件名
        return filename

    @staticmethod
    def _normalize_automation_card_id(cid):
        """统一卡片 ID 类型，便于与录制中的 choosedCardIdList 对比。"""
        if cid is None:
            return None
        if isinstance(cid, str):
            s = cid.strip()
            if s.isdigit():
                return int(s)
            return cid
        return cid

    def _analyze_card_selection_pattern(self, records):
        """
        分析人工流程中的卡片勾选模式：区分
        - 录制流程内 create_card/direct_card 产出卡片（自动化时映射为本轮 step_card_mapping 中的新 cid）
        - 录制前已存在的卡片（自动化时仍使用录制里保存的 cid）
        """
        card_to_step = {}
        flow_created_cards = set()

        for record in records:
            if record.action_type in ("create_card", "direct_card"):
                raw_id = record.action_data.get("created_card_id")
                cid = self._normalize_automation_card_id(raw_id)
                if cid is not None:
                    card_to_step[cid] = record.step_number
                    flow_created_cards.add(cid)

        for record in records:
            if "choosedCardIdList" not in record.action_data:
                continue

            chosen_raw = record.action_data.get("choosedCardIdList", [])
            chosen_cards = []
            if isinstance(chosen_raw, list):
                for c in chosen_raw:
                    if not c:
                        continue
                    nc = self._normalize_automation_card_id(c)
                    if nc is not None:
                        chosen_cards.append(nc)
            elif isinstance(chosen_raw, str) and chosen_raw.strip():
                chosen_cards = [
                    int(x)
                    for x in chosen_raw.split(",")
                    if x.strip() and x.strip().isdigit()
                ]

            if not chosen_cards:
                continue

            flow_created_steps = []
            seen_steps = set()
            existing_cards = []
            for card_id in chosen_cards:
                if card_id in flow_created_cards:
                    cstep = card_to_step[card_id]
                    if cstep not in seen_steps:
                        seen_steps.add(cstep)
                        flow_created_steps.append(cstep)
                else:
                    existing_cards.append(card_id)

            self.card_selection_pattern[record.step_number] = {
                "flow_created_steps": sorted(flow_created_steps),
                "existing_cards": existing_cards,
            }

    def _get_current_card_ids_fallback(self, recorded_card_list):
        """无结构化模式时的兜底（与旧逻辑一致）。"""
        num_cards = len(recorded_card_list)
        if not self.created_card_ids:
            return []
        if len(self.created_card_ids) >= num_cards:
            print(f"警告：使用简化的卡片选择逻辑，选择最近的{num_cards}张卡片")
            return self.created_card_ids[-num_cards:]
        return self.created_card_ids[:]

    def _get_current_card_ids(self, action_data):
        """获取当前应该勾选的卡片ID列表（流程新卡片 + 已有卡片）。"""
        current_step = getattr(self.task, "current_step", 0)
        print("_get_current_card_ids")
        print(current_step)

        recorded_card_list = action_data.get("choosedCardIdList", [])
        if not recorded_card_list:
            return []

        if current_step not in self.card_selection_pattern:
            return self._get_current_card_ids_fallback(recorded_card_list)

        pattern = self.card_selection_pattern[current_step]
        print(self.card_selection_pattern)
        print(self.step_card_mapping)

        selected_cards = []

        # 新格式：与 document_todo 中混合逻辑一致，但不依赖 document_todo 代码
        if isinstance(pattern, dict):
            for step in pattern.get("flow_created_steps", []):
                if step in self.step_card_mapping:
                    selected_cards.extend(self.step_card_mapping[step])
            selected_cards.extend(pattern.get("existing_cards", []))
            return selected_cards

        # 旧格式：仅步骤号列表（历史录制 / 执行状态恢复）
        if isinstance(pattern, list):
            for step in pattern:
                if step in self.step_card_mapping:
                    selected_cards.extend(self.step_card_mapping[step])
            return selected_cards

        return self._get_current_card_ids_fallback(recorded_card_list)

    def _generate_key_topics(self, content, existing_topics):
        """调用AI生成关键词"""
        try:
            # 这里可以调用kimi_api生成关键词
            # 简化处理，暂时返回existing_topics
            return existing_topics
        except:
            return existing_topics

    def _get_recent_card_content(self):
        """获取最近创建的卡片内容"""
        if self.created_card_ids:
            try:
                recent_card = Card.objects.get(cid=self.created_card_ids[-1])
                return recent_card.content
            except:
                pass
        return ""

    def _create_form_data(self, data_dict):
        """将字典转换为类似FormData的格式"""

        class FormDataDict(dict):
            def getlist(self, key):
                value = self.get(key)
                if isinstance(value, list):
                    return value
                return [value] if value is not None else []

        form_data = FormDataDict()
        for key, value in data_dict.items():
            if isinstance(value, list):
                # 对于列表，Django expects comma-separated string
                if key in ['filenamelist']:
                    form_data[key] = ','.join(str(v) for v in value)
                elif key in ['leftSelectList', 'rightSelectList', 'choosedCardIdList']:
                    form_data[key] = ','.join(str(v) for v in value)
                else:
                    form_data[key] = value
            else:
                form_data[key] = str(value) if value is not None else ''

        return form_data

    def _call_backend_function(self, func, data):
        """调用后端函数，带超时控制"""

        # 模拟request对象
        class FakeRequest:
            def __init__(self, data):
                if isinstance(data, dict):
                    self.body = json.dumps(data).encode('utf-8')
                    self.POST = data
                    self.GET = data
                    self.content_type = 'application/json'
                else:
                    # FormData格式
                    self.POST = data
                    self.body = json.dumps(dict(data)).encode('utf-8')
                    self.content_type = 'multipart/form-data'

                self.method = 'POST'
                self.FILES = {}  # 添加 FILES 属性以避免某些视图函数报错

        # 🔥 检查是否已经超时
        if self._is_step_timeout():
            print(f"[_call_backend_function] 调用 {func.__name__} 前检测到超时")
            return {'error_num': 1, 'msg': 'timeout_before_call'}

        fake_request = FakeRequest(data)

        # 🔥 使用简单的线程超时控制（跨平台）
        result_container = [None]
        exception_container = [None]

        def call_function():
            try:
                response = func(fake_request)
                if hasattr(response, 'content'):
                    result_container[0] = json.loads(response.content.decode('utf-8'))
                else:
                    result_container[0] = response
            except Exception as e:
                exception_container[0] = e

        # 计算剩余超时时间
        if self.step_start_time:
            elapsed = time.time() - self.step_start_time
            remaining_time = self.step_timeout_seconds - elapsed
            # 🔥 步骤级超时是4分钟（240秒），给单个backend调用的超时是动态的
            # 只限制最短时间（60秒），不限制最长时间
            # 如果步骤剩余时间很多，就给backend调用充分时间完成embedding等耗时操作
            remaining_timeout = max(60, remaining_time)
        else:
            remaining_timeout = 240  # 默认给整个步骤的时间

        print(f"[_call_backend_function] 调用 {func.__name__}，剩余超时时间: {remaining_timeout:.1f}秒")

        # 启动函数调用线程
        call_thread = threading.Thread(target=call_function, daemon=True)
        call_thread.start()

        # 等待函数完成或超时
        call_thread.join(timeout=remaining_timeout)

        if call_thread.is_alive():
            # 函数调用超时
            print(f"[_call_backend_function] {func.__name__} 调用超时 ({remaining_timeout:.1f}秒)")
            return {'error_num': 1, 'msg': 'timeout_during_call'}

        if exception_container[0]:
            # 函数调用出现异常
            print(f"[_call_backend_function] {func.__name__} 调用异常: {str(exception_container[0])}")
            return {'error_num': 1, 'msg': f'call_exception: {str(exception_container[0])}'}

        if result_container[0] is not None:
            print(f"[_call_backend_function] {func.__name__} 调用成功")
            return result_container[0]

        # 不应该到达这里
        print(f"[_call_backend_function] {func.__name__} 调用返回空结果")
        return {'error_num': 1, 'msg': 'empty_result'}

    def _get_automation_depth_suggestion(self, question, file_list, all_segments=None):
        """
        获取自动化问答的深度建议（提问前智慧激发）

        Args:
            question: 用户问题
            file_list: 文件列表
            all_segments: RAG检索结果（外部已提前执行）

        Returns:
            str: 深度建议文本
        """
        try:
            from llm_langchain import get_rel_que
            from app_chat.views import chat_history

            # 1. 构造输入文本
            input_text = ""

            # 2. 获取历史问题链（最近3段）
            question_chain = ""
            if self.unique_user_id in chat_history:
                history = chat_history[self.unique_user_id]
                recent_questions = []
                for entry in history[-3:]:
                    if 'question' in entry:
                        recent_questions.append(entry['question'])
                if recent_questions:
                    question_chain = " → ".join(recent_questions)
                    input_text += f"【历史问题链】\n{question_chain}\n\n"

            # 3. 添加当前问题
            input_text += f"【当前问题】\n{question}\n\n"

            # 4. 🔥 使用外部提供的RAG结果生成摘录（与QA深评保持一致）
            if all_segments:
                try:
                    # 优化文档选择：第一段+最后一段+中间随机一段
                    optimized_segments = get_rel_que.optimize_document_selection(all_segments)

                    # 添加RAG采样（三段每段100字）
                    if optimized_segments:
                        input_text += "【参考文档摘录】\n"
                        for i, doc_segments in enumerate(optimized_segments):
                            for j, segment in enumerate(doc_segments):
                                content = segment.page_content
                                if len(content) > 100:
                                    content = content[:100] + "..."
                                input_text += f"文档{i + 1}段落{j + 1}：{content}\n"
                        print(f"[_get_automation_depth_suggestion] 使用RAG结果，生成{len(optimized_segments)}个文档的摘录")
                except Exception as e:
                    print(f"[_get_automation_depth_suggestion] 摘录生成失败: {e}")
            elif file_list:
                # 降级：只取文件名
                input_text += "【参考文档】\n"
                for i, filename in enumerate(file_list[:3], 1):
                    input_text += f"文档{i}：{filename}\n"

            # 5. 调用小模型生成深度建议（task_type="automation_qa"）
            suggestion = get_rel_que.get_depth_suggestion(input_text, self.notebook_id, task_type="automation_qa")
            return suggestion

        except Exception as e:
            print(f"[_get_automation_depth_suggestion] 异常: {e}")
            import traceback
            print(traceback.format_exc())
            return ""


def adjust_lists_to_match(target_list, left_list, right_list):
    """调整left_list和right_list长度与target_list一致"""
    n = len(target_list)

    # # 🔥 修复：确保列表元素都是整数（可能从JSON读取时变成字符串）
    left_list = [int(x) if isinstance(x, str) else x for x in left_list] if left_list else []
    right_list = [int(x) if isinstance(x, str) else x for x in right_list] if right_list else []

    # 调整left_list：不足补1，过长截取
    left_list = (left_list + [1] * n)[:n]

    # 调整right_list：不足补3，过长截取
    right_list = (right_list + [3] * n)[:n]

    return left_list, right_list