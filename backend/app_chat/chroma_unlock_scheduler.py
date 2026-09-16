import threading
import time
import os
import logging
from datetime import datetime
from llm_langchain import parse_input, util, global_var

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 配置文件日志
file_handler = logging.FileHandler('chroma_unlock.log', encoding='utf-8')
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


class ChromaUnlockScheduler:
    """Chroma向量库定时解锁调度器"""
    
    def __init__(self, interval_hours=2):
        self.interval_hours = interval_hours
        self.interval_seconds = interval_hours * 3600  # 转换为秒
        self.is_running = False
        self.thread = None
        
        # 解锁测试参数
        # self.test_username = "admin"
        self.test_username = "admin_test4UnlockChroma"  # 用户名_本子名格式
        self.test_notebook = "test4UnlockChroma"
        self.test_document = "Arc·AGI评级On the Measure of Intelligence1911.01547v2.pdf"
        self.test_question = "一句话说说什么是Arc"
        
    def start(self):
        """启动定时解锁任务"""
        if self.is_running:
            logger.warning("Chroma解锁调度器已在运行中")
            return
            
        self.is_running = True
        self.thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.thread.start()
        logger.info(f"Chroma解锁调度器已启动，每{self.interval_hours}小时执行一次")
        
    def stop(self):
        """停止定时解锁任务"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Chroma解锁调度器已停止")
        
    def _run_scheduler(self):
        """运行调度器主循环"""
        # # 启动后1分钟执行第一次测试
        # logger.info("调度器启动，将在1分钟后执行首次Chroma解锁测试...")
        # time.sleep(60)  # 等待1分钟
        #
        # if not self.is_running:
        #     return
        #
        # # 执行第一次解锁测试
        # try:
        #     logger.info("执行首次Chroma解锁测试...")
        #     self._perform_unlock_test()
        # except Exception as e:
        #     logger.error(f"首次Chroma解锁测试失败: {e}")
        #
        # # 然后按间隔时间循环执行
        print(f"[chroma_unlock_scheduler]:{self.is_running}")
        while self.is_running:
            try:
                # 等待指定时间
                time.sleep(self.interval_seconds)
                
                if not self.is_running:
                    break
                    
                # 执行解锁检测
                self._perform_unlock_test()
                
            except Exception as e:
                logger.error(f"Chroma解锁调度器执行异常: {e}")
                # 即使出错也继续运行，避免调度器停止
                time.sleep(60)  # 出错后等待1分钟再继续
                
    def _perform_unlock_test(self):
        """执行Chroma解锁测试"""
        start_time = time.time()
        logger.info(f"[{datetime.now()}] 开始执行Chroma解锁测试...")
        
        try:
            # 1. 确保用户数据已加载
            self._ensure_user_loaded()
            
            # 2. 执行RAG搜索测试（这是关键的Chroma操作）
            self._test_rag_search()
            
            # 3. 记录成功日志
            duration = time.time() - start_time
            logger.info(f"[{datetime.now()}] Chroma解锁测试完成，耗时: {duration:.2f}秒")
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{datetime.now()}] Chroma解锁测试失败，耗时: {duration:.2f}秒，错误: {e}")

    def _ensure_user_loaded(self):
        """确保admin用户数据已加载"""
        try:
            # 检查用户是否已加载
            if self.test_username not in global_var.store_memory:
                logger.info(f"用户 {self.test_username} 数据未加载，开始加载...")

                # 检查用户目录是否存在
                user_dir = f"./received_dir/user_raw_file/{self.test_username}/"
                if not os.path.exists(user_dir):
                    logger.warning(f"用户目录不存在: {user_dir}")
                    # 尝试使用admin用户进行测试
                    self.test_username = "admin"
                    user_dir = f"./received_dir/user_raw_file/{self.test_username}/"
                    if not os.path.exists(user_dir):
                        logger.error(f"admin用户目录也不存在: {user_dir}")
                        raise FileNotFoundError(f"用户目录不存在: {user_dir}")
                    else:
                        logger.info(f"使用admin用户进行测试")

                # 同步加载用户数据
                parse_input.load_user(self.test_username)

                # 等待一下确保数据完全加载
                import time
                time.sleep(1)

                # 验证数据是否加载成功
                if self.test_username not in global_var.store_memory:
                    raise Exception(f"用户 {self.test_username} 数据加载失败")

                logger.info(f"用户 {self.test_username} 数据加载完成")
            else:
                logger.info(f"用户 {self.test_username} 数据已存在")
        except Exception as e:
            logger.error(f"加载用户数据失败: {e}")
            raise
            
    def _test_rag_search(self):
        """测试RAG搜索功能（关键Chroma操作）"""
        try:
            # 检查用户数据是否存在
            if self.test_username not in global_var.store_memory:
                logger.error(f"用户 {self.test_username} 数据不存在于store_memory中")
                return

            # 获取用户向量存储
            vector_store = global_var.get_user_vector(self.test_username)
            if not vector_store:
                logger.error(f"无法获取用户 {self.test_username} 的向量存储")
                # 尝试直接创建向量存储
                logger.info("尝试直接创建向量存储...")
                from langchain_community.vectorstores.chroma import Chroma
                from llm_langchain.parse_input import embeddings
                from llm_langchain import util

                db_path = util.db_path
                collection_name = util.construct_collection(self.test_username)
                vector_store = Chroma(
                    collection_name=collection_name,
                    embedding_function=embeddings,
                    persist_directory=db_path
                )
                logger.info(f"直接创建向量存储成功: {collection_name}")
                
            # 执行相似性搜索（这是最容易卡住的操作）
            logger.info(f"开始执行RAG搜索测试: {self.test_question}")
            
            # 设置超时保护
            def search_with_timeout():
                # 在函数内部导入util，避免作用域问题
                from llm_langchain import util

                return util.get_relevant_docs(
                    question=self.test_question,
                    vector_store=vector_store,
                    docs_name=[self.test_document],
                    user_name=self.test_username
                )
            
            # 使用线程执行搜索，设置超时
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(search_with_timeout)
                try:
                    # 设置5分钟超时
                    results = future.result(timeout=300)
                    logger.info(f"RAG搜索测试成功，找到 {len(results)} 个相关片段")
                    
                    # 打印前3个结果的前100个字符作为验证
                    for i, doc in enumerate(results[:3]):
                        content_preview = doc.page_content[:100] + "..." if len(doc.page_content) > 100 else doc.page_content
                        logger.info(f"结果 {i+1}: {content_preview}")
                        
                except concurrent.futures.TimeoutError:
                    logger.warning("RAG搜索测试超时（5分钟），但可能已解锁Chroma")
                    future.cancel()
                    
        except Exception as e:
            logger.error(f"RAG搜索测试失败: {e}")
            raise
            
    def force_unlock_now(self):
        """立即执行一次解锁测试"""
        logger.info("手动触发Chroma解锁测试...")
        self._perform_unlock_test()

# 全局调度器实例
chroma_scheduler = ChromaUnlockScheduler(interval_hours=2)

def start_chroma_unlock_scheduler():
    """启动Chroma解锁调度器（在Django启动时调用）"""
    chroma_scheduler.start()

def stop_chroma_unlock_scheduler():
    """停止Chroma解锁调度器（在Django关闭时调用）"""
    chroma_scheduler.stop()

def force_chroma_unlock():
    """手动触发Chroma解锁"""
    chroma_scheduler.force_unlock_now()
