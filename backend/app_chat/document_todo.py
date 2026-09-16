"""
文档级TODO清单自动化系统
基于现有的automation.py框架，实现单文档多位置的自动化操作
"""

import re
import json
import time
import threading
import uuid
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from django.db import models
from app_chat.models import Card
from app_chat import gpt4_api
from app_chat.automation import AutomationEngine, RUNNING_TASKS

# 🔥 全局锁：保护问题调整（避免并发冲突）
_question_adjust_lock = Lock()


def detect_todo_card(username, filename):
    """
    检测是否存在TODO清单卡片

    Args:
        username: 用户名（notebook_id格式）
        filename: 文件名（可带或不带后缀）

    Returns:
        Card对象或None
    """
    # 移除文件后缀
    filename_base = filename.rsplit('.', 1)[0] if '.' in filename else filename

    # 查找contentTitle匹配的卡片
    patterns = [
        f"{filename_base}清单卡",
        f"{filename}清单卡",
        f"{filename_base}+清单卡",
        f"{filename}+清单卡"
    ]

    for pattern in patterns:
        cards = Card.objects.filter(
            username=username,
            contentTitle__icontains=pattern
        ).order_by('-datetime')

        if cards.exists():
            print(f"[TODO清单] 找到清单卡片: {cards.first().contentTitle}")
            return cards.first()

    return None


def parse_todo_items(card_content):
    """
    解析TODO清单内容，提取TODO项

    Args:
        card_content: 卡片内容

    Returns:
        list: TODO项列表 ['xxx', 'yyy', 'zzz']
    """
    # 先尝试直接匹配序号格式：1. xxx 或 1.xxx
    pattern = r'^\s*(\d+)\.\s*(.+)$'

    items = []
    lines = card_content.split('\n')

    for line in lines:
        match = re.match(pattern, line.strip())
        if match:
            item_text = match.group(2).strip()
            if item_text:
                items.append(item_text)

    if items:
        print(f"[TODO清单] 解析到 {len(items)} 个TODO项")
        return items

    # 如果没有找到，尝试调用大模型提取
    print("[TODO清单] 未找到标准格式，尝试用大模型提取...")
    try:
        items = extract_todo_by_llm(card_content)
        if items:
            print(f"[TODO清单] 大模型提取到 {len(items)} 个TODO项")
            return items
    except Exception as e:
        print(f"[TODO清单] 大模型提取失败: {e}")

    return []


def extract_todo_by_llm(card_content):
    """
    用大模型从卡片内容中提取TODO项

    Args:
        card_content: 卡片内容

    Returns:
        list: TODO项列表
    """
    prompt = f"""请从以下内容中提取TODO清单项。

内容可能是：
- 序号列表（1. xxx 2. xxx）
- 表格形式
- 其他格式

请提取出所有清单项，每行一个，不要序号。

内容：
{card_content}

要求：
- 只输出清单项内容，每行一个
- 不要序号、不要其他说明
- 如果没有清单项，输出：无清单项"""

    try:
        # 使用gpt4o（简单任务，快速）
        import asyncio
        result = asyncio.run(gpt4_api.make_gpt4o_text_requests_async(
            user_prompt=prompt,
            system_prompt="你是一个清单提取助手。"
        ))

        if "无清单项" in result:
            return []

        # 按行分割
        items = [line.strip() for line in result.split('\n') if line.strip()]
        return items

    except Exception as e:
        print(f"[TODO清单] LLM提取失败: {e}")
        return []


def adjust_question_for_todo_item(demo_question, demo_item, current_item, item_index=None):
    """
    根据当前TODO项调整示范问题（线程安全）

    Args:
        demo_question: 示范时的问题
        demo_item: 示范时对应的TODO项
        current_item: 当前TODO项
        item_index: TODO项索引（用于日志）

    Returns:
        str: 调整后的问题
    """
    # 🔥 关键：加锁保证并发安全（一次只有一个线程调用GPT）
    with _question_adjust_lock:
        log_prefix = f"[问题调整-TODO{item_index + 1 if item_index is not None else '?'}]"

        prompt = f"""请将示范问题调整为适合当前TODO项的问题。

【示范问题】
{demo_question}

【示范TODO项】
{demo_item}

【当前TODO项】
{current_item}

要求：
- 保持问题的核心结构和意图
- 将问题中与示范TODO项相关的部分替换为当前TODO项
- 问题要简洁、准确
- 直接输出调整后的问题，不要其他说明

调整后的问题："""

        max_retries = 2  # 🔥 最多重试2次（共3次机会）

        for attempt in range(max_retries):
            try:
                # 使用gpt4o（速度快，适合简单任务）
                import asyncio

                # 🔥 并发安全：每次创建全新的event loop并确保正确关闭
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                try:
                    if attempt > 0:
                        print(f"{log_prefix} 第{attempt + 1}次尝试...")

                    print(f"{log_prefix} 示范项: {demo_item[:30]}...")
                    print(f"{log_prefix} 当前项: {current_item[:30]}...")
                    print(f"{log_prefix} 原问题: {demo_question[:50]}...")

                    # 🔥 设置60秒超时
                    adjusted = loop.run_until_complete(
                        asyncio.wait_for(
                            gpt4_api.make_gpt4o_text_requests_async(
                                user_prompt=prompt,
                                system_prompt="你是一个问题调整助手。"
                            ),
                            timeout=60.0
                        )
                    )

                    # 检查结果是否有效
                    if adjusted and len(adjusted.strip()) > 0:
                        print(f"{log_prefix} 新问题: {adjusted[:50]}... ✅")
                        return adjusted.strip()
                    else:
                        print(f"{log_prefix} 结果为空，重试...")
                        if attempt < max_retries - 1:
                            time.sleep(2)
                            continue

                finally:
                    # 确保loop正确关闭
                    try:
                        loop.close()
                    except:
                        pass

            except asyncio.TimeoutError:
                print(f"{log_prefix} 超时（60秒），尝试 {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # 等待2秒后重试
                    continue
            except Exception as e:
                print(f"{log_prefix} 调整失败: {e}，尝试 {attempt + 1}/{max_retries}")
                import traceback
                print(traceback.format_exc())
                if attempt < max_retries - 1:
                    time.sleep(2)  # 等待2秒后重试
                    continue

        # 所有重试都失败，降级：直接返回原问题
        print(f"{log_prefix} 所有重试都失败，使用原问题")
        return demo_question


class DocumentTodoEngine(AutomationEngine):
    """
    文档TODO清单自动化引擎
    继承AutomationEngine，添加TODO清单特定功能
    """

    def __init__(self, notebook_id, target_file, todo_items, current_user=None, scene_name=None):
        """
        初始化文档TODO引擎

        Args:
            notebook_id: 本子ID
            target_file: 目标文件
            todo_items: TODO项列表
            current_user: 当前操作用户（可选，默认从notebook_id提取）
            scene_name: 场景名（NK2026 等）
        """
        super().__init__(notebook_id, target_file, current_user=current_user, scene_name=scene_name)
        self.todo_items = todo_items
        self.demo_item_index = 0  # 示范项索引
        self.current_item_index = 1  # 当前执行的项索引
        self._progress_lock = threading.Lock()  # 🔥 用于保护current_item_index的更新

        # 🔥 修复：DocumentTodoEngine不使用数据库task，设为None避免refresh_from_db错误
        self.task = None

        # 🔥 增加超时时间：文档TODO处理可能更耗时
        self.step_timeout_seconds = 600  # 10分钟超时（原来是4分钟）

        # 🔥 关键修复：TODO模式不使用unique_user_id，避免锁冲突
        # 直接使用notebook_id，复用用户已有的初始化和锁
        self.unique_user_id = self.notebook_id

        print(f"[DocumentTodoEngine] 初始化: 文件={target_file}, TODO项数={len(todo_items)}, 当前用户={self.current_user}")
        print(f"[DocumentTodoEngine] 使用notebook_id作为user_id，避免锁冲突: {self.unique_user_id}")

    def _adjust_action_for_todo_item(self, action_data, item_index):
        """
        根据TODO项调整操作数据

        Args:
            action_data: 操作数据
            item_index: TODO项索引

        Returns:
            dict: 调整后的操作数据
        """
        adjusted_data = action_data.copy()

        # 如果是问答类操作，调整问题
        if 'message' in adjusted_data:
            demo_item = self.todo_items[self.demo_item_index]
            current_item = self.todo_items[item_index]

            # 🔥 传入item_index用于日志和调试
            adjusted_question = adjust_question_for_todo_item(
                adjusted_data['message'],
                demo_item,
                current_item,
                item_index  # 传入索引
            )

            adjusted_data['message'] = adjusted_question

        return adjusted_data

    def run_for_remaining_items(self):
        """
        对剩余的TODO项自动执行
        """
        from app_chat.models import AutomationRecord

        # 获取示范操作记录（获取最新的times）
        max_times = AutomationRecord.objects.filter(
            notebook_id=self.notebook_id,
            target_file=self.target_file
        ).aggregate(models.Max('times'))['times__max']

        if max_times is None:
            print("[DocumentTodoEngine] 没有找到示范操作记录")
            return False

        demo_records = AutomationRecord.objects.filter(
            notebook_id=self.notebook_id,
            target_file=self.target_file,
            times=max_times
        ).order_by('step_number')

        print(f"[DocumentTodoEngine] 找到 {demo_records.count()} 个示范步骤")

        # 🔥 关键：分析示范流程中的卡片选择模式
        self._analyze_card_selection_pattern_todo(demo_records)
        print(f"[DocumentTodoEngine] 卡片选择模式分析完成: {self.card_selection_pattern}")

        # 🔥 预先调整所有TODO项的问题（串行，避免并发冲突）
        print(f"[DocumentTodoEngine] 🔧 预先调整所有TODO项的问题...")
        adjusted_records_map = {}  # {item_index: [adjusted_records]}

        for item_index in range(1, len(self.todo_items)):
            adjusted_records = []
            for record in demo_records:
                action_data = json.loads(json.dumps(record.action_data))
                adjusted_data = self._adjust_action_for_todo_item(action_data, item_index)
                adjusted_records.append((record, adjusted_data))
            adjusted_records_map[item_index] = adjusted_records
            print(f"  TODO项{item_index + 1}的问题调整完成")

        print(f"[DocumentTodoEngine] 🚀 开始并发执行剩余 {len(self.todo_items) - 1} 项")
        print(f"[DocumentTodoEngine] TODO项总数: {len(self.todo_items)}, adjusted_records_map键: {sorted(adjusted_records_map.keys())}")

        # 🔥 动态并发执行：完成一个启动下一个（最多4个并发）
        max_workers = 4
        total_items = len(self.todo_items) - 1  # item_index范围是1到total_items（包含）

        # 🔥 统计已完成的任务数
        completed_count = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 🔥 使用两个字典：一个映射future到item_index，一个集合跟踪所有待等待的future
            future_to_index = {}  # {future: item_index}
            all_futures = set()  # 所有需要等待的future集合（动态更新）

            next_item = 1  # 下一个待提交的项索引（item_index从1开始）

            # 首先提交前min(max_workers, total_items)个任务
            initial_submit = min(max_workers, total_items)
            print(f"[并发执行] 初始提交 {initial_submit} 个任务，total_items={total_items}")
            for item_index in range(1, initial_submit + 1):
                if item_index not in adjusted_records_map:
                    print(f"[并发执行] ⚠️ 警告: item_index={item_index} 不在 adjusted_records_map 中，跳过")
                    continue
                future = executor.submit(
                    self._execute_single_todo_item,
                    item_index,
                    adjusted_records_map[item_index]
                )
                future_to_index[future] = item_index
                all_futures.add(future)  # 添加到待等待集合
                print(f"[并发执行] 提交 TODO项 {item_index + 1} (item_index={item_index})")

            next_item = initial_submit + 1
            print(f"[并发执行] 初始提交完成，next_item={next_item}, 待等待futures={len(all_futures)}")

            # 🔥 关键修复：持续循环，等待所有任务完成，并在任务完成时提交新任务
            from concurrent.futures import as_completed
            while len(all_futures) > 0:
                # 等待当前集合中的任意任务完成
                for future in as_completed(all_futures):
                    item_index = future_to_index.get(future)
                    if item_index is None:
                        print(f"[并发执行] ⚠️ 警告: future不在future_to_index映射中，跳过")
                        continue

                    # 🔥 从待等待集合中移除已完成的future
                    all_futures.discard(future)
                    del future_to_index[future]

                    try:
                        result = future.result()
                        completed_count += 1
                        if result:
                            print(f"[并发执行] TODO项 {item_index + 1} 完成 ✅ (已完成 {completed_count}/{total_items}, 剩余futures={len(all_futures)})")
                        else:
                            print(f"[并发执行] TODO项 {item_index + 1} 失败 ❌ (已完成 {completed_count}/{total_items}, 剩余futures={len(all_futures)})")
                    except Exception as e:
                        completed_count += 1
                        print(f"[并发执行] TODO项 {item_index + 1} 异常: {e} (已完成 {completed_count}/{total_items}, 剩余futures={len(all_futures)})")

                    # 完成一个，提交下一个（如果还有待执行的）
                    if next_item <= total_items:
                        if next_item not in adjusted_records_map:
                            print(f"[并发执行] ⚠️ 警告: next_item={next_item} 不在 adjusted_records_map 中，跳过")
                            next_item += 1
                            continue
                        new_future = executor.submit(
                            self._execute_single_todo_item,
                            next_item,
                            adjusted_records_map[next_item]
                        )
                        future_to_index[new_future] = next_item
                        all_futures.add(new_future)  # 🔥 关键：添加到待等待集合，会被下次循环等待
                        print(f"[并发执行] 提交 TODO项 {next_item + 1}（替补）(item_index={next_item}, 当前待等待futures={len(all_futures)})")
                        next_item += 1
                    else:
                        print(f"[并发执行] next_item={next_item} > total_items={total_items}，不再提交新任务")

                    # 🔥 关键：break出内层for循环，重新创建as_completed迭代器以包含新添加的future
                    break

        print(f"[DocumentTodoEngine] 🎉 所有TODO项并发执行完成 (总计完成 {completed_count}/{total_items} 项)")

        # 🔥 任务完成后，标记为完成状态
        self.current_item_index = len(self.todo_items)  # 设置为总数，表示全部完成

        return True

    def _execute_single_todo_item(self, item_index, adjusted_records):
        """
        执行单个TODO项（用于并发）- 完全独立的引擎实例

        Args:
            item_index: TODO项索引
            adjusted_records: 预调整的操作记录列表 [(record, adjusted_data), ...]

        Returns:
            bool: 是否成功
        """
        try:
            if self.stop_flag:
                print(f"[TODO项{item_index + 1}] 任务被停止")
                return False

            print(f"\n{'='*60}")
            print(f"[TODO项{item_index + 1}] 开始执行")
            print(f"  内容: {self.todo_items[item_index][:50]}...")
            print(f"{'='*60}")

            # 🔥 关键：为每个TODO项创建完全独立的AutomationEngine实例
            item_engine = AutomationEngine(
                self.notebook_id,
                self.target_file,
                current_user=self.current_user,
                scene_name=getattr(self, "scene_name", None),
            )

            # 设置为None避免数据库操作
            item_engine.task = None
            item_engine.step_timeout_seconds = self.step_timeout_seconds

            # 🔥 关键：重写_get_current_card_ids，让独立引擎直接使用action_data中的choosedCardIdList
            def _get_current_card_ids_direct(action_data):
                """直接返回action_data中的choosedCardIdList（已由主引擎计算好）"""
                chosen = action_data.get('choosedCardIdList', [])
                if chosen:
                    print(f"  [独立引擎] 直接使用choosedCardIdList: {chosen}")
                return chosen

            # 动态替换方法
            item_engine._get_current_card_ids = _get_current_card_ids_direct

            print(f"[TODO项{item_index + 1}] 独立引擎ID: {item_engine.unique_user_id}")
            print(f"[TODO项{item_index + 1}] 卡片选择模式: {self.card_selection_pattern}")

            # 对每个步骤执行
            for record, adjusted_data in adjusted_records:
                if self.stop_flag:
                    break

                step_start = time.time()

                # 创建临时task追踪步骤
                if not item_engine.task:
                    class TempTask:
                        def refresh_from_db(self):
                            pass
                        status = 'running'
                        error_message = ''
                        current_step = 0
                    item_engine.task = TempTask()

                item_engine.task.current_step = record.step_number

                # 🔥 关键：根据card_selection_pattern计算应该勾选的卡片
                if record.step_number in self.card_selection_pattern:
                    pattern = self.card_selection_pattern[record.step_number]
                    print(f"  [TODO项{item_index + 1}] 步骤{record.step_number}的选择模式: {pattern}")
                    print(f"  [TODO项{item_index + 1}] 当前item_engine的step_card_mapping: {item_engine.step_card_mapping}")
                    print(f"  [TODO项{item_index + 1}] 记录中的choosedCardIdList: {adjusted_data.get('choosedCardIdList', [])}")

                    # 1. 获取流程创建的卡片（映射到item_engine的step_card_mapping）
                    flow_cards = []
                    flow_created_steps = pattern.get('flow_created_steps', [])
                    for step in flow_created_steps:
                        if step in item_engine.step_card_mapping:
                            flow_cards.extend(item_engine.step_card_mapping[step])
                            print(f"    从步骤{step}获取卡片: {item_engine.step_card_mapping[step]}")
                        else:
                            print(f"    ⚠️ 步骤{step}在item_engine.step_card_mapping中不存在（可能该步骤还未执行）")

                    # 2. 获取已有卡片（每个TODO项都勾选相同的）
                    existing_cards = pattern.get('existing_cards', [])

                    # 3. 合并
                    all_cards = flow_cards + existing_cards

                    print(f"  [TODO项{item_index + 1}] 计算结果:")
                    print(f"    - 流程卡片: {flow_cards} (来自步骤{flow_created_steps})")
                    print(f"    - 已有卡片: {existing_cards}")
                    print(f"    - 合并结果: {all_cards}")

                    # 4. 只有在有卡片需要勾选且操作支持勾选时才设置
                    if all_cards:
                        adjusted_data = adjusted_data.copy()
                        adjusted_data['choosedCardIdList'] = all_cards
                        print(f"  [TODO项{item_index + 1}] ✅ 已设置choosedCardIdList = {all_cards}")
                    else:
                        print(f"  [TODO项{item_index + 1}] 没有需要勾选的卡片")
                else:
                    print(f"  [TODO项{item_index + 1}] 步骤{record.step_number}不在card_selection_pattern中")

                # 记录执行前的卡片数
                cards_before = len(item_engine.created_card_ids)

                # 执行操作
                print(f"  [TODO项{item_index + 1}] 步骤{record.step_number}: {record.action_type}")
                success = self._execute_action_isolated(item_engine, record.action_type, adjusted_data)

                # 更新卡片映射
                cards_after = len(item_engine.created_card_ids)
                if cards_after > cards_before:
                    new_cards = item_engine.created_card_ids[cards_before:]
                    item_engine.step_card_mapping[record.step_number] = new_cards
                    print(f"  [TODO项{item_index + 1}] 创建卡片: {new_cards}")

                if not success:
                    print(f"  [TODO项{item_index + 1}] ❌ 步骤失败（用时: {time.time() - step_start:.1f}秒）")
                    return False
                else:
                    print(f"  [TODO项{item_index + 1}] ✅ 步骤成功（用时: {time.time() - step_start:.1f}秒）")

                time.sleep(1)

            # 🔥 更新全局进度：使用 item_index + 1 确保能正确判断完成状态
            # item_index 是从1开始的（range(1, len(self.todo_items))），
            # 所以当所有项完成时，current_item_index 应该是 len(self.todo_items)
            # 例如：如果有12个TODO项（索引0-11），item_index范围是1-11，最后一个item_index=11完成时，
            # item_index+1=12=len(self.todo_items)，表示全部完成
            with self._progress_lock:
                self.current_item_index = max(self.current_item_index, item_index + 1)

            print(f"[TODO项{item_index + 1}] 完成，创建了{len(item_engine.created_card_ids)}张卡片")
            return True

        except Exception as e:
            print(f"[TODO项{item_index + 1}] 执行失败: {e}")
            import traceback
            print(traceback.format_exc())
            return False

    def _execute_action_isolated(self, item_engine, action_type, action_data):
        """使用独立引擎执行操作（完全隔离）"""
        try:
            if action_type == 'select_file':
                return True
            elif action_type == 'get_file_summary':
                return item_engine._get_file_summary(action_data)
            elif action_type == 'topic_click':
                return item_engine._handle_topic_click(action_data)
            elif action_type == 'send_message':
                return item_engine._send_message(action_data)
            elif action_type == 'create_card':
                return item_engine._create_card(action_data)
            elif action_type == 'click_question':
                return item_engine._click_question(action_data)
            elif action_type == 'enhance_question':
                return item_engine._enhance_question(action_data)
            elif action_type == 'card_operation':
                return item_engine._card_operation(action_data)
            elif action_type == 'select_cards':
                return item_engine._select_cards(action_data)
            elif action_type == 'change_subscene':
                return item_engine._change_subscene(action_data)
            elif action_type == 'direct_card':
                return self._create_direct_card_isolated(item_engine, action_data)
            elif action_type == 'wait':
                for i in range(action_data.get('seconds', 5)):
                    if self.stop_flag:
                        return False
                    time.sleep(1)
                return True
            else:
                print(f"  未知操作: {action_type}，跳过")
                return True
        except Exception as e:
            print(f"  操作失败: {e}")
            import traceback
            print(traceback.format_exc())
            return False

    def _create_direct_card_isolated(self, item_engine, action_data):
        """独立引擎的直接创建卡片"""
        try:
            from app_chat import views
            content = item_engine._replace_names(action_data.get('content', ''))

            request_data = {
                'username': item_engine.notebook_id,
                'content': content,
                'sceneName': action_data.get('sceneName', ''),
                'subSceneName': action_data.get('subSceneName', ''),
                'keyTopics': json.dumps(action_data.get('keyTopics', []))
            }
            result = item_engine._call_backend_function(views.add_card_directly, request_data)

            if result.get('error_num') == 0:
                card_id = result.get('cardId')
                item_engine.created_card_ids.append(card_id)
                print(f"  直接卡片创建成功: {card_id}")

                # 同步打分
                try:
                    score_data = {'username': item_engine.notebook_id, 'content': content, 'cid': card_id}
                    item_engine._call_backend_function(views.card_score, score_data)
                except:
                    pass

                return True
            return False
        except Exception as e:
            print(f"  直接卡片创建失败: {e}")
            return False

    def _analyze_card_selection_pattern_todo(self, records):
        """
        分析TODO模式下的卡片选择模式（正确版：使用created_card_id）

        核心思路：
        1. 收集所有create_card步骤的created_card_id → 流程创建的卡片集合
        2. 对于每个勾选步骤的cardIdList：
           - 在流程创建集合中 → 流程卡片（记录创建步骤号）
           - 不在流程创建集合中 → 已有卡片（记录具体ID）
        """
        # 第一遍：收集所有create_card步骤创建的卡片ID
        card_to_step = {}  # {card_id: 创建步骤号}
        flow_created_cards = set()  # 流程创建的所有卡片ID集合

        for record in records:
            if record.action_type in ['create_card', 'direct_card']:
                created_card_id = record.action_data.get('created_card_id')
                if created_card_id:
                    card_to_step[created_card_id] = record.step_number
                    flow_created_cards.add(created_card_id)
                    print(f"[卡片分析] 步骤{record.step_number}创建了卡片{created_card_id}")
                else:
                    print(f"[卡片分析] ⚠️ 步骤{record.step_number}是创建操作但无created_card_id")

        print(f"[卡片分析] 流程创建的卡片: {flow_created_cards}")
        print(f"[卡片分析] 卡片→步骤映射: {card_to_step}")

        # 第二遍：分析每个勾选步骤（send_message前的select_cards）
        for record in records:
            if 'choosedCardIdList' not in record.action_data:
                continue

            chosen_cards_raw = record.action_data.get('choosedCardIdList', [])

            # 处理不同格式
            chosen_cards = []
            if isinstance(chosen_cards_raw, list):
                chosen_cards = [int(cid) if isinstance(cid, str) and cid.isdigit() else cid
                               for cid in chosen_cards_raw if cid]
            elif isinstance(chosen_cards_raw, str) and chosen_cards_raw:
                chosen_cards = [int(cid) for cid in chosen_cards_raw.split(',') if cid.strip()]

            if not chosen_cards:
                continue

            print(f"[卡片分析] 步骤{record.step_number}勾选了{len(chosen_cards)}张卡片: {chosen_cards}")

            # 🔥 正确方法：查询每张卡片是否在流程创建集合中
            flow_created_steps = []  # 流程创建的卡片对应的创建步骤号
            existing_cards = []  # 已有卡片ID

            for card_id in chosen_cards:
                if card_id in flow_created_cards:
                    # 流程创建的卡片
                    creation_step = card_to_step[card_id]
                    if creation_step not in flow_created_steps:
                        flow_created_steps.append(creation_step)
                    print(f"  卡片{card_id}: 流程创建（步骤{creation_step}）")
                else:
                    # 已有卡片
                    existing_cards.append(card_id)
                    print(f"  卡片{card_id}: 已有卡片")

            # 记录选择模式
            self.card_selection_pattern[record.step_number] = {
                'flow_created_steps': sorted(flow_created_steps),  # 流程创建的卡片所在步骤号
                'existing_cards': existing_cards  # 已有卡片的具体ID
            }

            print(f"[卡片分析] 步骤{record.step_number}: 流程步骤={sorted(flow_created_steps)}, 已有卡片={existing_cards}")

        print(f"[卡片分析] 完整模式: {self.card_selection_pattern}")

    def _get_current_card_ids_todo(self, action_data, current_step):
        """
        获取当前应该勾选的卡片（TODO模式，支持已有卡片）

        Args:
            action_data: 操作数据
            current_step: 当前步骤号

        Returns:
            list: 应该勾选的卡片ID列表
        """
        # 如果记录中没有勾选卡片，返回空
        recorded_card_list = action_data.get('choosedCardIdList', [])
        if not recorded_card_list:
            return []

        # 查找选择模式
        if current_step not in self.card_selection_pattern:
            print(f"  [卡片选择] 步骤{current_step}无选择模式")
            return []

        pattern = self.card_selection_pattern[current_step]
        selected_cards = []

        # 1. 处理流程中创建的卡片
        flow_created_steps = pattern.get('flow_created_steps', [])
        for step in flow_created_steps:
            if step in self.step_card_mapping:
                selected_cards.extend(self.step_card_mapping[step])
                print(f"  [卡片选择] 从步骤{step}选择流程创建的卡片: {self.step_card_mapping[step]}")

        # 2. 处理已有卡片（每个TODO项都勾选相同的已有卡片）
        existing_cards = pattern.get('existing_cards', [])
        if existing_cards:
            selected_cards.extend(existing_cards)
            print(f"  [卡片选择] 勾选已有卡片: {existing_cards}")

        print(f"  [卡片选择] 最终选择: {selected_cards}")
        return selected_cards

    def _get_current_card_ids(self, action_data):
        """
        重写父类方法：获取当前应该勾选的卡片（TODO模式）
        """
        current_step = getattr(self.task, 'current_step', 0) if self.task else 0
        return self._get_current_card_ids_todo(action_data, current_step)

    def _execute_action_by_type(self, action_type, action_data):
        """
        根据动作类型执行操作（重写以避免task相关检查）
        """
        # 🔥 TODO模式下，跳过task相关的检查
        # 直接调用操作方法，不检查task状态

        action_map = {
            'select_file': lambda x: True,  # 文件选择，仅记录用，直接返回True
            'get_file_summary': self._get_file_summary,
            'topic_click': self._handle_topic_click,
            'send_message': self._send_message_todo,
            'create_card': self._create_card,
            'click_question': self._click_question,
            'enhance_question': self._enhance_question,
            'card_operation': self._card_operation,
            'select_cards': self._select_cards,
            'change_subscene': self._change_subscene,
            'direct_card': self._create_direct_card,
            'wait': self._handle_wait,  # 等待操作
        }

        handler = action_map.get(action_type)
        if handler:
            return handler(action_data)
        else:
            print(f"[DocumentTodoEngine] 未知操作类型: {action_type}，跳过")
            return True  # 未知操作视为成功，继续执行

    def _handle_wait(self, action_data):
        """处理等待操作"""
        wait_seconds = action_data.get('seconds', 5)
        print(f"[_handle_wait] 等待 {wait_seconds} 秒...")

        # 分段等待，支持中途停止
        for i in range(wait_seconds):
            if self.stop_flag:
                print(f"[_handle_wait] 等待被中断")
                return False
            time.sleep(1)

        return True

    def _create_direct_card(self, action_data):
        """创建直接卡片（TODO模式，简化版本避免asyncio问题）"""
        try:
            from app_chat import views

            content = self._replace_names(action_data.get('content', ''))

            # 1. 创建卡片
            request_data = {
                'username': self.notebook_id,
                'content': content,
                'sceneName': action_data.get('sceneName', ''),
                'subSceneName': action_data.get('subSceneName', ''),
                'keyTopics': json.dumps(action_data.get('keyTopics', []))
            }
            result = self._call_backend_function(views.add_card_directly, request_data)

            if result.get('error_num') == 0:
                card_id = result.get('cardId')
                self.created_card_ids.append(card_id)
                print(f"[_create_direct_card_todo] 卡片创建成功: {card_id}")

                # 2. 红蓝评测（同步版本，避免asyncio问题）
                try:
                    request_data_HL = {
                        'username': self.notebook_id,
                        'text': content
                    }
                    result_HL = self._call_backend_function(views.execute_commands, request_data_HL)

                    if result_HL.get('error_num') == 0:
                        data_str = result_HL.get('data', '').strip()
                        if data_str.startswith('"') and data_str.endswith('"'):
                            data_str = data_str[1:-1]
                        data_str = data_str.replace('\\"', '"').replace('\\\\', '\\')

                        result_object = json.loads(data_str)
                        decoded_result = self._decode_result(result_object.get('result', ''))

                        if decoded_result and decoded_result != "fail":
                            eval_data = {
                                'content': decoded_result,
                                'cid': str(card_id)
                            }
                            self._call_backend_function(views.card_evalSFT, eval_data)
                            print(f"[_create_direct_card_todo] 红蓝评测完成")
                except Exception as e:
                    print(f"[_create_direct_card_todo] 红蓝评测失败（不影响卡片）: {e}")

                # 3. 打分（同步版本）
                try:
                    score_data = {
                        'username': self.notebook_id,
                        'content': content,
                        'cid': card_id
                    }
                    self._call_backend_function(views.card_score, score_data)
                    print(f"[_create_direct_card_todo] 打分完成")
                except Exception as e:
                    print(f"[_create_direct_card_todo] 打分失败（不影响卡片）: {e}")

                return True
            else:
                print(f"[_create_direct_card_todo] 卡片创建失败: {result}")
                return False

        except Exception as e:
            print(f"[_create_direct_card_todo] 失败: {e}")
            import traceback
            print(traceback.format_exc())
            return False

    def _send_message_todo(self, action_data):
        """
        发送消息（TODO模式，跳过task检查）
        """
        try:
            # 检查stop_flag
            if self.stop_flag:
                print(f"[_send_message_todo] 任务被停止")
                return False

            # 🔥 保存当前task（包含current_step），在调用父类方法后恢复
            # 这样能保证卡片映射正确工作
            original_task = self.task
            current_step_backup = getattr(self.task, 'current_step', 0) if self.task else 0

            print(f"  [卡片映射调试] 当前步骤: {current_step_backup}")
            print(f"  [卡片映射调试] 选择模式: {self.card_selection_pattern}")
            print(f"  [卡片映射调试] 卡片映射: {self.step_card_mapping}")
            print(f"  [卡片映射调试] 已创建卡片: {self.created_card_ids}")

            # 临时创建FakeTask，但保留current_step
            class FakeTask:
                def refresh_from_db(self):
                    pass
                status = 'running'
                error_message = ''

            fake_task = FakeTask()
            fake_task.current_step = current_step_backup  # 保留步骤号
            self.task = fake_task

            try:
                # 调用父类的_send_message方法
                result = super()._send_message(action_data)
                print(f"[_send_message_todo] 消息发送{'成功' if result else '失败'}")
                return result
            finally:
                # 恢复原task状态（保持current_step）
                if original_task:
                    original_task.current_step = current_step_backup
                self.task = original_task

        except Exception as e:
            print(f"[_send_message_todo] 发送消息失败: {str(e)}")
            import traceback
            print(f"[_send_message_todo] 详细错误栈:\n{traceback.format_exc()}")
            return False


# 全局TODO任务映射
TODO_TASKS = {}  # {task_id: DocumentTodoEngine实例}

