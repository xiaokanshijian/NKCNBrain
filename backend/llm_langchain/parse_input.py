import nkcn_public_config as _public_config
# 需要确定输入的格式，可以有字符串，可以有文档，文档也需要区分其类别进行处理，如果可以得到文档document类型则无所谓，目前先使用text进行示例
import json
from threading import Event, Thread, RLock
from concurrent.futures import ThreadPoolExecutor
import subprocess

import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from langchain_community.embeddings.huggingface import HuggingFaceInstructEmbeddings
from langchain_community.embeddings import HuggingFaceBgeEmbeddings, ModelScopeEmbeddings
# from langchain_community.vectorstores.chroma import Chroma
from langchain_chroma.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from llm_langchain import util
from langchain_core.documents import Document
import os
from llm_langchain import global_var
from langchain_community.document_loaders import Docx2txtLoader
from langchain.document_loaders import PyPDFLoader, PyMuPDFLoader, TextLoader
from langchain_openai import OpenAIEmbeddings
from datetime import datetime
from app_chat.utils import encode_chinese_to_hex
import shutil
import chardet
import time
import chromadb

# os.environ["OPENAI_API_KEY"] = "[redacted]"   # openai old

os.environ.setdefault("OPENAI_API_KEY", _public_config.secret('OPENAI_API_KEY'))  # openai new
# OPEN_AI_KEY = "[redacted]"
# OPEN_AI_KEY = "[redacted]"
OPEN_AI_KEY = _public_config.secret('OPENAI_API_KEY')
DASHSCOPE_API_KEY = _public_config.secret('NKCN_LLM_DASHSCOPE_API_KEY')
# os.environ["OPENAI_API_KEY"] = "[redacted]"
# OPEN_AI_KEY = "[redacted]"
base_url = _public_config.endpoint('NKCN_LEGACY_GATEWAY_V1_URL', 'http://localhost:9999/v1')

# 使用的embedding模型的路径
EMBEDDING_MODEL_NAME = r"E:\LM2\instructor-large"

# 文件类型到加载器的映射（优化：直接使用字典而不是列表循环）
LOADER_MAPPING = {
    "docx": ("Docx2txtLoader", False),  # 不需要编码检测
    "pdf": ("PyMuPDFLoader", False),    # 不需要编码检测
    "txt": ("TextLoader", True),        # 需要编码检测
}

# 编码检测缓存（避免重复检测相同文件）
_ENCODING_CACHE = {}

# 保留向后兼容性
ends_str = ["docx", "pdf", "txt"]
rel_fun = ["Docx2txtLoader", "PyMuPDFLoader", "TextLoader"]


# def assess_document_confidence(user_name, document_content):
#     """
#     调用8卡服务器进行文档置信度评估
#     """
#     try:
#         # 通过中转服务器调用8卡服务器
#         api_url = "http://localhost:8000/assess_document_confidence"
#
#         # 准备请求数据
#         data = {
#             'user_name': user_name,
#             'document_content': document_content
#         }
#
#         # 发送请求
#         response = requests.post(api_url, json=data, timeout=30)
#
#         if response.status_code == 200:
#             result = response.json()
#             return result
#         else:
#             print(f"置信度评估API调用失败: {response.status_code}")
#             return {
#                 'confidence_score': 2.0,
#                 'assessment_time': 0,
#                 'raw_result': f"API调用失败: {response.status_code}"
#             }
#
#     except Exception as e:
#         print(f"调用置信度评估API失败: {str(e)}")
#         return {
#             'confidence_score': 2.0,
#             'assessment_time': 0,
#             'raw_result': f"API调用异常: {str(e)}"
#         }


def assess_document_confidence(user_name, document_content):
    """
    调用8卡服务器进行文档置信度评估（通过中转服务器）
    """
    # 处理换行符和特殊字符
    document_content = document_content.replace("\n", "\\n")
    document_content = document_content.replace('```', '').replace('"""', '').replace('"', '“').replace("'", '‘')

    json_data = json.dumps({
        "user_name": user_name,
        "document_content": document_content
    })

    try:
        # 从全局变量获取小模型ID（使用系统用户名）
        def get_small_model_server_url(username):
            """根据username从全局变量获取小模型ID，返回对应的服务器URL"""
            from app_chat.global_state import GLOBAL_STATE
            model_id = GLOBAL_STATE.user_little_model_id.get(username, "3003")
            if str(model_id) == "3007":
                return _public_config.endpoint('NKCN_SERVICE_8000_URL', 'http://localhost:8000')
            else:
                return _public_config.endpoint('NKCN_SERVICE_8000_URL', 'http://localhost:8000')

        server_url = get_small_model_server_url(user_name)
        # 使用curl命令调用中转服务器API
        # command = f'curl -X POST -H "Content-Type: application/json" -d \'{json_data}\' http://localhost:8000/assess_document_confidence'
        command = f'curl -X POST -H "Content-Type: application/json" -d \'{json_data}\' {server_url}/assess_document_confidence'
        result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

        # 解析返回结果
        result_data = json.loads(result.stdout)

        if result_data.get('error_num') == 0:
            return {
                'confidence_score': result_data.get('confidence_score', 2.0),
                'assessment_time': result_data.get('assessment_time', 0),
                'raw_result': result_data.get('raw_result', '')
            }
        else:
            print(f"置信度评估API调用失败: {result_data.get('message', 'Unknown error')}")
            return {
                'confidence_score': 2.0,
                'assessment_time': 0,
                'raw_result': f"API调用失败: {result_data.get('message', 'Unknown error')}"
            }

    except subprocess.CalledProcessError as e:
        print(f"调用置信度评估API失败(subprocess): {str(e)}")
        return {
            'confidence_score': 2.0,
            'assessment_time': 0,
            'raw_result': f"API调用异常: {str(e)}"
        }
    except Exception as e:
        print(f"调用置信度评估API失败: {str(e)}")
        return {
            'confidence_score': 2.0,
            'assessment_time': 0,
            'raw_result': f"API调用异常: {str(e)}"
        }


# def create_embeddings_with_retry():
#     """创建带有重试机制的 embeddings 实例"""
#     max_retries = 3
#     for attempt in range(max_retries):
#         try:
#             return OpenAIEmbeddings(
#                 model="text-embedding-3-large",
#                 openai_api_key=OPEN_AI_KEY,
#                 openai_api_base='http://localhost:9999/v1/',
#                 default_headers={"x-foo": "true"},
#                 request_timeout=120,  # 增加超时时间
#                 max_retries=3,  # 设置重试次数
#             )
#         except Exception as e:
#             print(f"创建 embeddings 第 {attempt + 1} 次尝试失败: {e}")
#             if attempt < max_retries - 1:
#                 time.sleep(2 ** attempt)  # 指数退避
#             else:
#                 print("所有重试都失败了，使用备用方案")
#                 # 备用方案：使用本地 HuggingFace 模型
#                 return HuggingFaceInstructEmbeddings(
#                     model_name=EMBEDDING_MODEL_NAME,
#                     query_instruction="Represent the query for retrieval: "
#                 )
#
# embeddings = create_embeddings_with_retry()

# 🔥 简单的Embedding客户端复用方案
from llm_langchain.embedding_client_pool import get_embedding_client


def create_embeddings_with_retry():
    """创建带有重试机制的 embeddings 实例"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 🔥 使用复用的OpenAI客户端
            client = get_embedding_client(
                api_key=OPEN_AI_KEY,
                base_url=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/')
            )

            return OpenAIEmbeddings(
                model="text-embedding-3-large",
                # model="text-embedding-3-large-X",
                openai_api_key=OPEN_AI_KEY,
                openai_api_base=_public_config.endpoint('NKCN_MODEL_GATEWAY_V1_URL', 'http://localhost:9999/v1/'),
                default_headers={"x-foo": "true"},
                request_timeout=120,  # 增加超时时间
                max_retries=3,  # 设置重试次数
                # client=client  # 🔥 关键：使用复用连接的客户端
                client=client.embeddings  # 🔥 关键：传入embeddings对象而不是完整客户端
            )
        except Exception as e:
            print(f"创建 embeddings 第 {attempt + 1} 次尝试失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
            else:
                print("所有重试都失败了，使用备用方案")
                # 备用方案：使用本地 HuggingFace 模型
                return HuggingFaceInstructEmbeddings(
                    model_name=EMBEDDING_MODEL_NAME,
                    query_instruction="Represent the query for retrieval: "
                )


embeddings = create_embeddings_with_retry()

# embeddings = HuggingFaceInstructEmbeddings(
#     model_name=EMBEDDING_MODEL_NAME,
#     query_instruction="Represent the query for retrieval: "
# )

lock = {}
_meta_lock = {}
_meta_guard = RLock()
# 同一本子并发 load_user：后来的请求挂到这次加载上，而不是 25 秒后报错
_load_done = {}
_load_done_guard = RLock()


def _memory_lock(user_name):
    with _meta_guard:
        if user_name not in _meta_lock:
            _meta_lock[user_name] = RLock()
        return _meta_lock[user_name]


def _user_lock(user_name):
    if user_name not in lock:
        lock[user_name] = RLock()
    return lock[user_name]


def _force_new_user_lock(user_name, progress_id=None, reason=''):
    old = lock.get(user_name)
    lock[user_name] = RLock()
    print(
        f"[{progress_id}] 强制换锁 user={user_name} reason={reason} "
        f"old_id={id(old) if old is not None else None}"
    )
    return lock[user_name]


def _vector_ready(user_name):
    mem = global_var.store_memory.get(user_name) or {}
    return mem.get('vector_store') is not None


def _write_progress(progress_id, **fields):
    """热重载后创建进度的进程和灌向量的进程可能不是同一个；没有内存记录也要写上（并落盘）。"""
    if not progress_id:
        return
    from zym.views import progress_data
    if hasattr(progress_data, 'ensure'):
        progress_data.ensure(progress_id, **fields)
        return
    if progress_id not in progress_data:
        progress_data[progress_id] = {'status': 'started', 'progress': 0, 'message': '准备加载用户数据...'}
    for key, value in fields.items():
        progress_data[progress_id][key] = value


def _mark_progress_done(progress_id, message='加载完成'):
    _write_progress(progress_id, progress=100, status='completed', message=message)


def _wait_for_inflight_load(user_name, progress_id, seconds=180):
    """锁被占用时跟随正在进行的加载，而不是卡在 0% 连试 5 次后失败。"""
    from zym.views import progress_data
    deadline = time.time() + seconds
    attempt = 0
    while time.time() < deadline:
        if _vector_ready(user_name):
            _mark_progress_done(progress_id)
            return True
        with _load_done_guard:
            event = _load_done.get(user_name)
        if event is None:
            return False
        if event.is_set():
            if _vector_ready(user_name):
                _mark_progress_done(progress_id)
                return True
            return False
        attempt += 1
        _write_progress(progress_id, progress=min(12, 4 + attempt // 3), message='本子正在加载，请稍候…')
        event.wait(timeout=2)
    return False


# 共享 Chroma 数据探测缓存：避免 load_user 频繁触发磁盘/锁等待
_SHARED_CHROMA_PRESENCE_CACHE = {}
_SHARED_CHROMA_PRESENCE_CACHE_LOCK = RLock()
_SHARED_CHROMA_PRESENCE_CACHE_TTL_SEC = 300


def _detect_shared_chroma_collection_fast(shared_db_file: str, collection_name: str, timeout_sec: float = 1.0):
    """尽量快速判断共享 chroma.sqlite3 中某个 collection 是否存在/是否有数据。

    关键点：
    - 不调用 chromadb 的 collection.get()/count()，避免触发 HNSW 索引加载或长时间阻塞。
    - 直接只读访问 sqlite3（mode=ro），并设置短 timeout/busy_timeout。

    返回：(collection_exists: bool, has_any_row: bool|None)
    - has_any_row 为 None 表示无法从当前 schema 中确认是否有数据，但 collection 记录存在。
    """
    import sqlite3

    uri = f"file:{shared_db_file}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=timeout_sec)
    try:
        conn.execute("PRAGMA query_only = ON;")
        # 尽量不要在数据库忙时等待太久
        conn.execute("PRAGMA busy_timeout = 500;")

        # 1) collection 是否存在（通常足够快）
        row = conn.execute(
            "SELECT id FROM collections WHERE name = ? LIMIT 1;",
            (collection_name,),
        ).fetchone()
        if not row:
            return False, False

        collection_id = row[0]

        # 2) 尝试确认是否有数据（不同版本 schema 可能不同，逐个尝试）
        candidate_queries = [
            # 常见 schema：segments(collection_id) + embeddings(segment_id)
            (
                "SELECT 1 FROM embeddings e JOIN segments s ON e.segment_id = s.id WHERE s.collection_id = ? LIMIT 1;",
                (collection_id,),
            ),
            # 兼容旧列名：segments(collection)
            (
                "SELECT 1 FROM embeddings e JOIN segments s ON e.segment_id = s.id WHERE s.collection = ? LIMIT 1;",
                (collection_id,),
            ),
            # 少数 schema：embeddings 表直接有 collection_id
            (
                "SELECT 1 FROM embeddings WHERE collection_id = ? LIMIT 1;",
                (collection_id,),
            ),
        ]

        for sql, params in candidate_queries:
            try:
                hit = conn.execute(sql, params).fetchone()
                if hit:
                    return True, True
            except Exception:
                continue

        # 能找到 collection，但无法确认是否有数据（或确实为空）
        return True, False
    finally:
        try:
            conn.close()
        except Exception:
            pass


# # 🔥 智能数据库路径检测函数（兼容新旧数据库结构，支持数据合并）
# def get_user_db_path(usr_name):
#     """
#     智能检测并返回用户的数据库路径（支持数据分散在两处的情况）

#     检测逻辑：
#     1. 检查用户独立目录是否有数据
#     2. 检查共享目录是否有数据
#     3. 根据检测结果返回合适的路径配置

#     返回值：
#         (primary_db_path, db_type, secondary_db_path)
#         - primary_db_path: 主数据库路径（写入目标）
#         - db_type: "独立" / "共享" / "新建独立" / "混合"
#         - secondary_db_path: 次要数据库路径（仅读取，混合模式下使用）
#     """
#     db_path = util.db_path  # ./received_dir/user_db_file
#     user_db_path = os.path.join(db_path, usr_name)  # 用户独立目录
#     shared_db_file = os.path.join(db_path, "chroma.sqlite3")  # 共享数据库文件
#     user_db_file = os.path.join(user_db_path, "chroma.sqlite3")  # 用户独立数据库文件

#     has_user_db = os.path.exists(user_db_path) and os.path.exists(user_db_file)
#     has_shared_data = False
#     shared_count = 0

#     # 检查共享目录是否存在该用户的数据
#     if os.path.exists(shared_db_file):
#         try:
#             import chromadb
#             start_time = time.time()

#             client = chromadb.PersistentClient(path=db_path)
#             collection_name = util.construct_collection(usr_name)

#             get_client_time = time.time()
#             print(f"get_client耗时: {get_client_time - start_time:.3f}秒")

#             try:
#                 collection = client.get_collection(collection_name)
#                 get_collection_time = time.time()
#                 print(f"get_collection耗时: {get_collection_time - start_time:.3f}秒")

#                 # # 使用limit=1只获取一条数据，比count()快得多
#                 # result = collection.get(limit=1)
#                 # has_shared_data = len(result.get('ids', [])) > 0
#                 # get_limit_time = time.time()
#                 # print(f"get_limit耗时: {get_limit_time - start_time:.3f}秒")

#                 result = collection.peek(limit=1)  # 比 get(limit=1) 快很多
#                 has_shared_data = len(result.get('ids', [])) > 0
#                 peek_time = time.time()
#                 print(f"peek耗时: {peek_time - get_collection_time:.3f}秒")

#                 # shared_count = collection.count()
#                 # has_shared_data = shared_count > 0
#             except Exception:
#                 pass
#         except Exception as e:
#             print(f"[DB路径检测] 检查共享数据库时出错: {e}")

#     # 🔥 场景1: 数据分散在两处（混合模式）
#     if has_user_db and has_shared_data:
#         print(f"[DB路径检测] ⚠️ 检测到数据分散：独立目录有数据，共享目录也有数据")
#         print(f"[DB路径检测] 使用混合模式：主库={user_db_path}, 从库={db_path}")
#         return user_db_path, "混合", db_path

#     # 场景2: 仅独立目录有数据
#     if has_user_db:
#         print(f"[DB路径检测] 使用用户独立数据库: {user_db_path}")
#         return user_db_path, "独立", None

#     # 场景3: 仅共享目录有数据
#     if has_shared_data:
#         print(f"[DB路径检测] 在共享数据库中发现用户数据，使用共享目录: {db_path}")
#         return db_path, "共享", None

#     # 场景4: 都没有数据，创建新的用户独立目录
#     os.makedirs(user_db_path, exist_ok=True)
#     print(f"[DB路径检测] 创建新的用户独立数据库目录: {user_db_path}")
#     return user_db_path, "新建独立", None


# 🔥 智能数据库路径检测函数（兼容新旧数据库结构，支持数据合并）
def get_user_db_path(usr_name):
    """
    智能检测并返回用户的数据库路径（支持数据分散在两处的情况）

    检测逻辑：
    1. 检查用户独立目录是否有数据
    2. 检查共享目录是否有数据
    3. 根据检测结果返回合适的路径配置

    返回值：
        (primary_db_path, db_type, secondary_db_path)
        - primary_db_path: 主数据库路径（写入目标）
        - db_type: "独立" / "共享" / "新建独立" / "混合"
        - secondary_db_path: 次要数据库路径（仅读取，混合模式下使用）
    """
    db_path = util.db_path  # ./received_dir/user_db_file
    user_db_path = os.path.join(db_path, usr_name)  # 用户独立目录
    shared_db_file = os.path.join(db_path, "chroma.sqlite3")  # 共享数据库文件
    user_db_file = os.path.join(user_db_path, "chroma.sqlite3")  # 用户独立数据库文件

    has_user_db = os.path.exists(user_db_path) and os.path.exists(user_db_file)
    has_shared_data = False
    shared_count = 0

    # 检查共享目录是否存在该用户的数据（只读直查 sqlite，避免 chromadb API 卡住）
    if os.path.exists(shared_db_file):
        collection_name = util.construct_collection(usr_name)
        cache_key = (shared_db_file, collection_name)

        now = time.time()
        with _SHARED_CHROMA_PRESENCE_CACHE_LOCK:
            cached = _SHARED_CHROMA_PRESENCE_CACHE.get(cache_key)
            if cached and (now - cached.get("ts", 0) < _SHARED_CHROMA_PRESENCE_CACHE_TTL_SEC):
                has_shared_data = bool(cached.get("has_shared_data", False))
            else:
                try:
                    t0 = time.time()
                    collection_exists, has_any_row = _detect_shared_chroma_collection_fast(
                        shared_db_file=shared_db_file,
                        collection_name=collection_name,
                        timeout_sec=1.0,
                    )
                    cost = time.time() - t0
                    if cost > 2:
                        print(f"[DB路径检测] ⚠️ 共享库探测耗时较长: {cost:.3f}s")

                    # 只要 collection 记录存在，就认为共享库可能有数据，避免误判导致创建新库而“丢数据”
                    if collection_exists:
                        has_shared_data = True if (has_any_row is None) else bool(has_any_row)
                    else:
                        has_shared_data = False
                except Exception as e:
                    # 探测失败时，为了不阻塞 load_user，快速降级：
                    # - 若用户独立库存在，则优先独立库
                    # - 否则倾向认为共享库有数据（避免误创建新库导致老数据不可见）
                    print(f"[DB路径检测] 共享库快速探测失败: {e}")
                    has_shared_data = not has_user_db

                _SHARED_CHROMA_PRESENCE_CACHE[cache_key] = {
                    "ts": now,
                    "has_shared_data": has_shared_data,
                }

    # 🔥 场景1: 数据分散在两处（混合模式）
    if has_user_db and has_shared_data:
        print(f"[DB路径检测] ⚠️ 检测到数据分散：独立目录有数据，共享目录也有数据")
        print(f"[DB路径检测] 使用混合模式：主库={user_db_path}, 从库={db_path}")
        return user_db_path, "混合", db_path

    # 场景2: 仅独立目录有数据
    if has_user_db:
        print(f"[DB路径检测] 使用用户独立数据库: {user_db_path}")
        return user_db_path, "独立", None

    # 场景3: 仅共享目录有数据
    if has_shared_data:
        print(f"[DB路径检测] 在共享数据库中发现用户数据，使用共享目录: {db_path}")
        return db_path, "共享", None

    # 场景4: 都没有数据，创建新的用户独立目录
    os.makedirs(user_db_path, exist_ok=True)
    print(f"[DB路径检测] 创建新的用户独立数据库目录: {user_db_path}")
    return user_db_path, "新建独立", None


def merge_query_results(primary_results, secondary_results):
    """
    合并来自主数据库和次要数据库的查询结果

    参数：
        primary_results: 主数据库的查询结果列表 [(doc, score), ...]
        secondary_results: 次要数据库的查询结果列表 [(doc, score), ...]

    返回：
        合并并去重后的结果，按相关性得分排序
    """
    if not secondary_results:
        return primary_results

    # 使用文档内容的哈希去重
    seen = set()
    merged = []

    # 合并两个列表
    all_results = list(primary_results) + list(secondary_results)

    # 去重并保留最高分
    doc_scores = {}  # {doc_content: max_score}
    for doc, score in all_results:
        content = doc.page_content if hasattr(doc, 'page_content') else str(doc)
        if content not in doc_scores or score > doc_scores[content][1]:
            doc_scores[content] = (doc, score)

    # 转换回列表并按分数排序
    merged = sorted(doc_scores.values(), key=lambda x: x[1], reverse=True)

    print(f"[混合查询] 主库结果: {len(primary_results)}条, 从库结果: {len(secondary_results)}条, 合并后: {len(merged)}条")
    return merged


def similarity_search_with_merge(vector_store, user_name, query, k=10, filter=None):
    """
    支持混合模式的相似性搜索（自动合并主库和从库的结果）

    参数：
        vector_store: 主向量数据库
        user_name: 用户名
        query: 查询文本
        k: 返回结果数量
        filter: 过滤条件

    返回：
        查询结果列表（已去重和合并）
    """
    # 从主库查询
    primary_docs = vector_store.similarity_search(query, k, filter=filter)

    # 检查是否有从库（混合模式）
    secondary_store = None
    if user_name in global_var.store_memory and "secondary_vector_store" in global_var.store_memory[user_name]:
        secondary_store = global_var.store_memory[user_name]["secondary_vector_store"]

    if secondary_store is None:
        # 非混合模式，直接返回主库结果
        return primary_docs

    # 混合模式：从从库也查询
    print(f"[混合查询] 同时从主库和从库查询...")
    try:
        secondary_docs = secondary_store.similarity_search(query, k, filter=filter)

        # 合并结果（这里简化处理，直接合并列表并去重）
        # 注意：similarity_search返回的是Document列表，没有分数
        # 我们需要转换为 similarity_search_with_score 来获取分数
        primary_with_scores = vector_store.similarity_search_with_score(query, k, filter=filter)
        secondary_with_scores = secondary_store.similarity_search_with_score(query, k, filter=filter)

        # 合并结果
        merged_results = merge_query_results(primary_with_scores, secondary_with_scores)

        # 只返回文档，不返回分数（保持接口一致）
        merged_docs = [doc for doc, score in merged_results[:k]]

        print(f"[混合查询] 返回合并后的 {len(merged_docs)} 条结果")
        return merged_docs

    except Exception as e:
        print(f"[混合查询] 从库查询失败: {e}，仅使用主库结果")
        return primary_docs


def mmr_search_with_merge(vector_store, user_name, query, k=8, fetch_k=16, lambda_mult=0.7, filter=None):
    """
    支持混合模式的MMR搜索（自动合并主库和从库的结果）

    MMR (Maximal Marginal Relevance) 在保证相关性的同时增加结果多样性

    参数：
        vector_store: 主向量数据库
        user_name: 用户名
        query: 查询文本
        k: 最终返回文档数量
        fetch_k: 先获取多少候选文档供MMR选择（通常是k的2-3倍）
        lambda_mult: 平衡相似性和多样性的参数 (0-1之间，越大越注重相关性)
        filter: 过滤条件

    返回：
        MMR优化后的查询结果列表
    """
    # 从主库查询
    primary_docs = vector_store.max_marginal_relevance_search(
        query=query,
        k=k,
        fetch_k=fetch_k,
        lambda_mult=lambda_mult,
        filter=filter
    )

    # 检查是否有从库（混合模式）
    secondary_store = None
    if user_name in global_var.store_memory and "secondary_vector_store" in global_var.store_memory[user_name]:
        secondary_store = global_var.store_memory[user_name]["secondary_vector_store"]

    if secondary_store is None:
        # 非混合模式，直接返回主库结果
        return primary_docs

    # 混合模式：从从库也查询
    print(f"[混合MMR查询] 同时从主库和从库查询...")
    try:
        secondary_docs = secondary_store.max_marginal_relevance_search(
            query=query,
            k=k,
            fetch_k=fetch_k,
            lambda_mult=lambda_mult,
            filter=filter
        )

        # MMR搜索没有直接返回分数，我们需要手动计算相似度来合并
        # 简化处理：先用 similarity_search_with_score 获取分数，再按MMR逻辑选择
        primary_with_scores = vector_store.similarity_search_with_score(query, fetch_k, filter=filter)
        secondary_with_scores = secondary_store.similarity_search_with_score(query, fetch_k, filter=filter)

        # 合并候选文档
        merged_candidates = merge_query_results(primary_with_scores, secondary_with_scores)

        # 从合并的候选中选择多样性最好的k个文档
        # 这里简化处理：直接返回前k个高分文档
        # 如果需要严格的MMR，需要实现完整的MMR算法
        merged_docs = [doc for doc, score in merged_candidates[:k]]

        print(f"[混合MMR查询] 主库: {len(primary_docs)}条, 从库: {len(secondary_docs)}条, 合并后: {len(merged_docs)}条")
        return merged_docs

    except Exception as e:
        print(f"[混合MMR查询] 从库查询失败: {e}，仅使用主库结果")
        return primary_docs


# store_memory = {}

def async_thread(f):
    def wrapper(*args, **kwargs):
        t = Thread(target=f, args=args, kwargs=kwargs)
        t.start()

    return wrapper


def log_time(message, start_time=None):
    current = time.time()
    if start_time:
        elapsed = current - start_time
        print(f"[TIME] {message}: {elapsed:.4f}秒")
        return current
    return current


# 这里有待进行文档分割的各种方式的对比以及对于文档分割方法的进一步探索
# 这里使用text进行示例
# 对于embedding处理后的文档的存储方式等有待探索以进行改进
# 要清楚这里对于每一个文档仅仅进行一次分割
# 分割后的文档存进向量数据库里， 有一个问题是我们有时需要对分割的文档而不是对文档的向量存储进行处理，这里我们不可能再对分割后的文档进行单独存储
# 由于用户再退出之后文件和向量数据库依旧存在，所以这里只存储它们
# 等用户再次上线时，只需要针对文档和数据库进行加载即可。
# 这里还需要实现根据用户名对数据库的加载和文件的加载
# 加载后数据库的代理变量和文件分割后的（这里的content应该直接就在内存里，并不能确定存储方式）都存在store_memory里
# 用户每加载一个新文档要存储一次，用户推出后再次进来是另一次存储

def get_loader(file_path, enable_encoding_detection=None):
    """
    获取文档加载器，针对大文件进行了优化。

    优化点：
    1. PDF/DOCX 不需要编码检测（二进制格式）
    2. 仅对 TXT 文件进行编码检测，且仅读取文件头部（默认前64KB）
    3. 使用字典映射而非循环遍历
    4. 编码检测结果缓存，避免重复检测

    Args:
        file_path: 文件路径
        enable_encoding_detection: 是否强制进行编码检测。
            - None: 自动判断（仅TXT文件检测）
            - True: 强制检测（用于特殊情况）
            - False: 不检测

    Returns:
        加载器实例
    """
    # 获取文件后缀（不区分大小写）
    file_ext = None
    for ext in LOADER_MAPPING.keys():
        if file_path.lower().endswith(f".{ext}") or file_path.lower().endswith(ext):
            file_ext = ext
            break

    if not file_ext:
        raise ValueError(f"不支持的文件格式: {file_path}")

    loader_name, needs_detection = LOADER_MAPPING[file_ext]

    # 确定是否进行编码检测
    if enable_encoding_detection is None:
        should_detect = needs_detection
    else:
        should_detect = enable_encoding_detection

    # 仅对 TXT 文件进行编码检测
    encoding = None
    if should_detect and file_ext == "txt":
        # 检查缓存
        if file_path in _ENCODING_CACHE:
            encoding = _ENCODING_CACHE[file_path]
        else:
            try:
                # 优化：仅读取文件头部进行编码检测（而不是整个文件）
                with open(file_path, 'rb') as f:
                    # 只读取前 64KB 用于检测，大多数情况足够准确
                    raw_data = f.read(65536)
                    if raw_data:  # 确保文件非空
                        result = chardet.detect(raw_data)
                        encoding = result.get('encoding', 'utf-8')
                        if encoding is None:
                            encoding = 'utf-8'  # 默认 UTF-8
                # 缓存结果
                _ENCODING_CACHE[file_path] = encoding
            except Exception as e:
                print(f"编码检测失败 ({file_path}): {e}，使用默认编码 UTF-8")
                encoding = 'utf-8'
                _ENCODING_CACHE[file_path] = encoding

    # 返回对应的加载器
    if file_ext == "txt" and encoding:
        return TextLoader(file_path, encoding=encoding)
    else:
        return eval(loader_name)(file_path)


def _try_load_split_docs_from_ocr_raw(user_name: str, doc_name: str, file_path: str = None):
    """
    扫描件PDF在重启/重新加载时，pdf_type缓存可能丢失。
    这里改为：只要存在 {file_base}_ocr/{file_base}_raw.txt 就直接用它生成 split_docs。
    返回 split_docs(list[Document]) 或 None
    """
    try:
        fp = file_path or util.construct_file_path(user_name, doc_name)
        if not fp.lower().endswith(".pdf"):
            return None

        file_base = os.path.splitext(doc_name)[0]
        ocr_dir = os.path.join(os.path.dirname(fp), f"{file_base}_ocr")
        txt_path = os.path.join(ocr_dir, f"{file_base}_raw.txt")
        if not os.path.exists(txt_path):
            return None

        ocr_loader = TextLoader(txt_path, encoding='utf-8')
        ocr_docs = ocr_loader.load()
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)
        ocr_split_docs = text_splitter.split_documents(ocr_docs)

        for d in ocr_split_docs:
            if not d.metadata:
                d.metadata = {}
            d.metadata["source"] = fp
            d.metadata["file_path"] = fp
            d.metadata["type"] = "ocr_text"

        return ocr_split_docs
    except Exception as e:
        print(f"[_try_load_split_docs_from_ocr_raw] 失败: {user_name}/{doc_name}: {e}")
        return None


def save_hlscore_to_db_async(usr_name, realName, docs_name, content, base64_image):
    """异步保存HLScore到数据库"""
    import threading
    from zym.models import UserNotebook

    def _save_hlscore():
        try:
            HLScore = util.imageSum_2_HLScore(content, base64_image)
            book_name = usr_name[len(realName) + 1:]
            notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
            # 读取现有的JSON数据
            try:
                existing_data = json.loads(notebook.MayImgDocHLScore) if notebook.MayImgDocHLScore else {}
            except json.JSONDecodeError:
                existing_data = {}
            # 更新JSON数据 - HLScore会被正确编码，处理特殊字符，避免HLScore中有""或者:之类符号
            existing_data[docs_name] = HLScore
            notebook.MayImgDocHLScore = json.dumps(existing_data, ensure_ascii=False)
            notebook.save()
            print(f"[异步HLScore] 已保存 {docs_name} 的评分")
        except Exception as e:
            print(f"[异步HLScore] 保存失败: {e}")

    # 在后台线程中执行
    thread = threading.Thread(target=_save_hlscore)
    thread.daemon = True
    thread.start()


def process_document_pre_summary(realName, usr_name, docs_name):
    """
    处理文档预处理章节摘要
    返回：(success: bool, error_message: str)

    🔥 新增：先检查全局缓存文件夹 backend/pre_summary_cache/ 是否已有此文件的摘要，
    如果有则直接复用，不再调用大模型重新生成
    """
    try:
        from openai import OpenAI
        from zym.models import UserNotebook
        import os
        import hashlib

        # 获取文件路径
        file_path = util.construct_file_path(usr_name, docs_name)
        if not os.path.exists(file_path):
            return False, f"文件不存在: {file_path}"

        # 只处理PDF和TXT文件
        if not (docs_name.lower().endswith('.pdf') or docs_name.lower().endswith('.txt')):
            return False, "只支持PDF和TXT文件"

        # 🔥 全局缓存文件夹（在backend目录下）
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pre_summary_cache')
        os.makedirs(cache_dir, exist_ok=True)

        # 🔥 根据文件名+文件大小生成缓存键（只要文件名和大小相同就认为是同一文件）
        file_stat = os.stat(file_path)
        cache_key = f"{docs_name}_{file_stat.st_size}"
        cache_key_hash = hashlib.md5(cache_key.encode('utf-8')).hexdigest()[:12]

        # 缓存文件名：原文件名_hash.md
        file_base_name = os.path.splitext(docs_name)[0]
        file_ext = os.path.splitext(docs_name)[1][1:] if os.path.splitext(docs_name)[1] else ""
        cache_filename = f"{file_base_name}_{cache_key_hash}_Presummary_{file_ext}.md"
        cache_path = os.path.join(cache_dir, cache_filename)

        # 🔥 检查缓存是否存在
        if os.path.exists(cache_path):
            print(f"[文档预处理章节摘要] 🎯 在全局缓存中找到匹配的摘要文件: {cache_filename}")

            # 读取缓存内容
            with open(cache_path, 'r', encoding='utf-8') as f:
                cached_summary = f.read()

            # 复制到用户目录
            base_dir = f"./received_dir/user_raw_file/{usr_name}/pre_summary"
            os.makedirs(base_dir, exist_ok=True)
            user_summary_filename = f"{file_base_name}_Presummary_{file_ext}.md"
            user_summary_path = os.path.join(base_dir, user_summary_filename)

            with open(user_summary_path, 'w', encoding='utf-8') as f:
                f.write(cached_summary)

            print(f"[文档预处理章节摘要] ✅ 已从缓存复用摘要到: {user_summary_path}")
            return True, None

        # 加载文档内容
        # 🔥 检查是否是扫描件PDF，如果是则使用OCR结果文件
        all_docs = []
        if file_path.endswith("pdf"):
            file_key = f"{usr_name}/{docs_name}"
            pdf_type = global_var.get_pdf_type(file_key)

            # 如果未检测过，尝试检测
            if pdf_type is None:
                print(f"[文档预处理章节摘要] 对新PDF进行精确扫描件检测: {docs_name}")
                from llm_langchain.pdf_ocr_utils import check_pdf_type_by_word
                pdf_type = check_pdf_type_by_word(file_path)
                global_var.set_pdf_type(file_key, pdf_type)
                print(f"[文档预处理章节摘要] 检测结果: {pdf_type}")

            # 如果是扫描件，尝试使用OCR结果文件
            if pdf_type == 'scanned':
                file_base = os.path.splitext(docs_name)[0]
                ocr_dir = os.path.join(os.path.dirname(file_path), f"{file_base}_ocr")
                txt_path = os.path.join(ocr_dir, f"{file_base}_raw.txt")

                if os.path.exists(txt_path):
                    print(f"[文档预处理章节摘要] 检测到扫描件，使用OCR结果文件: {txt_path}")
                    from langchain.document_loaders import TextLoader
                    ocr_loader = TextLoader(txt_path, encoding='utf-8')
                    all_docs = ocr_loader.load()
                    print(f"[文档预处理章节摘要] OCR结果文件加载成功")
                else:
                    print(f"[文档预处理章节摘要] 扫描件但OCR结果文件不存在，使用原始PDF: {txt_path}")
                    loader = get_loader(file_path)
                    all_docs = loader.load()
            else:
                # 数字原生PDF，正常加载
                loader = get_loader(file_path)
                all_docs = loader.load()
        else:
            # 非PDF文件（TXT等），正常加载
            loader = get_loader(file_path)
            all_docs = loader.load()

        # 合并文档内容，并记录每段的页数信息
        full_content_parts = []
        current_page = None

        for doc in all_docs:
            page_num = None
            if doc.metadata and "page" in doc.metadata:
                page_num = doc.metadata["page"]
                if isinstance(page_num, int):
                    page_num = page_num + 1  # 转换为从1开始的页码

            content = doc.page_content.strip()
            if content:
                # 如果有页码信息，在内容前添加页码标记
                if page_num is not None:
                    full_content_parts.append(f"[页码：第{page_num}页]\n{content}")
                else:
                    full_content_parts.append(content)

        full_content = "\n\n".join(full_content_parts)

        # 🔥 限制文档内容长度，避免超过模型的最大上下文长度
        # deepseek-chat 最大上下文：131072 tokens
        # 🔥 重要：这里的“1.5”是【字符/Token】（200000字符≈133459 tokens → chars_per_token≈1.50）
        # 所以：可容纳字符数 ≈ tokens_budget * chars_per_token（不是除法）。
        CONTEXT_MAX_TOKENS = 131072
        COMPLETION_MAX_TOKENS = 4096
        RESERVED_TOKENS = 6500  # system_prompt + user_prompt前缀 + 额外安全边际（保守）
        CHARS_PER_TOKEN = 1.50  # 基于你提供的扫描件_raw.txt实测比例
        SAFETY_FACTOR = 0.90  # 给token估算误差留余量，尽可能多保留但避免400

        tokens_budget = max(0, CONTEXT_MAX_TOKENS - COMPLETION_MAX_TOKENS - RESERVED_TOKENS)
        MAX_CONTENT_LENGTH = int(tokens_budget * CHARS_PER_TOKEN * SAFETY_FACTOR)
        original_length = len(full_content)

        if len(full_content) > MAX_CONTENT_LENGTH:
            print(f"[文档预处理章节摘要] 文档内容过长 ({original_length} 字符)，将截取到 {MAX_CONTENT_LENGTH} 字符")
            # 尝试在段落边界截断
            truncated_content = full_content[:MAX_CONTENT_LENGTH]
            last_paragraph_end = truncated_content.rfind('\n\n')
            if last_paragraph_end > MAX_CONTENT_LENGTH * 0.85:
                full_content = full_content[:last_paragraph_end]
                print(f"[文档预处理章节摘要] 在段落边界截断，保留 {len(full_content)} 字符")
            else:
                full_content = truncated_content
                print(f"[文档预处理章节摘要] 在字符边界截断，保留 {MAX_CONTENT_LENGTH} 字符")

        # 计算文档总字数（支持中英文）
        # 中文按字符数统计，英文按单词数统计
        import re
        # 统计中文字符数（包括中文标点）
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', full_content))
        # 统计英文单词数（连续的字母、数字和常见符号组合）
        english_words = len(re.findall(r'\b[a-zA-Z0-9]+\b', full_content))
        # 总字数 = 中文字符数 + 英文单词数
        total_word_count = chinese_chars + english_words

        # 构建提示词
        system_prompt = """你是专业的文档分析专家，擅长对文档进行忠实原文的章节分段摘要。

你的任务是：
1. 仔细阅读并理解全文内容
2. 根据文档的结构特征进行章节分段
3. 为每个章节生成忠实原文的分段摘要

重要要求：
- 必须忠实原文，严禁自我发挥、杜撰或添加非原文明确写出的内容
- 如果原文有明确的章节结构或目录结构、大小标题等，一定要保持按原文的这些结构来切分章节，且应在对应的章节分段摘要中明确指出此部分涉及的章/节/小节等序号及名称
- 如果确信原文没有直接、明确的这些结构，则用深入理解后根据语义关联紧密性来分段，做智能分段
- 每段摘要必须包含以下三项，缺一不可：
  1. 内容主体：这段讲的内容主体是什么
  2. 核心要素：涉及的概念/想法/过程/观点/结论等是什么
  3. 页数：来自原文的页数（格式：[页码：第X页]）

格式要求：
- 两段章节分段摘要之间，用三个连字符"---"分隔
- 每段摘要内部不可以包含"---"符号
- 每段摘要要精准精炼但不丢失信息细节、包含全面，控制篇幅但必须包含上述三项内容
- 所有输出最多不超过2000字（对于字数较多达到数万字的文档），输出最合适的总字数应该随文档字数减少而减少，最好是能够满足“精准精炼、包含全面、不失细节”的尽量少的字数

输出格式示例：
[页码：第xx页-xx页] 内容主体：... 核心要素：... 
---
[页码：第xx页-xx页] 内容主体：... 核心要素：... 
---
..."""

        # 调用deepseek-chat API
        API_KEY = _public_config.secret('DEEPSEEK_API_KEY')
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://api.deepseek.com",
        )
        summary_content = None
        current_content = full_content
        # 静态字符截断仍可能因为中英混排/页码标记而低估 token；命中上下文 400 时再二次收缩重试。
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            # 每次根据当前内容重算字数提示，避免提示信息与实际内容不一致
            chinese_chars_try = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', current_content))
            english_words_try = len(re.findall(r'\b[a-zA-Z0-9]+\b', current_content))
            total_word_count_try = chinese_chars_try + english_words_try
            user_prompt = f"""请对以下文档进行章节分段摘要：

        文档全文总字数：{total_word_count_try}字/词（中文{chinese_chars_try}字，英文{english_words_try}词）

        {current_content}

        请严格按照所有要求，生成忠实原文的章节分段摘要，每段必须包含内容主体、核心要素和页数三项，段与段之间用---分隔。请根据文档总字数（{total_word_count_try}字/词）合理控制输出总篇幅，在满足"精准精炼、包含全面、不失细节"的前提下尽量精准精炼。"""
            try:
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,  # 较低温度确保忠实原文
                    max_tokens=4096,  # 根据文档长度调整
                )
                summary_content = (response.choices[0].message.content or "").strip()
                if summary_content:
                    break
                # 返回空内容也降载重试一次
                if attempt < max_attempts:
                    current_content = current_content[: max(1000, int(len(current_content) * 0.85))]
                    continue
            except Exception as call_e:
                msg = str(call_e)
                # 仅对上下文超限做自动收缩重试，其它异常沿用原行为
                if ("maximum context length" in msg or "requested" in msg) and attempt < max_attempts:
                    import re as _re
                    req_m = _re.search(r"requested\s+(\d+)\s+tokens", msg)
                    max_m = _re.search(r"maximum context length is\s+(\d+)\s+tokens", msg)
                    if req_m and max_m:
                        requested = max(1, int(req_m.group(1)))
                        allowed = max(1, int(max_m.group(1)))
                        # 预留安全余量，避免下一次再卡边界
                        shrink = max(0.50, min(0.92, (allowed / float(requested)) * 0.92))
                    else:
                        shrink = 0.75
                    new_len = max(1000, int(len(current_content) * shrink))
                    print(
                        f"[文档预处理章节摘要] 命中上下文上限，自动收缩重试 "
                        f"try={attempt}/{max_attempts} shrink={shrink:.3f} len={len(current_content)}->{new_len}"
                    )
                    current_content = current_content[:new_len]
                    # 优先在段落边界截断
                    para = current_content.rfind('\n\n')
                    if para > int(new_len * 0.80):
                        current_content = current_content[:para]
                    continue
                raise

        if not summary_content:
            raise RuntimeError("预处理摘要返回空内容")

        # 保存摘要到文件
        # 路径：received_dir/user_raw_file/用户名_本子名/pre_summary/原文件名_Presummary_文件类型.md
        realName_part = usr_name.split('_')[0] if '_' in usr_name else usr_name
        book_name_part = usr_name[len(realName_part) + 1:] if '_' in usr_name and len(usr_name) > len(
            realName_part) + 1 else ""

        base_dir = f"./received_dir/user_raw_file/{usr_name}/pre_summary"
        os.makedirs(base_dir, exist_ok=True)

        # 获取文件扩展名（去掉点）
        file_ext = os.path.splitext(docs_name)[1][1:] if os.path.splitext(docs_name)[1] else ""
        file_base_name = os.path.splitext(docs_name)[0]
        summary_filename = f"{file_base_name}_Presummary_{file_ext}.md"

        summary_path = os.path.join(base_dir, summary_filename)
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary_content)

        # 🔥 同时保存到全局缓存文件夹，供其他用户/本子复用
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                f.write(summary_content)
            print(f"[文档预处理章节摘要] 📦 已保存到全局缓存: {cache_filename}")
        except Exception as cache_e:
            print(f"[文档预处理章节摘要] ⚠️ 保存到全局缓存失败（不影响主流程）: {cache_e}")

        print(f"[文档预处理章节摘要] 成功处理文档 {docs_name}，摘要已保存到 {summary_path}")
        return True, None

    except Exception as e:
        error_msg = f"处理文档 {docs_name} 预处理章节摘要失败: {str(e)}"
        print(f"[文档预处理章节摘要] {error_msg}")
        import traceback
        traceback.print_exc()
        return False, error_msg


def process_pre_image_summary(usr_name, docs_name, pre_image_origin_path):
    """
    对PreImageOrigin_pdf.md进行智能分段摘要，生成PreImageSummary_pdf.md

    参数：
        usr_name: 用户名（格式：用户名_本子名）
        docs_name: 文档名
        pre_image_origin_path: PreImageOrigin_pdf.md的完整路径
    """
    try:
        from openai import OpenAI
        import os

        if not os.path.exists(pre_image_origin_path):
            print(f"[图片分析摘要] PreImageOrigin文件不存在: {pre_image_origin_path}")
            return False, "PreImageOrigin文件不存在"

        # 读取PreImageOrigin内容
        with open(pre_image_origin_path, 'r', encoding='utf-8') as f:
            origin_content = f.read()

        if not origin_content.strip():
            print(f"[图片分析摘要] PreImageOrigin文件为空: {pre_image_origin_path}")
            return False, "PreImageOrigin文件为空"

        # 限制内容长度（和pre_summary章节摘要一样）
        CONTEXT_MAX_TOKENS = 131072
        COMPLETION_MAX_TOKENS = 4096
        RESERVED_TOKENS = 6500
        CHARS_PER_TOKEN = 1.50
        SAFETY_FACTOR = 0.90

        tokens_budget = max(0, CONTEXT_MAX_TOKENS - COMPLETION_MAX_TOKENS - RESERVED_TOKENS)
        MAX_CONTENT_LENGTH = int(tokens_budget * CHARS_PER_TOKEN * SAFETY_FACTOR)

        if len(origin_content) > MAX_CONTENT_LENGTH:
            print(f"[图片分析摘要] 内容过长 ({len(origin_content)} 字符)，将截取到 {MAX_CONTENT_LENGTH} 字符")
            truncated_content = origin_content[:MAX_CONTENT_LENGTH]
            last_paragraph_end = truncated_content.rfind('\n\n')
            if last_paragraph_end > MAX_CONTENT_LENGTH * 0.85:
                origin_content = origin_content[:last_paragraph_end]
            else:
                origin_content = truncated_content

        # 构建提示词
        system_prompt = """你是专业的文档分析专家，擅长对图片分析结果进行智能分段摘要。

你的任务是：
1. 仔细阅读并理解所有图片的分析结果
2. 根据语义关联性进行自然自洽的分段
3. 为每个段落生成精准精炼的摘要

重要要求：
- 分段要语义上自然自洽，每段重点突出
- **必须显式保留关键的数据性信息**：如具体数值、统计数据、测量结果、实验数据等
- **必须显式保留关键的规律性信息**：如趋势、模式、关联关系、变化规律等
- **必须显式保留关键的结论性信息**：如核心发现、重要结论、关键判断等
- **必须具体而有综合价值**：避免泛泛而谈，要包含图片中的具体信息点，这些信息点应该对理解文档有实际价值
- 重要细节保留，尽可能少地丢失信息
- 精准精炼，控制篇幅
- 每段必须先按格式输出页数区间信息（格式：[页码：第X页] 或 [页码：第X页-X页]）
- 如果同一段涉及多页，使用页数区间格式

格式要求：
- 两段摘要之间，用三个连字符"---"分隔
- 每段摘要内部不可以包含"---"符号
- **每段摘要必须包含具体的数据、规律或结论信息，不能只是描述性文字**
- 每段摘要要精准精炼但不丢失信息细节、包含全面，控制篇幅但必须包含页数信息

输出格式示例：
[页码：第xx页] 内容摘要：...
---
[页码：第xx页-xx页] 内容摘要：...
---"""

        user_prompt = f"""请对以下图片分析结果进行智能分段摘要：

{origin_content}

请严格按照所有要求，生成智能分段摘要，每段必须包含页数信息，段与段之间用---分隔。分段要语义上自然自洽，每段重点突出，重要细节保留，尽可能少地丢失信息，精准精炼。

**特别强调**：每段摘要必须显式保留关键的数据性、规律性、结论性信息，要具体而有综合价值。不能只是泛泛描述"图片展示了xxx"，而要明确指出图片中的具体数据、规律、结论等有价值的信息点。"""

        # 调用deepseek-chat API
        API_KEY = _public_config.secret('DEEPSEEK_API_KEY')
        client = OpenAI(
            api_key=API_KEY,
            base_url="https://api.deepseek.com",
        )

        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=4096,
        )

        summary_content = response.choices[0].message.content.strip()

        # 保存摘要到文件
        # 路径：user_raw_file/用户名_本子名/pre_image_summary/文件名_PreImageSummary_pdf.md
        file_base_name = os.path.splitext(docs_name)[0]
        base_dir = f"./received_dir/user_raw_file/{usr_name}/pre_image_summary"
        os.makedirs(base_dir, exist_ok=True)

        summary_filename = f"{file_base_name}_PreImageSummary_pdf.md"
        summary_path = os.path.join(base_dir, summary_filename)

        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(summary_content)

        print(f"[图片分析摘要] 成功生成摘要: {summary_path}")
        return True, None

    except Exception as e:
        error_msg = f"处理图片分析摘要失败: {str(e)}"
        print(f"[图片分析摘要] {error_msg}")
        import traceback
        traceback.print_exc()
        return False, error_msg


def update_document_pre_summary_status(realName, book_name, docs_name, status):
    """
    更新文档预处理章节摘要状态到数据库
    status: True表示已完成，False表示未处理
    """
    try:
        from zym.models import UserNotebook
        import json

        notebook = UserNotebook.objects.get(username=realName, bookName=book_name)

        # 读取现有的JSON数据
        try:
            existing_data = json.loads(notebook.documentPreSummaryStatus) if notebook.documentPreSummaryStatus else {}
        except json.JSONDecodeError:
            existing_data = {}

        # 更新状态
        existing_data[docs_name] = status

        # 保存回数据库
        notebook.documentPreSummaryStatus = json.dumps(existing_data, ensure_ascii=False)
        notebook.save()

        print(f"[更新文档预处理状态] {docs_name}: {status}")

    except Exception as e:
        print(f"[更新文档预处理状态] 失败: {e}")


# 全局处理锁和正在处理的文档集合，防止重复处理
_pre_summary_processing_lock = RLock()
_pre_summary_processing_set = set()


def process_documents_pre_summary_batch(realName, book_name, usr_name, doc_list):
    """
    批量处理文档预处理章节摘要（3并发，防重复）
    doc_list: 需要处理的文档名列表
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # 过滤出需要处理的文档（排除正在处理的）
    with _pre_summary_processing_lock:
        to_process = []
        for doc_name in doc_list:
            # 只处理PDF和TXT文件
            if not (doc_name.lower().endswith('.pdf') or doc_name.lower().endswith('.txt')):
                continue
            # 检查是否正在处理
            doc_key = f"{usr_name}_{doc_name}"
            if doc_key not in _pre_summary_processing_set:
                to_process.append(doc_name)
                _pre_summary_processing_set.add(doc_key)

    if not to_process:
        print(f"[批量文档预处理] 没有需要处理的文档")
        return

    print(f"[批量文档预处理] 开始处理 {len(to_process)} 个文档（每文档：PreSummary → Skill）")

    def process_single_doc(doc_name):
        """处理单个文档：先 PreSummary，再触发 Skill。"""
        doc_key = f"{usr_name}_{doc_name}"
        presummary_ok = False
        try:
            # 先将状态设为false（如果还没有）
            update_document_pre_summary_status(realName, book_name, doc_name, False)

            print(f"[批量文档预处理] 开始 PreSummary: {doc_name}")
            success, error_msg = process_document_pre_summary(realName, usr_name, doc_name)

            if success:
                update_document_pre_summary_status(realName, book_name, doc_name, True)
                presummary_ok = True
                print(f"[批量文档预处理] ✅ PreSummary 完成: {doc_name}")
            else:
                print(f"[批量文档预处理] ❌ PreSummary 失败，仍将生成 Skill: {doc_name}, 错误: {error_msg}")

        except Exception as e:
            print(f"[批量文档预处理] ❌ PreSummary 异常，仍将生成 Skill: {doc_name}, 错误: {str(e)}")
        finally:
            # PreSummary 结束后再生成 Skill（与新上传路径一致）
            try:
                from app_chat import skills_store as skills_store
                from app_chat.skill_generate import spawn_document_skill_async
                if skills_store.find_skill_by_source_doc(usr_name, doc_name):
                    print(f"[批量文档预处理] 已有 Skill，跳过生成: {doc_name}")
                else:
                    print(f"[批量文档预处理] 触发 Skill 生成: {doc_name} (presummary_ok={presummary_ok})")
                    spawn_document_skill_async(realName, usr_name, doc_name)
            except Exception as _sk_e:
                print(f"[批量文档预处理] Skill 启动失败: {doc_name}, {_sk_e}")
            with _pre_summary_processing_lock:
                _pre_summary_processing_set.discard(doc_key)

    # 使用线程池，最多3个并发
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_single_doc, doc_name): doc_name for doc_name in to_process}

        # 等待所有任务完成
        for future in as_completed(futures):
            doc_name = futures[future]
            try:
                future.result()  # 获取结果，如果有异常会抛出
            except Exception as e:
                print(f"[批量文档预处理] 任务异常: {doc_name}, {str(e)}")

    print(f"[批量文档预处理] 批量处理完成")


def save_document_four_color_dmt_to_db_async(usr_name, realName, docs_name, document_attributes):
    """异步保存文档四色DMT属性到数据库"""
    import threading
    from zym.models import UserNotebook

    def _save_four_color_dmt():
        try:
            book_name = usr_name[len(realName) + 1:] if len(usr_name) > len(realName) else None
            if not book_name:
                print(f"[异步四色DMT] 无法从usr_name解析bookName: usr_name={usr_name}, realName={realName}")
                return

            notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
            # 读取现有的JSON数据
            try:
                existing_data = json.loads(notebook.documentFourColorDMT) if notebook.documentFourColorDMT else {}
            except json.JSONDecodeError:
                existing_data = {}

            # 更新JSON数据：合并写入，避免新增作业属性或人工修改字段被覆盖
            current_attrs = existing_data.get(docs_name, {}) if isinstance(existing_data.get(docs_name, {}), dict) else {}
            for key in ('main_four_color', 'secondary_four_color', 'dmt_level'):
                value = document_attributes.get(key, '')
                if value or key not in current_attrs:
                    current_attrs[key] = value
            for key in (
                'is_k12_homework', 'is_homework_pdf', 'homework_subject', 'homework_stage',
                'homework_confidence', 'homework_reason', 'homework_checked_at', 'homework_analyzer_version'
            ):
                if key in document_attributes:
                    current_attrs[key] = document_attributes.get(key)
            existing_data[docs_name] = current_attrs
            notebook.documentFourColorDMT = json.dumps(existing_data, ensure_ascii=False)
            notebook.save()
            print(f"[异步四色DMT] 已保存文档 {docs_name} 的四色DMT属性到数据库")
        except Exception as e:
            print(f"[异步四色DMT] 保存失败: {e}")

    # 在后台线程中执行
    thread = threading.Thread(target=_save_four_color_dmt)
    thread.daemon = True
    thread.start()


def get_split_docs_vectors(realName, usr_name, docs_name, task_id, process_images=True):
    """
    处理文档分割和向量化
    process_images: 是否处理图片，False时只处理文本部分（用于两段式处理）
    """
    # global store_memory
    # lock[usr_name].acquire()
    begin_time = time.time()
    file_path = util.construct_file_path(usr_name, docs_name)
    split_docs, base_64_out = [], []
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)  # 不根据模型大小限制分割大小，而是提供更多文档。
    # text_splitter = RecursiveCharacterTextSplitter(
    #     chunk_size=500,  # 目标块大小
    #     chunk_overlap=50,  # 块间重叠大小
    #     separators=["\n\n", "\n", "。", "！", "？", "．", " ", ""]  # 分割优先级
    # )
    if file_path.endswith("png") or file_path.endswith("jpg") or file_path.endswith("jpeg"):
        try:
            base64_image = util.encode_image(file_path)
            base_64_out.append(base64_image)
            content = util.summarize_image(file_path, user_name=usr_name)

            # 出红蓝卡标并保存数据库
            from zym.models import UserNotebook
            # HLScore = util.imageSum_2_HLScore(content, base64_image)
            # book_name = usr_name[len(realName) + 1:]  # 去掉 "用户名_" 部分
            # notebook = UserNotebook.objects.get(username=realName, bookName=book_name)
            # # 读取现有的JSON数据
            # try:
            #     existing_data = json.loads(notebook.MayImgDocHLScore) if notebook.MayImgDocHLScore else {}
            # except json.JSONDecodeError:
            #     existing_data = {}
            # # 更新JSON数据 - HLScore会被正确编码，处理特殊字符，避免HLScore中有""或者:之类符号
            # existing_data[docs_name] = HLScore
            # notebook.MayImgDocHLScore = json.dumps(existing_data, ensure_ascii=False)
            # notebook.save()
            # 异步保存HLScore到数据库
            save_hlscore_to_db_async(usr_name, realName, docs_name, content, base64_image)

            split_docs = text_splitter.split_documents([
                Document(
                    page_content=content,
                    metadata={
                        "source": file_path,  # type: ignore[attr-defined]
                        "file_path": file_path,  # type: ignore[attr-defined]
                        "page": 0,
                        "total_pages": 0,
                        "type": "image",
                        "seq": 1,
                    },
                )])

            # 🔥 对图片文档进行四色主辅色和DMT分析
            document_attributes = {
                'main_four_color': '',
                'secondary_four_color': '',
                'dmt_level': ''
            }
            try:
                # 分析图片的文本摘要内容
                import threading
                analysis_result = {}
                analysis_complete = threading.Event()

                def analyze_image_document_async():
                    try:
                        from app_chat.document_analyzer import analyze_document_attributes
                        # result = analyze_document_attributes(content)
                        from app_chat.scene_context_helper import get_scene_info_from_username

                        # 🔥 获取场景信息
                        scene_name, sub_scene_name, scene_summary, notebook_desc = get_scene_info_from_username(
                            usr_name)

                        result = analyze_document_attributes(
                            content,
                            scene_name=scene_name,
                            sub_scene_name=sub_scene_name,
                            scene_summary=scene_summary,
                            notebook_description=notebook_desc
                        )
                        analysis_result.update(result)
                        print(
                            f"[get_split_docs_vectors] 图片文档分析完成: 主色={result.get('main_four_color')}, 辅色={result.get('secondary_four_color')}, DMT={result.get('dmt_level')}")
                    except Exception as e:
                        print(f"[get_split_docs_vectors] 图片文档分析失败: {e}")
                    finally:
                        analysis_complete.set()

                # 启动后台线程进行分析
                analysis_thread = threading.Thread(target=analyze_image_document_async, daemon=True)
                analysis_thread.start()

                # 等待分析完成（最多等待30秒）
                if analysis_complete.wait(timeout=30):
                    document_attributes = analysis_result
            except Exception as e:
                print(f"[get_split_docs_vectors] 图片文档分析初始化失败: {e}")

            # 🔥 将分析结果添加到图片文档的metadata中
            for doc in split_docs:
                if not doc.metadata:
                    doc.metadata = {}
                doc.metadata['main_four_color'] = document_attributes.get('main_four_color', '')
                doc.metadata['secondary_four_color'] = document_attributes.get('secondary_four_color', '')
                doc.metadata['dmt_level'] = document_attributes.get('dmt_level', '')

            # 🔥 异步保存图片文档的四色DMT属性到数据库
            if document_attributes.get('main_four_color') or document_attributes.get('dmt_level'):
                save_document_four_color_dmt_to_db_async(usr_name, realName, docs_name, document_attributes)

            global_var.set_task_current_page(task_id, 1)
        except Exception as e:
            print("解析图片时发生了一些错误:", e)
            lock[usr_name].release()
            return [], []
    else:
        # pdf_file_path = "./attention is all you need.pdf"
        loader = get_loader(file_path)
        # 这里分割后文档metadata为loader使用的file_path
        split_docs = text_splitter.split_documents(loader.load())

        # 🔥 对文档进行四色主辅色和DMT分析（一个文档做一次分析）
        document_attributes = {
            'main_four_color': '',
            'secondary_four_color': '',
            'dmt_level': ''
        }
        try:
            # 合并所有segment的完整内容作为文档整体内容
            full_content = "\n".join([doc.page_content for doc in split_docs])

            # 分析文档属性（在后台线程中进行，不阻塞主流程）
            import threading
            analysis_result = {}
            analysis_complete = threading.Event()

            def analyze_document_async():
                try:
                    from app_chat.document_analyzer import analyze_document_attributes
                    # result = analyze_document_attributes(full_content)
                    from app_chat.scene_context_helper import get_scene_info_from_username

                    # 🔥 获取场景信息
                    scene_name, sub_scene_name, scene_summary, notebook_desc = get_scene_info_from_username(usr_name)

                    result = analyze_document_attributes(
                        full_content,
                        scene_name=scene_name,
                        sub_scene_name=sub_scene_name,
                        scene_summary=scene_summary,
                        notebook_description=notebook_desc
                    )
                    if docs_name.lower().endswith('.pdf'):
                        from app_chat.homework_classifier import analyze_homework_document_attributes
                        result.update(analyze_homework_document_attributes(
                            full_content,
                            docs_name,
                            scene_name=scene_name,
                            sub_scene_name=sub_scene_name,
                            scene_summary=scene_summary,
                            notebook_description=notebook_desc,
                            pdf_path=file_path,
                            allow_vision_fallback=False
                        ))
                    analysis_result.update(result)
                    print(
                        f"[get_split_docs_vectors] 文档分析完成: 主色={result.get('main_four_color')}, 辅色={result.get('secondary_four_color')}, DMT={result.get('dmt_level')}")
                except Exception as e:
                    print(f"[get_split_docs_vectors] 文档分析失败: {e}")
                finally:
                    analysis_complete.set()

            # 启动后台线程进行分析
            analysis_thread = threading.Thread(target=analyze_document_async, daemon=True)
            analysis_thread.start()

            # 等待分析完成（最多等待30秒，避免阻塞太久）
            if analysis_complete.wait(timeout=30):
                document_attributes = analysis_result
            else:
                print(f"[get_split_docs_vectors] 文档分析超时，使用默认值")

        except Exception as e:
            print(f"[get_split_docs_vectors] 文档分析初始化失败: {e}")

        # 🔥 将分析结果添加到所有segment的metadata中
        for doc in split_docs:
            if not doc.metadata:
                doc.metadata = {}
            doc.metadata['main_four_color'] = document_attributes.get('main_four_color', '')
            doc.metadata['secondary_four_color'] = document_attributes.get('secondary_four_color', '')
            doc.metadata['dmt_level'] = document_attributes.get('dmt_level', '')
            for key in (
                'is_k12_homework', 'is_homework_pdf', 'homework_subject', 'homework_stage',
                'homework_confidence', 'homework_reason', 'homework_checked_at', 'homework_analyzer_version'
            ):
                if key in document_attributes:
                    doc.metadata[key] = document_attributes.get(key)

        # 🔥 异步保存文档的四色DMT属性到数据库
        if document_attributes.get('main_four_color') or document_attributes.get('dmt_level') or document_attributes.get('homework_checked_at'):
            save_document_four_color_dmt_to_db_async(usr_name, realName, docs_name, document_attributes)

        # 🔥 为每个segment的content添加页号信息（如果metadata中有page信息）
        for doc in split_docs:
            if doc.metadata and "page" in doc.metadata:
                page_num = doc.metadata["page"]
                # 页号从0开始，转换为从1开始的页码
                page_display = page_num + 1 if isinstance(page_num, int) else page_num
                # 在content开头添加页号标记
                if not doc.page_content.strip().startswith("[页码："):
                    doc.page_content = f"[页码：第{page_display}页]\n{doc.page_content}"

        # print(split_docs)
        if file_path.endswith("pdf"):
            # 🔥 新上传的PDF文档：进行精确的扫描件检测并缓存
            file_key = f"{usr_name}/{docs_name}"
            cached_type = global_var.get_pdf_type(file_key)

            if cached_type is None:
                # 未缓存，使用新方法检测
                print(f"[PDF上传] 对新PDF进行精确扫描件检测: {docs_name}")
                from llm_langchain.pdf_ocr_utils import check_pdf_type_by_word
                pdf_type = check_pdf_type_by_word(file_path)
                global_var.set_pdf_type(file_key, pdf_type)
                print(f"[PDF上传] 检测结果: {pdf_type}")
            else:
                print(f"[PDF上传] 使用缓存的检测结果: {cached_type}")

            # 🔥 改造：将OCR识别、提取保存图片、生成布局PDF、markdown转PDF改为同步操作
            pdf_type = global_var.get_pdf_type(file_key)
            is_scanned = (pdf_type == 'scanned')
            ocr_txt_path = None  # 🔥 保存OCR文本文件路径

            if is_scanned:
                print(f"[PDF处理] 检测到扫描件，开始同步处理...")
                from llm_langchain.pdf_ocr_utils import run_remote_ocr, md_to_pdf, extract_and_save_images_from_ocr, generate_layout_pdf

                try:
                    # 1. 执行OCR识别
                    file_base = os.path.splitext(docs_name)[0]
                    ocr_dir = os.path.join(os.path.dirname(file_path), f"{file_base}_ocr")
                    print(f"[PDF处理] 开始OCR识别...")
                    ocr_success, md_path_dict, txt_path = run_remote_ocr(file_path, ocr_dir)
                    md_origin_path = md_path_dict.get('md_origin_path', None)
                    md_path = md_path_dict.get('md_path', None)

                    if not ocr_success or not txt_path:
                        print(f"[PDF处理] OCR识别失败")
                    else:
                        ocr_txt_path = txt_path  # 🔥 保存OCR文本文件路径
                        # 2. 提取并保存图片
                        print("[PDF处理] OCR成功，开始提取并保存图片...")
                        image_dir = file_path[:-4] + "_image/"
                        extract_success, image_count, image_output_dir = extract_and_save_images_from_ocr(
                            file_path, txt_path, image_dir
                        )

                        if extract_success:
                            print(f"[PDF处理] 图片提取成功，共保存 {image_count} 张图片到: {image_output_dir}")
                        else:
                            print("[PDF处理] 图片提取失败")

                        # 3. 生成版面布局PDF
                        print("[PDF处理] 开始生成版面布局PDF...")
                        layout_pdf_path = os.path.join(ocr_dir, f"{file_base}_layouts.pdf")
                        layout_success, generated_path = generate_layout_pdf(file_path, txt_path, layout_pdf_path)
                        if layout_success and os.path.exists(layout_pdf_path):
                            print(f"[PDF处理] 版面布局PDF生成成功: {layout_pdf_path}")
                        else:
                            print("[PDF处理] 版面布局PDF生成失败")

                        # 4. 将markdown转换为可处理的PDF
                        print("[PDF处理] 检测到扫描件，尝试将OCR的markdown转换为PDF...")
                        origin_converted_pdf_path = os.path.join(ocr_dir, f"{file_base}_origin_converted.pdf")
                        conversion_success_1 = md_to_pdf(md_origin_path, origin_converted_pdf_path)
                        processed_converted_pdf_path = os.path.join(ocr_dir, f"{file_base}_converted.pdf")
                        conversion_success_2 = md_to_pdf(md_path, processed_converted_pdf_path)

                        if conversion_success_1 and conversion_success_2 \
                            and os.path.exists(origin_converted_pdf_path) \
                                and os.path.exists(processed_converted_pdf_path):
                            print(f"[PDF处理] Markdown转PDF成功")
                        else:
                            print("[PDF处理] Markdown转PDF失败")
                except Exception as e:
                    print(f"[PDF处理] OCR处理出错: {e}")
            else:
                print(f"[PDF处理] 检测到数字原生PDF，跳过OCR处理")

            if is_scanned:
                try:
                    from app_chat.homework_classifier import analyze_homework_document_attributes, extract_existing_ocr_text_sample
                    from app_chat.scene_context_helper import get_scene_info_from_username

                    scene_name, sub_scene_name, scene_summary, notebook_desc = get_scene_info_from_username(usr_name)
                    current_full_content = full_content if 'full_content' in locals() else "\n".join([doc.page_content for doc in split_docs])
                    ocr_content, ocr_source = extract_existing_ocr_text_sample(file_path)
                    homework_attrs = analyze_homework_document_attributes(
                        ocr_content or current_full_content,
                        docs_name,
                        scene_name=scene_name,
                        sub_scene_name=sub_scene_name,
                        scene_summary=scene_summary,
                        notebook_description=notebook_desc,
                        pdf_path=file_path,
                    )
                    document_attributes.update(homework_attrs)
                    save_document_four_color_dmt_to_db_async(usr_name, realName, docs_name, document_attributes)
                    print(
                        f"[PDF处理] 扫描件作业属性已刷新: OCR来源={ocr_source or '无'}, "
                        f"is_homework={homework_attrs.get('is_homework_pdf')}, "
                        f"subject={homework_attrs.get('homework_subject')}"
                    )
                except Exception as e:
                    print(f"[PDF处理] 刷新扫描件作业属性失败: {e}")

            # 🔥 OCR完成后，如果是扫描件且OCR成功，用OCR结果更新split_docs
            if is_scanned and ocr_txt_path and os.path.exists(ocr_txt_path):
                try:
                    print(f"[PDF处理] 扫描件OCR成功，使用OCR结果更新split_docs: {ocr_txt_path}")
                    print(f"[PDF处理] 当前split_docs状态: len={len(split_docs) if split_docs else 0}, 将替换为OCR结果")
                    # 使用TextLoader加载OCR文本文件
                    ocr_loader = TextLoader(ocr_txt_path, encoding='utf-8')
                    ocr_docs = ocr_loader.load()
                    # 分割OCR文档
                    ocr_split_docs = text_splitter.split_documents(ocr_docs)
                    # 更新metadata，确保包含原始文件信息
                    for doc in ocr_split_docs:
                        if not doc.metadata:
                            doc.metadata = {}
                        doc.metadata["source"] = file_path
                        doc.metadata["file_path"] = file_path
                        doc.metadata["type"] = "ocr_text"
                        # 添加四色DMT属性（使用已分析的document_attributes）
                        doc.metadata['main_four_color'] = document_attributes.get('main_four_color', '')
                        doc.metadata['secondary_four_color'] = document_attributes.get('secondary_four_color', '')
                        doc.metadata['dmt_level'] = document_attributes.get('dmt_level', '')
                        for key in (
                            'is_k12_homework', 'is_homework_pdf', 'homework_subject', 'homework_stage',
                            'homework_confidence', 'homework_reason', 'homework_checked_at', 'homework_analyzer_version'
                        ):
                            if key in document_attributes:
                                doc.metadata[key] = document_attributes.get(key)
                    # 替换split_docs
                    split_docs = ocr_split_docs
                    print(f"[PDF处理] OCR结果已更新到split_docs，共 {len(split_docs)} 个文档片段")
                except Exception as e:
                    print(f"[PDF处理] 使用OCR结果更新split_docs失败: {e}")
                    import traceback
                    traceback.print_exc()

            global_var.set_task_current_page(task_id, 1)
        else:
            global_var.set_task_current_page(task_id, 1)
    print(f"处理文件耗时: {time.time()-begin_time}")
    begin_time = time.time()
    ids = util.construct_ids(file_path, len(split_docs))  # ids = 其实可以由docs_name + 顺序组成 # 另一个问题是顺序也可以由meta_data得到

    # 🔥 修复方案1（改进版）：智能检测数据库路径，兼容新旧结构
    actual_db_path, db_type, secondary_db_path = get_user_db_path(usr_name)

    collection_name = util.construct_collection(usr_name)
    vector_store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=actual_db_path  # 🔥 使用智能检测的路径
    )
    print(f"[INFO] 用户 {usr_name} 数据库类型: {db_type}, 路径: {actual_db_path}")
    print(f"Chroma准备时长: {time.time()-begin_time}")
    # 已经找到了问题所在
    # 使用add与from的问题在于当时使用from没有指定path和collection_name，所以是新生成的
    # 而add使用前先指定了db_path与collection_name导致使用的是原来的且每次都新进行添加所以出现了问题
    # 因此这里直接指定add是不会出现问题的，只需要不进行重复调用
    # ids是id的list包括可能之后删除也是idlist
    # print(len(split_docs))
    # print(split_docs)
    # split_docs_s = []
    # 🔥 修复方案4：优化批次大小，减少数据库写入次数
    BATCH_SIZE = 100  # 从55增加到100
    n_add = len(split_docs) // BATCH_SIZE
    # n_add = len(split_docs) // 166
    global_var.set_task_total_items(task_id, len(split_docs))
    global_var.set_task_current_item(task_id, 0)
    print("当前任务进度：", task_id, "项数：", global_var.tasks.get(task_id).get("current_item", -1), "/", len(split_docs))

    # 并行处理向量存储
    def add_documents_batch(batch_data):
        """添加文档批次的函数"""
        batch_idx, docs_batch, ids_batch, vector_store, max_retries = batch_data
        for retry in range(max_retries):
            try:
                vector_store.add_documents(documents=docs_batch, ids=ids_batch)
                print(f"Chroma准备+处理add_documents批次{batch_idx}完成，总共时长: {time.time() - begin_time}")
                time.sleep(1)
                return True, batch_idx
            except (requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ConnectionError,
                    Exception) as e:
                print(f"添加文档批次 {batch_idx} 第 {retry + 1} 次尝试失败: {e}")
                if retry < max_retries - 1:
                    time.sleep(2 ** retry)  # 指数退避
                else:
                    print(f"批次 {batch_idx} 所有重试都失败了，跳过此批次")
                    return False, batch_idx

    # 准备批次数据
    max_retries = 3
    batch_data_list = []

    # 主要批次
    for i in range(n_add):
        batch_data = (
            i,
            split_docs[i * BATCH_SIZE:(i + 1) * BATCH_SIZE],  # 🔥 使用新的批次大小
            ids[i * BATCH_SIZE:(i + 1) * BATCH_SIZE],
            vector_store,
            max_retries
        )
        batch_data_list.append(batch_data)

    # 剩余文档批次
    if n_add * BATCH_SIZE < len(split_docs):
        batch_data = (
            n_add,
            split_docs[n_add * BATCH_SIZE:len(split_docs)],  # 🔥 使用新的批次大小
            ids[n_add * BATCH_SIZE:len(split_docs)],
            vector_store,
            max_retries
        )
        batch_data_list.append(batch_data)

    # 🔥 修复方案3：降低内部并行度，减少峰值负载（4->3）
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for batch_data in batch_data_list:
            future = executor.submit(add_documents_batch, batch_data)
            futures.append(future)

        # 等待所有批次完成并更新进度
        completed_batches = 0
        for future in futures:
            try:
                success, batch_idx = future.result()
                completed_batches += 1
                global_var.set_task_current_item(task_id, completed_batches * BATCH_SIZE)  # 🔥 使用新的批次大小
                print("当前任务进度：", task_id, "项数：", global_var.tasks.get(task_id).get("current_item", -1), "/",
                      len(split_docs))
            except Exception as e:
                print(f"批次处理异常: {e}")

    global_var.set_task_current_item(task_id, len(split_docs))
    print("当前任务进度：", task_id, "项数：", global_var.tasks.get(task_id).get("current_item", -1), "/", len(split_docs))
    # vector_store.add_documents(documents=split_docs, ids=ids)
    global_var.set_user_split(usr_name, docs_name, split_docs)
    if len(base_64_out) != 0:
        global_var.set_user_image(usr_name, docs_name, base_64_out)
    global_var.set_user_vector(usr_name, vector_store)
    global_var.add_split_file(usr_name, docs_name)
    # lock[usr_name].release()

    # 异步后台任务：文档置信度评估
    def async_assess_confidence():
        try:
            if split_docs and len(split_docs) > 0:
                # 提取文档的前、中、后部分内容用于置信度评估
                total_docs = len(split_docs)
                sample_docs = []

                # 取前3个、中间1个、后3个文档片段
                if total_docs >= 7:
                    sample_docs = split_docs[:3] + split_docs[total_docs // 2:total_docs // 2 + 1] + split_docs[-3:]
                elif total_docs >= 3:
                    sample_docs = split_docs[:2] + split_docs[-1:]
                else:
                    sample_docs = split_docs

                # 拼接样本内容
                sample_content = "\n".join([doc.page_content for doc in sample_docs])
                # 限制长度，避免过长
                if len(sample_content) > 2000:
                    sample_content = sample_content[:2000] + "..."

                # 调用8卡服务器进行置信度评估
                confidence_assessment = assess_document_confidence(usr_name, sample_content)

                # 将置信度评分存储到文档metadata中
                for doc in split_docs:
                    doc.metadata['confidence_score'] = confidence_assessment.get('confidence_score', 2.0)
                    doc.metadata['confidence_assessment_time'] = confidence_assessment.get('assessment_time', 0)

                print(f"[异步] 文档置信度评估完成: {confidence_assessment.get('confidence_score', 2.0)}分")
            else:
                print("[异步] 文档为空，跳过置信度评估")
        except Exception as e:
            print(f"[异步] 文档置信度评估失败: {str(e)}")

    # 启动异步线程
    Thread(target=async_assess_confidence).start()
    print("文档置信度评估已在后台启动")

    # store_memory[usr_name]["split_docs"][docs_name] = split_docs
    # store_memory[usr_name]["vector_store"] = vector_store
    # query = "What is attention"
    # docs = vector_store.similarity_search(query)
    # print(docs[0].page_content) #得到的文档调用page_content得到内容
    print(f"向量数据库耗时: {time.time() - begin_time}")
    return split_docs, vector_store


def process_pdf_images_async(realName, usr_name, docs_name, task_id):
    """
    异步处理PDF图片分析（已简化）

    说明：OCR识别、图片提取、版面布局PDF生成、Markdown转PDF等操作
    已移到同步的 get_split_docs_vectors 函数中执行

    此函数现在仅负责：
    1. 提取并生成图片的Document对象和base64编码
    2. 更新向量库
    """
    import threading
    import time

    def _process_images():
        try:
            print(f"[异步图片处理] 开始处理 {docs_name} 的图片...")
            file_path = util.construct_file_path(usr_name, docs_name)

            # 检查是否已经有OCR生成的图片
            from llm_langchain.pdf_ocr_utils import muExtractImages_with_ocr

            file_base = os.path.splitext(docs_name)[0]
            ocr_dir = os.path.join(os.path.dirname(file_path), f"{file_base}_ocr")
            txt_path = os.path.join(ocr_dir, f"{file_base}_raw.txt")

            # 优先使用OCR结果的已保存图片（扫描件）
            if os.path.exists(txt_path):
                print("[异步图片处理] 使用OCR结果的已保存图片生成文档对象...")
                docs_out, base_64_out = muExtractImages_with_ocr(
                    file_path,
                    txt_path,
                    usr_name,
                    realName,
                    task_id=task_id,
                    real_time_update=True
                )
            else:
                # OCR文件不存在（数字原生PDF），直接从PDF提取图片
                print("[异步图片处理] OCR文件不存在（数字原生PDF），直接从PDF中提取图片...")
                docs_out, base_64_out = util.muExtractImages(
                    file_path,
                    usr_name=usr_name,
                    realName=realName,
                    task_id=task_id,
                    real_time_update=True
                )
                if docs_out:
                    print(f"[异步图片处理] 从数字原生PDF中提取到 {len(docs_out)} 张图片")
                else:
                    print("[异步图片处理] 未从PDF中提取到图片")

            if docs_out:
                print(f"[异步图片处理] 图片处理完成，共 {len(docs_out)} 张图片")

                # 智能检测数据库路径，兼容新旧结构
                actual_db_path, db_type, secondary_db_path = get_user_db_path(usr_name)

                collection_name = util.construct_collection(usr_name)
                vector_store = Chroma(
                    collection_name=collection_name,
                    embedding_function=embeddings,
                    persist_directory=actual_db_path
                )
                print(f"[INFO] 异步图片处理数据库类型: {db_type}, 路径: {actual_db_path}")

                # 获取现有文档
                existing_docs = global_var.get_user_split(usr_name, docs_name)
                if existing_docs is None:
                    existing_docs = []

                # 为图片提取的文档添加页号信息
                for doc in docs_out:
                    if doc.metadata and "page" in doc.metadata:
                        page_num = doc.metadata["page"]
                        page_display = page_num + 1 if isinstance(page_num, int) else page_num
                        if not doc.page_content.strip().startswith("[页码："):
                            doc.page_content = f"[页码：第{page_display}页]\n{doc.page_content}"

                # 合并图片文档
                all_docs = existing_docs + docs_out
                global_var.set_user_split(usr_name, docs_name, all_docs)

                # 更新图片数据
                if base_64_out:
                    global_var.set_user_image(usr_name, docs_name, base_64_out)
                    print(f"[异步图片处理] 已更新图片数据，共 {len(base_64_out)} 张图片")

                # 重新构建ID并添加到向量库
                file_path = util.construct_file_path(usr_name, docs_name)
                ids = util.construct_ids(file_path, len(all_docs))

                # 添加图片文档到向量库
                n_add = len(docs_out) // 166
                for i in range(n_add):
                    start_idx = len(existing_docs) + i * 166
                    end_idx = len(existing_docs) + (i + 1) * 166
                    vector_store.add_documents(
                        documents=docs_out[i * 166:(i + 1) * 166],
                        ids=ids[start_idx:end_idx]
                    )
                vector_store.add_documents(
                    documents=docs_out[n_add * 166:len(docs_out)],
                    ids=ids[len(existing_docs) + n_add * 166:len(existing_docs) + len(docs_out)]
                )

                global_var.set_user_vector(usr_name, vector_store)
                print(f"[异步图片处理] {docs_name} 图片处理完成并已更新向量库")
            else:
                print(f"[异步图片处理] 未找到图片数据，跳过向量库更新")

        except Exception as e:
            print(f"[异步图片处理] 处理 {docs_name} 图片时出错: {e}")
            import traceback
            traceback.print_exc()

    # 在后台线程中执行
    thread = threading.Thread(target=_process_images)
    thread.daemon = True
    thread.start()


def count_db_folders():
    """
    统计 received_dir/user_db_file 下的文件夹数量
    """
    import os

    db_path = "./received_dir/user_db_file"
    if not os.path.exists(db_path):
        return 0

    folders = [item for item in os.listdir(db_path)
               if os.path.isdir(os.path.join(db_path, item)) and item != '__pycache__']

    return len(folders)


def delete_notebook_vectors_precise(usr_name, book_name):
    """
    精确删除指定本子的向量数据
    文件夹结构: ./received_dir/user_raw_file/{username}_{bookname}/
    文档ID格式: ./received_dir/user_raw_file/{username}_{bookname}/{filename}_{序号}
    """
    try:
        # 统计删除前的文件夹数量
        folders_before = count_db_folders()
        print(f"删除前文件夹数量: {folders_before}")

        # 检查 chroma.sqlite3 大小
        chroma_db_path = "./received_dir/user_db_file/chroma.sqlite3"
        if os.path.exists(chroma_db_path):
            size_before = os.path.getsize(chroma_db_path)
            print(f"删除前 chroma.sqlite3 大小: {size_before / (1024 * 1024):.2f} MB")
        else:
            size_before = 0
            print("chroma.sqlite3 不存在")

        # 构建collection名称
        collection_name = util.construct_collection(usr_name + "_" + book_name)
        print(f"Collection名称: {collection_name}")

        # 🔥 使用智能路径检测
        actual_db_path, db_type, secondary_db_path = get_user_db_path(usr_name + "_" + book_name)
        print(f"数据库类型: {db_type}, 路径: {actual_db_path}")

        vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=embeddings,
            persist_directory=actual_db_path  # 🔥 使用智能检测的路径
        )

        collection = vector_store._collection
        all_data = collection.get()
        all_ids = all_data['ids']

        print(f"=== 调试信息 ===")
        print(all_ids)

        if all_ids:
            print(f"\n前10个实际ID:")
            for i, doc_id in enumerate(all_ids[:10]):
                print(f"  {i + 1}: {doc_id}")
        else:
            print("没有找到任何文档ID!")
            return False

        # 构建该本子的文件路径前缀
        book_path_prefix = f"./received_dir/user_raw_file/{usr_name}_{book_name}/"

        # 找到该本子的所有文档ID
        target_ids = [doc_id for doc_id in all_ids if doc_id.startswith(book_path_prefix)]

        if target_ids:
            print(f"找到本子 {usr_name}_{book_name} 的 {len(target_ids)} 个文档")
            print("前几个文档ID:")
            for doc_id in target_ids[:5]:
                print(f"  - {doc_id}")

            # 删除匹配的文档
            collection.delete(ids=target_ids)
            vector_store.persist()

            # 强制刷新 - 重新获取数据验证删除
            print("验证删除结果...")
            vector_store = None  # 释放引用
            collection = None
            print("释放连接")

            # 等待一下确保释放
            time.sleep(1)

            # 重新连接验证
            vector_store = Chroma(
                collection_name=collection_name,
                embedding_function=embeddings,
                persist_directory=actual_db_path  # 🔥 使用智能检测的路径
            )

            verify_data = vector_store._collection.get()
            remaining_ids = [doc_id for doc_id in verify_data['ids'] if doc_id.startswith(book_path_prefix)]
            if remaining_ids:
                print(f"⚠️  警告：仍有 {len(remaining_ids)} 个文档未删除")
            else:
                print("✓ 验证：所有目标文档已删除")

            # 再次释放
            vector_store = None
            print("等待自动持久化...")
            time.sleep(2)

            print(f"成功删除本子 {usr_name}_{book_name} 的所有向量数据")
            # return True
        else:
            print(f"未找到本子 {usr_name}_{book_name} 的向量数据")
            # return False

        # 统计删除后的状态
        folders_after = count_db_folders()
        print(f"删除后文件夹数量: {folders_after}")
        print(f"文件夹变化: {folders_before - folders_after}")

        if os.path.exists(chroma_db_path):
            size_after = os.path.getsize(chroma_db_path)
            print(f"删除后 chroma.sqlite3 大小: {size_after / (1024 * 1024):.2f} MB")
            print(f"数据库大小变化: {(size_before - size_after) / (1024 * 1024):.2f} MB")

            if size_after >= size_before:
                print("❌ chroma.sqlite3 大小没有减少，可能只删除了文件夹")
            else:
                print("✓ chroma.sqlite3 大小已减少，删除成功")

        return True

    except Exception as e:
        print(f"删除向量库失败: {e}")
        return False


def delete_notebook_vectors_simple(usr_name, book_name):
    """
    最简洁的物理删除版本 - 直接删除整个collection
    """
    try:
        import chromadb
        import os

        collection_name = util.construct_collection(usr_name + "_" + book_name)

        # 🔥 使用智能路径检测
        actual_db_path, db_type, secondary_db_path = get_user_db_path(usr_name + "_" + book_name)

        print(f"删除collection: {collection_name}, 数据库类型: {db_type}")

        # 记录删除前大小
        chroma_db_path = os.path.join(actual_db_path, "chroma.sqlite3")
        size_before = os.path.getsize(chroma_db_path) if os.path.exists(chroma_db_path) else 0

        # 直接删除整个collection
        client = chromadb.PersistentClient(path=actual_db_path)
        client.delete_collection(collection_name)

        # 等一秒缓冲
        time.sleep(1)

        # 检查结果
        size_after = os.path.getsize(chroma_db_path) if os.path.exists(chroma_db_path) else 0
        size_diff = (size_before - size_after) / (1024 * 1024)

        print(f"删除成功，数据库减少: {size_diff:.2f}MB")
        return True

    except Exception as e:
        print(f"删除失败: {e}")
        return False


# 现在有个明显的问题，我的分割大小到底该怎么确定，到底是不管模型直接就确定它的分割大小（分割方式另定）
# 还是说在确定模型之后，针对不同的模型由不同的分割策略。
# 这里涉及到分割究竟是为了什么
# 如果我们采取根据模型采取不同的分割大小，那么就需要对应的与大小有关的分割的策略
# 模型越大，分割的大小越大？
# 那么这么做的目的是什么呐？分割的片段越大，自然每次能输入的片段就越少，如果需要维持的是输入的片段的个数，那么自然需要这样的策略
# 但是实际上如果为了要充分利用上下文token数，那么我们可以采取多文档的策略，切割更多的文档，并且提供更多的文档
# 这样一来问题在于采取更大的文档，更相关的内容天生就更有可能被放在一起，如果采取小文档分割，我们能做的最多
# 只有尽可能使分割后的文档内部相似度最高，外部相似度最小，这是唯一能做到的。
# 在采取更多文档的策略下，假设相似度能确切地表示问题与回答之间的相关性，那么其实采取一定程度上的小粒度而非更大粒度会更有助于解决问题，（不论与）
# 问题相关地部分究竟是离散地还是聚合地，这里还涉及到相关性、相关度、文本大小之间的关系
# 明显的，非常小粒度的例如只有一个句子，与问题之间不可能存在什么相关性，而大粒度的文本可能会带有多个话题从而扰乱信息。
# 假设现在有一种分割策略，能够确定地将同一个话题的文本分割到一起，这些文本的长度可长可短
# 采取过小粒度会将话题磨灭掉
# 大粒度的带一个话题的文本其实不存在什么问题，问题只在于，这个话题的字数过大，
# 所以是否限制可以允许的最大的文本的数量就是一个很重要的问题，又限制到多少。
# 这里问题太多，太乱，现在思考不了。操。需要先确定更多的概念
# 现在就采取较小粒度并且大数量文档输入！
@async_thread
def load_user(user_name, progress_id=None):
    _user_lock(user_name)

    acquired = False
    load_event = None
    from zym.views import progress_data
    try:
        if _vector_ready(user_name):
            _mark_progress_done(progress_id)
            print(f"[{progress_id}] 本子已在内存中，跳过重复加载: {user_name}")
            return

        _write_progress(progress_id, progress=8, message='初始化数据库连接...')
        print(f"[{progress_id}] load_user 开始 user={user_name}")

        acquired = lock[user_name].acquire(blocking=False)
        if not acquired:
            with _load_done_guard:
                inflight = _load_done.get(user_name)
            if inflight is not None:
                print(f"[{progress_id}] 锁被占用，跟随已有加载: {user_name}")
                if _wait_for_inflight_load(user_name, progress_id):
                    print(f"[{progress_id}] 已复用进行中的加载: {user_name}")
                    return
            # 没有正在灌向量的人却拿不到锁 = 泄漏的 threading.RLock（异常未 release），
            # 不是热重载文件锁。换一把继续，避免卡在 8% 直到放弃。
            print(f"[{progress_id}] 锁被占用但无进行中加载，视为泄漏并换锁: {user_name}")
            _force_new_user_lock(user_name, progress_id, reason='no_inflight')
            acquired = lock[user_name].acquire(timeout=5)
            if not acquired:
                if _vector_ready(user_name):
                    _mark_progress_done(progress_id)
                    return
                _write_progress(
                    progress_id,
                    status='error',
                    message='本子仍在加载，请稍后再打开',
                )
                print(f"[{progress_id}] 无法获取用户 {user_name} 的锁，放弃")
                return

        if _vector_ready(user_name):
            _mark_progress_done(progress_id)
            return

        load_event = Event()
        with _load_done_guard:
            _load_done[user_name] = load_event

        # memory_usage = psutil.virtual_memory().percent
        # cpu_usage = psutil.cpu_percent()

        # 如果有进度ID，更新进度
        if progress_id:
            print(f"{progress_id}: 初始化数据库连接...")
            progress_data[progress_id]['progress'] = 15
            progress_data[progress_id]['message'] = '初始化数据库连接...'

        try:
            # 🔥 使用智能路径检测，兼容新旧数据库结构
            actual_db_path, db_type, secondary_db_path = get_user_db_path(user_name)
            collection_name = util.construct_collection(user_name)

            if progress_id:
                print(f"{progress_id}: 创建向量存储，collection: {collection_name}, 数据库类型: {db_type}")
                progress_data[progress_id]['progress'] = 17
                progress_data[progress_id]['message'] = f'创建向量存储({db_type})...'

            vector_store = Chroma(
                collection_name=collection_name,
                embedding_function=embeddings,
                persist_directory=actual_db_path  # 🔥 使用智能检测的路径
            )

            # 🔥 混合模式：同时加载从库（共享数据库）
            secondary_vector_store = None
            if db_type == "混合" and secondary_db_path:
                print(f"[混合模式] 加载从库: {secondary_db_path}")
                try:
                    secondary_vector_store = Chroma(
                        collection_name=collection_name,
                        embedding_function=embeddings,
                        persist_directory=secondary_db_path
                    )
                    # 将从库存储到全局变量，供查询时使用
                    if user_name not in global_var.store_memory:
                        global_var.store_memory[user_name] = {}
                    global_var.store_memory[user_name]["secondary_vector_store"] = secondary_vector_store
                except Exception as e:
                    print(f"[混合模式] 加载从库失败: {e}，仅使用主库")

            if progress_id:
                print(f"{progress_id}: 向量存储创建完成，路径: {actual_db_path}")
                progress_data[progress_id]['progress'] = 20
                progress_data[progress_id]['message'] = f'向量存储初始化完成({db_type})...'

            # 🔥 预热 ChromaDB 索引（避免首次查询时触发索引加载导致 260 秒阻塞）
            # 在后台线程中执行预热，不阻塞主流程
            def _warmup_chromadb_index(store, store_path, store_name="主库"):
                """预热 ChromaDB 索引，避免首次查询时触发索引加载导致长时间阻塞"""
                try:
                    # 🔥 参考 _detect_shared_chroma_collection_fast 的做法，先用 SQLite 快速检查是否有数据
                    # 避免使用 ChromaDB API（如 peek/get）进行检测，因为那些也会触发索引加载
                    chroma_db_file = os.path.join(store_path, "chroma.sqlite3")
                    if not os.path.exists(chroma_db_file):
                        print(f"[索引预热] {store_name} 数据库文件不存在，跳过预热")
                        return
                    
                    # 使用快速 SQLite 检测是否有数据
                    collection_name = util.construct_collection(user_name)
                    try:
                        collection_exists, has_any_row = _detect_shared_chroma_collection_fast(
                            shared_db_file=chroma_db_file,
                            collection_name=collection_name,
                            timeout_sec=1.0,
                        )
                        
                        if not collection_exists:
                            print(f"[索引预热] {store_name} collection 不存在，跳过预热")
                            return
                        
                        # collection_exists 为 True 但 has_any_row 可能为 None（无法确认）或 False
                        # 为了安全，只要有 collection 就尝试预热（即使数据可能为空）
                        if has_any_row is False:
                            print(f"[索引预热] {store_name} 确认无数据，跳过预热")
                            return
                        
                        # 有数据或无法确认时，进行预热查询（触发索引加载）
                        # 🔥 使用 vector_store.similarity_search() 而不是 collection.query()
                        # 因为 similarity_search() 会自动处理 embedding，而 query() 需要手动提供 embedding
                        try:
                            # 进行一次最小查询来预热索引（这是唯一需要触发索引加载的操作）
                            # 使用 similarity_search 会自动调用 embedding function
                            _ = store.similarity_search("test", k=1)
                            print(f"[索引预热] {store_name} 索引预热完成")
                        except Exception as query_error:
                            # 查询失败不影响，可能是没有足够的数据或索引已损坏
                            print(f"[索引预热] {store_name} 索引预热查询失败（不影响主流程）: {query_error}")
                            
                    except Exception as detect_error:
                        print(f"[索引预热] {store_name} SQLite 检测失败，跳过预热: {detect_error}")
                        
                except Exception as e:
                    # 预热失败不影响主流程，只记录日志
                    print(f"[索引预热] {store_name} 预热过程出错（不影响主流程）: {e}")

            # 在后台线程中预热主库索引
            import threading
            warmup_thread = threading.Thread(
                target=_warmup_chromadb_index,
                args=(vector_store, actual_db_path, "主库"),
                daemon=True
            )
            warmup_thread.start()
            print(f"[索引预热] 已启动主库索引预热（后台线程）")

            # 如果是混合模式，也预热从库索引
            if secondary_vector_store is not None and secondary_db_path:
                secondary_warmup_thread = threading.Thread(
                    target=_warmup_chromadb_index,
                    args=(secondary_vector_store, secondary_db_path, "从库"),
                    daemon=True
                )
                secondary_warmup_thread.start()
                print(f"[索引预热] 已启动从库索引预热（后台线程）")

        except Exception as e:
            print(f"[{progress_id}] 向量存储初始化失败: {e}")
            if progress_id:
                progress_data[progress_id]['status'] = 'error'
                progress_data[progress_id]['message'] = f'向量存储初始化失败: {e}'
            raise

        t1 = log_time("开始处理文件")
        error_file = []
        global_var.set_split_file(user_name)

        if progress_id:
            print(f"{progress_id}: 扫描用户文件目录...")
            progress_data[progress_id]['progress'] = 22
            progress_data[progress_id]['message'] = '扫描文件目录...'

        # 获取文件列表并计算总数，用于进度计算
        file_list = os.listdir(util.construct_file_path(user_name, ""))
        total_files = len(file_list)
        processed_files = 0

        t2 = log_time("文件扫描结束准备处理", t1)
        if progress_id:
            progress_data[progress_id]['progress'] = 25
            progress_data[progress_id]['message'] = f'找到 {len(file_list)} 个文件，准备处理...'
            print(f"{progress_id}: 开始文件处理循环，总共 {total_files} 个文件")

        # # 🔥 新增：对已存在的PDF文档进行扫描件检测（后台异步）
        # pdf_files_to_check = [f for f in file_list if f.endswith('.pdf') and '_transFTWYGUHX' not in f]
        # if pdf_files_to_check:
        #     print(f"[{progress_id}] 发现 {len(pdf_files_to_check)} 个PDF文件，准备检测扫描件类型...")

        #     def batch_check_pdf_types():
        #         """后台批量检测PDF类型"""
        #         from llm_langchain.pdf_ocr_utils import check_pdf_type_by_word

        #         for pdf_file in pdf_files_to_check:
        #             try:
        #                 file_key = f"{user_name}/{pdf_file}"
        #                 cached_type = global_var.get_pdf_type(file_key)

        #                 if cached_type is None:
        #                     # 未缓存，进行检测
        #                     pdf_path = util.construct_file_path(user_name, pdf_file)
        #                     if os.path.exists(pdf_path) and os.path.isfile(pdf_path):
        #                         print(f"[PDF批量检测] 正在检测: {pdf_file}")
        #                         pdf_type = check_pdf_type_by_word(pdf_path)
        #                         global_var.set_pdf_type(file_key, pdf_type)
        #                         print(f"[PDF批量检测] {pdf_file} → {pdf_type}")
        #                 else:
        #                     print(f"[PDF批量检测] {pdf_file} 已缓存: {cached_type}")
        #             except Exception as e:
        #                 print(f"[PDF批量检测] 检测 {pdf_file} 失败: {e}")

        #         print(f"[PDF批量检测] 完成，共检测 {len(pdf_files_to_check)} 个PDF")

        #     # 在后台线程中执行批量检测（不阻塞主流程）
        #     import threading
        #     check_thread = threading.Thread(target=batch_check_pdf_types, daemon=True)
        #     check_thread.start()
        #     print(f"[{progress_id}] PDF扫描件检测已在后台启动")

        for f in file_list:
            print(f"[{progress_id}] 开始处理: {f}")
            file_path = util.construct_file_path(user_name, f)
            base_64 = []

            # 添加这个检查来跳过cardImage和pre_summary目录
            if os.path.isdir(file_path) and f == "cardImage":
                total_files = total_files - 1
                print(f"[{progress_id}] 跳过cardImage目录")
                continue

            if os.path.isdir(file_path) and f == "pre_summary":
                total_files = total_files - 1
                print(f"[{progress_id}] 跳过pre_summary目录")
                continue

            if os.path.isdir(file_path) and f == "skills":
                total_files = total_files - 1
                print(f"[{progress_id}] 跳过skills目录")
                continue

            if os.path.isfile(file_path) and f.lower().endswith(".zip"):
                # Skill 包 zip 不向量化
                total_files = total_files - 1
                print(f"[{progress_id}] 跳过 Skill 包 zip: {f}")
                continue

            if os.path.isdir(file_path) and f != "cardImage" and f != "pre_summary" and f != "skills" and not f.endswith("_ocr"):
                total_files = total_files - 1

                # 连续图片理解等系统目录不参与图片base64恢复
                if not f.endswith("_image"):
                    print(f"[{progress_id}] 跳过非图片资源目录: {f}")
                    continue

                pdf = util.back_image_path(f)
                print(f"[{progress_id}] 处理图片目录: {f}")

                path_list = os.listdir(file_path)

                # 修复排序逻辑：只对数字开头的文件进行数字排序，其他文件按字符串排序
                def sort_key(x):
                    try:
                        num_part = x.split('.')[0]
                        return (0, int(num_part))
                    except (ValueError, IndexError):
                        return (1, x)

                path_list.sort(key=sort_key)

                image_exts = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff'}
                for img_path in path_list:
                    img_abs_path = os.path.join(file_path, img_path)
                    if not os.path.isfile(img_abs_path):
                        continue
                    ext = os.path.splitext(img_path)[1].lower()
                    if ext not in image_exts:
                        continue
                    base_64.append(util.encode_image(img_abs_path))

                global_var.set_user_image(user_name, pdf, base_64)
                print(f"[{progress_id}] 图片目录处理完成: {f}, 有效图片数: {len(base_64)}")

                continue

            # 添加这个检查来跳过_transFTWYGUHX标记的翻译文档
            if "_transFTWYGUHX" in f:
                total_files = total_files - 1
                print(f"[{progress_id}] 跳过_transFTWYGUHX翻译文档")
                continue

            try:
                # split_docs = util.get_seq_doc_by_name(user_name, [f], vector_store)
                # global_var.set_user_split(user_name, f, split_docs)

                # t3 = log_time(f"开始设置split_docs {processed_files}", t2)
                # # 先检查是否已经存在分割文档
                # if user_name in global_var.store_memory and \
                #         "split_docs" in global_var.store_memory[user_name] and \
                #         f in global_var.store_memory[user_name]["split_docs"] and \
                #         global_var.store_memory[user_name]["split_docs"][f]:
                #     # 如果内存中已存在，应该可以直接跳过
                #     print(f"内存中已有文档分割: {user_name}/{f}")
                # else:
                #     # 如果不存在，执行耗时操作并存储结果
                #     split_docs = util.get_seq_doc_by_name(user_name, [f], vector_store)
                #     global_var.set_user_split(user_name, f, split_docs)
                #     print(f"获取文档分割: {user_name}/{f}")

                print(f"[{progress_id}] 开始处理文件: {f} (类型: 普通文件)")

                # 立即更新进度，让用户知道已经开始处理文件了
                if progress_id and processed_files == 0:
                    progress_data[progress_id]['progress'] = 26
                    progress_data[progress_id]['message'] = f'正在处理第1个文件: {f}...'
                    print(f"[{progress_id}] 更新进度到26%，开始处理第一个文件")

                # 导入简单的文档缓存工具
                from llm_langchain.document_cache import doc_cache

                t3 = log_time(f"开始设置split_docs {processed_files}", t2)
                split_docs = None

                print(f"[{progress_id}] 开始三层缓存检查: {f}")

                # 三层缓存机制：内存 -> 文件缓存 -> 重新计算
                # 第一层：检查内存中是否已经存在分割文档，并验证文件是否变更
                memory_cache_valid = False
                print(f"[{progress_id}] 检查内存缓存: {f}")

                if user_name in global_var.store_memory and \
                        "split_docs" in global_var.store_memory[user_name] and \
                        f in global_var.store_memory[user_name]["split_docs"] and \
                        global_var.store_memory[user_name]["split_docs"][f]:

                    print(f"[{progress_id}] 内存中发现缓存，开始验证文件哈希: {f}")
                    # 检查文件是否已变更（比较哈希值）
                    current_hash = doc_cache.get_file_hash(file_path)
                    print(f"[{progress_id}] 文件哈希计算完成: {f}")

                    # 尝试从文件缓存获取之前保存的哈希值
                    cache_path = doc_cache.get_cache_path(user_name, f)
                    if os.path.exists(cache_path):
                        try:
                            print(f"[{progress_id}] 读取缓存文件验证哈希: {f}")
                            import pickle
                            with open(cache_path, 'rb') as cache_file:
                                cache_data = pickle.load(cache_file)
                                cached_hash = cache_data.get('file_hash')
                                if current_hash == cached_hash:
                                    memory_cache_valid = True
                                    print(f"内存中已有文档分割且文件未变更: {user_name}/{f}")
                                    split_docs = global_var.store_memory[user_name]["split_docs"][f]
                                else:
                                    print(f"文件已变更，清理内存缓存: {user_name}/{f}")
                                    # 清理内存中的旧缓存
                                    try:
                                        del global_var.store_memory[user_name]["split_docs"][f]
                                    except KeyError:
                                        pass
                        except Exception as e:
                            print(f"[{progress_id}] 无法验证文件哈希({e})，清理内存缓存: {user_name}/{f}")
                            try:
                                del global_var.store_memory[user_name]["split_docs"][f]
                            except KeyError:
                                pass
                    else:
                        # 没有文件缓存，无法验证，清理内存缓存
                        print(f"无文件缓存验证，清理内存缓存: {user_name}/{f}")
                        try:
                            del global_var.store_memory[user_name]["split_docs"][f]
                        except KeyError:
                            pass
                else:
                    print(f"[{progress_id}] 内存中无缓存: {f}")

                if not memory_cache_valid:
                    print(f"[{progress_id}] 检查文件缓存: {f}")
                    # 第二层：从文件缓存中查找
                    split_docs = doc_cache.load_split_docs(user_name, f, file_path)

                    if split_docs is not None:
                        # 从文件缓存加载成功，同时更新到内存缓存
                        # 🔥 如果split_docs为空或内容很少，且是扫描件PDF，尝试从OCR结果文件加载
                        if (not split_docs or len(split_docs) == 0 or all(
                                not doc.page_content.strip() for doc in split_docs)) and file_path.endswith("pdf"):
                            ocr_split_docs = _try_load_split_docs_from_ocr_raw(user_name, f, file_path)
                            if ocr_split_docs:
                                split_docs = ocr_split_docs
                                try:
                                    doc_cache.save_split_docs(user_name, f, file_path, split_docs)
                                except Exception:
                                    pass

                        global_var.set_user_split(user_name, f, split_docs)
                        print(f"从文件缓存加载成功并更新到内存: {user_name}/{f}")
                    else:
                        # 第三层：都没有找到，执行耗时的重新计算操作
                        print(f"[{progress_id}] 缓存未命中，开始重新计算文档分割: {user_name}/{f}")

                        # 这是最耗时的操作，可能是卡顿的原因
                        split_start_time = log_time(f"开始文档分割 {f}")
                        split_docs = util.get_seq_doc_by_name(user_name, [f], vector_store)
                        log_time(f"文档分割完成 {f}", split_start_time)

                        # 🔥 如果split_docs为空或内容很少，且是扫描件PDF，尝试从OCR结果文件加载
                        if (not split_docs or len(split_docs) == 0 or all(
                                not doc.page_content.strip() for doc in split_docs)) and file_path.endswith("pdf"):
                            ocr_split_docs = _try_load_split_docs_from_ocr_raw(user_name, f, file_path)
                            if ocr_split_docs:
                                split_docs = ocr_split_docs

                        # 将结果保存到内存缓存
                        global_var.set_user_split(user_name, f, split_docs)
                        print(f"文档分割完成并保存到内存: {user_name}/{f}")

                        # 保存到文件缓存（不阻塞主流程）
                        try:
                            doc_cache.save_split_docs(user_name, f, file_path, split_docs)
                            print(f"[{progress_id}] 文档分割已保存到文件缓存: {user_name}/{f}")
                        except Exception as cache_error:
                            print(f"[{progress_id}] 保存到文件缓存失败: {user_name}/{f}, 错误: {cache_error}")

                print(f"[{progress_id}] 文档分割处理完成: {f}")

                # 记录全局变量操作时间
                t4 = log_time(f"开始设置split_file {processed_files}", t3)
                global_var.add_split_file(user_name, f)
                t5 = log_time(f"完成设置split_file {processed_files}", t4)

                if file_path.endswith("png") or file_path.endswith("jpg") or file_path.endswith("jpeg"):
                    base_64.append(util.encode_image(file_path))
                    global_var.set_user_image(user_name, f, base_64)

                # 更新进度
                processed_files += 1
                if progress_id:
                    # 计算进度百分比（25%-95%区间）
                    file_progress = 25 + (processed_files / total_files) * 70
                    progress_data[progress_id]['progress'] = int(file_progress)
                    progress_data[progress_id]['message'] = f'处理文件（夹） {processed_files}/{total_files}...'
                    print(f"{progress_id}: 目前进度：")
                    print(progress_data[progress_id])

            except Exception as e:
                print(f"[{progress_id}] 处理文件 {f} 时出错: {e}")
                error_file.append(f)
                # 即使出错也要增加processed_files计数，确保进度正常
                processed_files += 1

        global_var.set_user_vector(user_name, vector_store)
        mem = global_var.store_memory.get(user_name) or {}
        if not mem.get('prompt'):
            global_var.set_user_prompt(user_name)
        if 'params' not in mem:
            global_var.set_user_params(user_name)
        global_var.set_user_model(user_name, 0)

        if progress_id:
            # 最终完成
            progress_data[progress_id]['progress'] = 100
            progress_data[progress_id]['status'] = 'completed'
            progress_data[progress_id]['message'] = '加载完成'
        print('[parse_input]load_user:', error_file)
    finally:
        if load_event is not None:
            load_event.set()
            with _load_done_guard:
                if _load_done.get(user_name) is load_event:
                    _load_done.pop(user_name, None)
        if acquired:
            lock[user_name].release()
            print(f"[{progress_id}] 成功释放用户 {user_name} 的锁")


def get_docs_by_user_doc(user_name, docs_name):
    held = _user_lock(user_name)
    held.acquire()
    try:
        texts = []
        images_all = []
        # print(global_var.store_memory)
        for doc_name in docs_name:
            str_doc = ""
            if doc_name.endswith('txt') or doc_name.endswith('pdf'):
                for doc in global_var.store_memory[user_name]["split_docs"][doc_name]:
                    str_doc += doc.page_content
            texts.append(str_doc)
            images = []
            if doc_name.endswith('pdf') or doc_name.endswith('png') or doc_name.endswith('jpg') or doc_name.endswith('jpeg'):
                # 检查是否有图片数据
                # if "images" in global_var.store_memory[user_name] and doc_name in global_var.store_memory[user_name]["images"]:
                #     for image in global_var.store_memory[user_name]["images"][doc_name]:
                #         images.append(image)
                # if global_var.store_memory[user_name]["params"]["image"] < len(images):
                #     images = images[:global_var.store_memory[user_name]["params"]["image"]]
                if "images" in global_var.store_memory[user_name] and doc_name in global_var.store_memory[user_name]["images"]:
                    for image in global_var.store_memory[user_name]["images"][doc_name]:
                        images.append(image)
                    # 限制图片数量
                    if global_var.store_memory[user_name]["params"]["image"] < len(images):
                        images = images[:global_var.store_memory[user_name]["params"]["image"]]
                else:
                    # 如果没有图片数据，返回空数组（用于两段式处理）
                    print(f"[get_docs_by_user_doc] 文档 {doc_name} 暂无图片数据")
            images_all.append(images)
        return texts, images_all
    finally:
        held.release()


def update_pdf_image_sum(user_name, doc_name, seq, merge_content="", imgtext=""):
    """
    更新矢量存储中特定文档的 <图片> 解析文本内容

    参数：
    user_name （str）：用户的名称（userId <用户名_本子名> ）
    doc_name （str）：文档的名称
    seq （int）：要更新的 chunk 的序列号（根据 ID 逻辑进行调整）

    返回：
    bool：如果更新成功，则为 True，否则为 False
    """
    lock[user_name].acquire()
    try:
        base64_image = global_var.store_memory[user_name]["images"][doc_name][seq]
        new_content = ""
        if merge_content == "":
            # new_content = util.image_2_summary(base64_image)
            old_content = get_pdf_image_sum(user_name=user_name, doc_name=doc_name, seq=seq)
            # new_content = util.image_retry_summary(old_content, base64_image)
            new_content = imgtext
        else:
            old_content = get_pdf_image_sum(user_name=user_name, doc_name=doc_name, seq=seq)
            new_content = util.image_merge_summary(old_content, merge_content, base64_image)
        file_name = util.construct_file_path(user_name, doc_name)

        # 构造过滤器以查找文档 ID
        # 注意：根据您的 ID 的结构和存储方式调整过滤器。
        # 原来的 filter 使用了 seq+1，需要就调整一下。
        filter_k = {
            "$and": [
                {"source": {"$eq": file_name}},
                {"seq": {"$eq": seq + 1}}
            ]
        }

        # 1. 获取与筛选器匹配的文档以查找 ID
        # results = global_var.store_memory[user_name]["vector_store"].get(where=filter_k, include=["metadatas"])  # 如果新文档需要，请包含元数据
        # 修改此行，同时包含metadatas和documents
        results = global_var.store_memory[user_name]["vector_store"].get(where=filter_k,
                                                                         include=["metadatas", "documents"])

        if not results or not results.get("ids"):
            print(f"Error: Document not found for source='{file_name}' and seq={seq + 1}")
            return '生成失败，请稍后再试！'

        # 获取所有需要更新的文档ID、元数据和内容
        doc_ids_to_update = results["ids"]
        original_metadatas = results["metadatas"]
        original_contents = results["documents"]
        doc_count = len(doc_ids_to_update)

        # 计算原始内容的总长度和平均每块的长度
        original_total_length = sum(len(content) for content in original_contents)
        original_avg_length = original_total_length / doc_count if doc_count > 0 else 0

        # 强制将新内容分割成与原始文档相同数量的块
        new_texts = []
        new_content_length = len(new_content)

        if doc_count == 1:
            # 如果只有一个文档，直接使用全部新内容
            new_texts = [new_content]
        else:
            # 计算每个块应该包含的字符数
            chars_per_chunk = new_content_length // doc_count
            remainder = new_content_length % doc_count

            start_idx = 0
            for i in range(doc_count):
                # 最后一个块可能会略长，包含余数部分
                chunk_size = chars_per_chunk + (1 if i < remainder else 0)
                end_idx = start_idx + chunk_size

                # 确保不超出内容范围
                if end_idx > new_content_length:
                    end_idx = new_content_length

                # 添加分割后的块
                new_texts.append(new_content[start_idx:end_idx])
                start_idx = end_idx

        # 准备更新的文档
        updated_docs = []
        for i, doc_id in enumerate(doc_ids_to_update):
            # 复制原始元数据
            updated_metadata = original_metadatas[i].copy()

            # 处理PDF文件的特殊情况
            if updated_metadata.get("source", "").endswith(".pdf"):
                out_file = updated_metadata["source"][:-4] + "_image" + "/"
                current_content = out_file + "文件中的一张图片，内容为" + new_texts[i]
            else:
                current_content = new_texts[i]

            # 创建更新的文档对象
            updated_docs.append(Document(
                page_content=current_content,
                metadata=updated_metadata
            ))

        # 更新所有匹配的文档
        global_var.store_memory[user_name]["vector_store"].update_documents(
            ids=doc_ids_to_update,
            documents=updated_docs
        )

        # doc_id_to_update = results["ids"][0]
        # # 假设只有一个文档匹配。如有必要，处理多个匹配项。
        # original_metadata = results["metadatas"][0] if results.get("metadatas") else {}

        # # 2. 创建更新的 Document 对象
        # # 您可能希望保留原始元数据或更新其中的某些部分
        # updated_metadata = original_metadata.copy()  # 从原始元数据开始
        # # 如果需要，可能会更新元数据字段，例如：
        # # updated_metadata["last_updated"] = datetime.now().isoformat()
        # if updated_metadata.get("source").endswith(".pdf"):
        #     out_file = updated_metadata["source"][:-4] + "_image" + "/"
        #     new_content = out_file + "文件中的一张图片，内容为" + new_content
        # updated_doc = Document(
        #     page_content=new_content,
        #     metadata=updated_metadata
        # )
        #
        # # 3. 调用更新方法
        # # 使用 update_documents 保持一致性，即使对于单个文档也是如此
        # global_var.store_memory[user_name]["vector_store"].update_documents(ids=[doc_id_to_update],
        #                                                                     documents=[updated_doc])

        # 可选：更新 In-Memory split_docs（如果您单独维护）
        # 这需要在其中找到对应的doc：global_var.store_memory[user_name]["split_docs"]
        # 并更新其 page_content

        print(f"Successfully updated document with ID: {doc_ids_to_update}")
        return new_content

    except Exception as e:
        print(f"Error updating document: {e}")
        return '生成失败，请稍后再试！'
    finally:
        lock[user_name].release()


# --- 如何调用 ---
# 假设 'user1', 'mydoc.pdf', seq=0 需要更新 content
# success = update_pdf_image_sum("user1", "mydoc.pdf", 0, "这是新的内容.")
# if success:
#     print("Update successful.")
# else:
#     print("Update failed.")


def get_pdf_image_sum(user_name, doc_name, seq):
    file_name = util.construct_file_path(user_name, doc_name)
    # query = {}
    # query["source"] = {"$eq": file_name}
    # query["seq"] = {"eq": seq}
    # filter_k = {
    #     "$and": [
    #         {"source": {"$eq": file_name}},
    #         {"seq": {"$eq": seq + 1}}
    #     ]
    # }
    # lock[user_name].acquire()
    # docs = global_var.store_memory[user_name]["vector_store"].get(where=filter_k)
    # lock[user_name].release()
    #
    # # 遍历所有文档，并通过空行拼接
    # result = "\n\n".join(docs["documents"])
    # return result
    # # return docs["documents"][0]

    # 优先从向量库获取数据（原有方式）
    try:
        filter_k = {
            "$and": [
                {"source": {"$eq": file_name}},
                {"seq": {"$eq": seq + 1}}
            ]
        }
        held = _user_lock(user_name)
        held.acquire()
        try:
            docs = global_var.store_memory[user_name]["vector_store"].get(where=filter_k)
        finally:
            held.release()

        # 检查是否获取到有效数据
        if docs and docs.get("documents") and len(docs["documents"]) > 0:
            # 过滤掉空字符串
            valid_docs = [doc for doc in docs["documents"] if doc and doc.strip()]
            if valid_docs:
                result = "\n\n".join(valid_docs)
                print(f"[图片文本获取] 从向量库获取第{seq + 1}张图片分析结果")
                return result

        print(f"[图片文本获取] 向量库中未找到第{seq + 1}张图片数据，尝试从global_var获取")

    except Exception as e:
        print(f"[图片文本获取] 从向量库获取失败: {e}")

    # 如果向量库中没有或为空，从global_var中获取数据（实时更新）
    try:
        split_docs = global_var.get_user_split(user_name, doc_name)
        if split_docs:
            for doc in split_docs:
                if (doc.metadata.get('type') == 'image' and
                        doc.metadata.get('seq') == seq + 1):
                    print(f"[图片文本获取] 从global_var获取第{seq + 1}张图片分析结果")
                    return doc.page_content
    except Exception as e:
        print(f"[图片文本获取] 从global_var获取失败: {e}")

    # 如果都获取失败，返回默认消息
    print(f"[图片文本获取] 未能获取到第{seq + 1}张图片分析结果")
    return "图片分析结果暂未可用，请稍后再试"


# 返回根据用户指定的一系列文档的分割后的所有文档的列表
def get_split_by_user_docs(user_name, docs_name):
    held = _user_lock(user_name)
    held.acquire()
    try:
        docs = []
        for doc_name in docs_name:
            # docs.extend(global_var.store_memory[user_name]["split_docs"][doc_name])
            split_docs = None
            try:
                split_docs = global_var.get_user_split(user_name, doc_name)
            except Exception:
                split_docs = None
            if split_docs is None:
                split_docs = []

            # 🔥 如果split_docs为空或内容很少，且是扫描件PDF，尝试从OCR结果文件加载
            if (not split_docs or len(split_docs) == 0 or all(not doc.page_content.strip() for doc in split_docs)):
                try:
                    file_path = util.construct_file_path(user_name, doc_name)
                    if file_path.endswith("pdf"):
                        ocr_split_docs = _try_load_split_docs_from_ocr_raw(user_name, doc_name, file_path)
                        if ocr_split_docs:
                            split_docs = ocr_split_docs
                            global_var.set_user_split(user_name, doc_name, split_docs)
                except Exception as e:
                    print(f"[get_split_by_user_docs] 从OCR结果文件加载失败: {e}")

            docs.extend(split_docs)
        return docs
    finally:
        held.release()


def get_vector_by_user(user_name):
    # lock[user_name].acquire()
    out = global_var.store_memory[user_name]["vector_store"]
    # lock[user_name].release()
    return out


def set_user_prompt(user_name, prompt):
    held = _memory_lock(user_name)
    held.acquire()
    try:
        global_var.set_user_prompt(user_name, prompt)
    finally:
        held.release()


def set_user_model(user_name, model_num):
    held = _user_lock(user_name)
    held.acquire()
    try:
        global_var.set_user_model(user_name, model_num)
    finally:
        held.release()


def get_user_model(user_name):
    held = _user_lock(user_name)
    held.acquire()
    try:
        return global_var.store_memory[user_name]["model_num"]
    finally:
        held.release()


def get_user_params(user_name):
    held = _user_lock(user_name)
    held.acquire()
    try:
        return global_var.store_memory[user_name]["params"]
    finally:
        held.release()


def set_user_params(user_name, params):
    held = _memory_lock(user_name)
    held.acquire()
    try:
        global_var.set_user_params(user_name, params)
    finally:
        held.release()


def get_list_by_scene_name(scene_name):
    secenDirPath = "./received_dir/scene_excel/" + scene_name
    filesList = []
    sizeList = []
    if os.path.exists(secenDirPath):
        files_and_dirs = os.listdir(secenDirPath)
        for file in files_and_dirs:
            if os.path.isfile(os.path.join(secenDirPath, file)):
                if file.endswith(".xlsx"):
                    continue
                filesList.append(file)
                sizeList.append(os.path.getsize(os.path.join(secenDirPath, file)))
    return filesList, sizeList


# import init
# import get_suma
# import get_rel_que
# import normal_qa
# import red_bule_rate
# init.init()
# init.switch(1)
# global_var.init_store_memory()
# get_split_docs_vectors("admin", "Notebooklm复现（红蓝融合GPT认知）任务单.docx")
# split_docs, vector_store = get_split_docs_vectors("admin", "attention is all you need.pdf")
# load_user("admin")
# global_var.save_config(**{"temperature": 0, "top_p": 0.95})
# get_split_by_user_docs("admin", ["attention is all you need.pdf"])
# get_rel_que.get_rel_que_user_doc("admin",["attention is all you need.pdf", "Notebooklm复现（红蓝融合GPT认知）任务单.docx"])
# get_suma.get_summary_user_docs("admin", ["attention is all you need.pdf"])
# out = red_bule_rate.get_rate("我们要积极向上，奋发图强")
# print(out)
# normal_qa.get_qa_user_docs("admin",
# "我的计划是什么", ["attention is all you need.pdf", "Notebooklm复现（红蓝融合GPT认知）任务单.docx"]) print(store_memory[user_name])

# 改用pymu之后的metadata是不一样的，这点要谨记，之前的不全了
def get_split_docs_vectors_scene(scene_name, docs_name):
    # global store_memory
    file_path = "./received_dir/scene_excel/" + scene_name + "/" + docs_name
    # pdf_file_path = "./attention is all you need.pdf"
    loader = get_loader(file_path)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=0)  # 不根据模型大小限制分割大小，而是提供更多文档。
    # 这里分割后文档metadata为loader使用的file_path
    split_docs = text_splitter.split_documents(loader.load())

    # 🔥 为每个segment的content添加页号信息（如果metadata中有page信息）
    for doc in split_docs:
        if doc.metadata and "page" in doc.metadata:
            page_num = doc.metadata["page"]
            # 页号从0开始，转换为从1开始的页码
            page_display = page_num + 1 if isinstance(page_num, int) else page_num
            # 在content开头添加页号标记
            if not doc.page_content.strip().startswith("[页码："):
                doc.page_content = f"[页码：第{page_display}页]\n{doc.page_content}"

    # print(split_docs)
    base_64_out = []
    if file_path.endswith("pdf"):
        # 场景相关的PDF处理，不写入PreImageOrigin_pdf.md（因为这是场景文件，不是用户文件）
        docs_out, base_64_out = util.muExtractImages(file_path)
        # 🔥 为图片提取的文档也添加页号信息
        for doc in docs_out:
            if doc.metadata and "page" in doc.metadata:
                page_num = doc.metadata["page"]
                page_display = page_num + 1 if isinstance(page_num, int) else page_num
                if not doc.page_content.strip().startswith("[页码："):
                    doc.page_content = f"[页码：第{page_display}页]\n{doc.page_content}"
        split_docs.extend(docs_out)
    # print(split_docs)
    ids = util.construct_ids(file_path, len(split_docs))  # ids = 其实可以由docs_name + 顺序组成 # 另一个问题是顺序也可以由meta_data得到
    db_path = util.db_path
    # encoded_bytes = scene_name.encode('utf-8')
    # encoded_text = base64.b64encode(encoded_bytes)
    # scene_name = encoded_text.decode('utf-8')
    # print(scene_name)
    hex_scene = encode_chinese_to_hex(scene_name)
    # print(hex_scene)
    collection_name = util.construct_collection("scene_name_" + hex_scene)
    if len(collection_name) > 63:
        collection_name = collection_name[:63]
    vector_store = Chroma(
        collection_name=collection_name,
        embedding_function=embeddings,
        persist_directory=db_path
    )
    # 已经找到了问题所在
    # 使用add与from的问题在于当时使用from没有指定path和collection_name，所以是新生成的
    # 而add使用前先指定了db_path与collection_name导致使用的是原来的且每次都新进行添加所以出现了问题
    # 因此这里直接指定add是不会出现问题的，只需要不进行重复调用
    # ids是id的list包括可能之后删除也是idlist
    # print(len(split_docs))
    # print(split_docs)
    # split_docs_s = []
    n_add = len(split_docs) // 55
    for i in range(n_add):
        vector_store.add_documents(documents=split_docs[i * 55:(i + 1) * 55], ids=ids[i * 55:(i + 1) * 55])
        print(f"分割处理上传的场景文档add_documents批次{i}/{n_add}完成")
        time.sleep(0.5)
    vector_store.add_documents(documents=split_docs[n_add * 55:len(split_docs)], ids=ids[n_add * 55:len(split_docs)])
    # vector_store.add_documents(documents=split_docs, ids=ids)
    # global_var.set_user_split(usr_name, docs_name, split_docs)
    # if len(base_64_out) != 0:
    #    global_var.set_user_image(usr_name, docs_name, base_64_out)
    # global_var.set_user_vector(usr_name, vector_store)
    # store_memory[usr_name]["split_docs"][docs_name] = split_docs
    # store_memory[usr_name]["vector_store"] = vector_store
    # query = "What is attention"
    # docs = vector_store.similarity_search(query)
    # print(docs[0].page_content) #得到的文档调用page_content得到内容
    return split_docs, vector_store


# 需要修改的包括file_path, source
def split_scene_to_user(scene_name, user_name):
    scene_dir = "./received_dir/scene_excel/" + scene_name
    error_file = []
    user_dir = util.construct_file_path(user_name, "")
    user_dir = user_dir[:len(user_dir) - 1]
    hex_scene = encode_chinese_to_hex(scene_name)
    # chinese = decode_chinese_from_binary(binary)
    scene_collection_name = util.construct_collection("scene_name_" + hex_scene)
    scene_db_path = util.db_path  # 场景数据库使用共享路径
    if len(scene_collection_name) > 63:
        scene_collection_name = scene_collection_name[:63]

    # 🔥 使用 get_or_create_collection 避免并发创建冲突
    try:
        scene_client = chromadb.PersistentClient(path=scene_db_path)
        try:
            scene_client.get_collection(name=scene_collection_name)
        except Exception:
            # Collection不存在，创建它
            scene_client.create_collection(name=scene_collection_name)
    except Exception as e:
        # 如果 collection 已存在（并发创建），忽略错误
        if "already exists" not in str(e).lower():
            print(f"[split_scene_to_user] 场景collection处理失败: {e}")

    vector_store_scene = Chroma(
        collection_name=scene_collection_name,
        embedding_function=embeddings,
        persist_directory=scene_db_path
    )

    # 🔥 使用 get_user_db_path 获取正确的用户数据库路径（支持主库从库）
    actual_db_path, db_type, secondary_db_path = get_user_db_path(user_name)
    user_collection_name = util.construct_collection(user_name)
    if len(user_collection_name) > 63:
        user_collection_name = user_collection_name[:63]

    # 🔥 使用 get_or_create_collection 避免并发创建冲突
    try:
        user_client = chromadb.PersistentClient(path=actual_db_path)
        try:
            user_client.get_collection(name=user_collection_name)
        except Exception:
            # Collection不存在，创建它
            user_client.create_collection(name=user_collection_name)
    except Exception as e:
        # 如果 collection 已存在（并发创建），忽略错误
        if "already exists" not in str(e).lower():
            print(f"[split_scene_to_user] 用户collection处理失败: {e}")

    vector_store_user = Chroma(
        collection_name=user_collection_name,
        embedding_function=embeddings,
        persist_directory=actual_db_path  # 🔥 使用智能检测的路径
    )
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    # 并行处理文件
    def process_single_file(f, vector_store_scene, vector_store_user):
        scene_doc_path = scene_dir + "/" + f
        user_doc_path = user_dir + "/" + f
        print(f)

        if os.path.isdir(scene_doc_path):
            if not f.endswith("_image"):
                return None
            # pdf = util.back_image_path(f)
            if not os.path.exists(user_doc_path):
                os.makedirs(user_doc_path)
            for image_f in os.listdir(scene_doc_path):
                src_path = scene_doc_path + "/" + image_f
                tar_path = user_doc_path + '/' + image_f
                shutil.copy(src_path, tar_path)
            # global_var.set_user_image(user_name, pdf, base_64)
            return None

        try:
            if f.endswith("xlsx"):
                return None
            shutil.copy(scene_doc_path, user_doc_path)
            split_docs = util.get_seq_doc_by_path([scene_doc_path], vector_store_scene)
            for split_doc in split_docs:
                # split_doc（文本、图片片段）指向PDF路径
                split_doc.metadata["source"] = split_doc.metadata["source"].replace(scene_dir, user_dir)
                # split_doc（文本、图片片段）真实文件路径，如果存在的话!!!（pdf和图像文本分割后的metadata里都有多项，包括这两个；而txt分割后只有source）
                if "file_path" in split_doc.metadata:
                    split_doc.metadata["file_path"] = split_doc.metadata["file_path"].replace(scene_dir, user_dir)
            ids = util.construct_ids(user_doc_path, len(split_docs))
            n_add = len(split_docs) // 55
            for i in range(n_add):
                vector_store_user.add_documents(documents=split_docs[i * 55:(i + 1) * 55],
                                                ids=ids[i * 55:(i + 1) * 55])
                print(f"分割处理分享本子的场景文档add_documents批次{i}/{n_add}完成")
                time.sleep(0.5)
            vector_store_user.add_documents(documents=split_docs[n_add * 55:len(split_docs)],
                                            ids=ids[n_add * 55:len(split_docs)])
            # global_var.set_user_split(user_name, f, split_docs)
            return None
        except Exception as e:
            print(e)
            return f

    # 获取所有文件列表
    file_list = os.listdir(scene_dir + "/")

    # 并行处理所有文件
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for f in file_list:
            future = executor.submit(process_single_file, f, vector_store_scene, vector_store_user)
            futures.append(future)

        # 收集错误文件
        for future in futures:
            try:
                error_f = future.result()
                if error_f:
                    error_file.append(error_f)
            except Exception as e:
                print(f"处理文件时出错: {e}")
    return error_file


def split_user_to_user(user_from_name, user_name):
    user_from_dir = util.construct_file_path(user_from_name, "")
    user_from_dir = user_from_dir[:len(user_from_dir) - 1]
    error_file = []
    user_dir = util.construct_file_path(user_name, "")
    user_dir = user_dir[:len(user_dir) - 1]

    # 🔥 使用 get_user_db_path 获取源用户的数据库路径（支持主库从库）
    user_from_db_path, _, _ = get_user_db_path(user_from_name)
    user_from_collection_name = util.construct_collection(user_from_name)
    if len(user_from_collection_name) > 63:
        user_from_collection_name = user_from_collection_name[:63]

    # 🔥 使用 get_or_create_collection 避免并发创建冲突
    try:
        user_from_client = chromadb.PersistentClient(path=user_from_db_path)
        try:
            user_from_client.get_collection(name=user_from_collection_name)
        except Exception:
            # Collection不存在，创建它
            user_from_client.create_collection(name=user_from_collection_name)
    except Exception as e:
        # 如果 collection 已存在（并发创建），忽略错误
        if "already exists" not in str(e).lower():
            print(f"[split_user_to_user] 源用户collection处理失败: {e}")

    vector_store_user_from = Chroma(
        collection_name=user_from_collection_name,
        embedding_function=embeddings,
        persist_directory=user_from_db_path  # 🔥 使用智能检测的路径
    )

    # 🔥 使用 get_user_db_path 获取目标用户的数据库路径（支持主库从库）
    actual_db_path, db_type, secondary_db_path = get_user_db_path(user_name)
    user_collection_name = util.construct_collection(user_name)
    if len(user_collection_name) > 63:
        user_collection_name = user_collection_name[:63]

    # 🔥 使用 get_or_create_collection 避免并发创建冲突
    try:
        user_client = chromadb.PersistentClient(path=actual_db_path)
        try:
            user_client.get_collection(name=user_collection_name)
        except Exception:
            # Collection不存在，创建它
            user_client.create_collection(name=user_collection_name)
    except Exception as e:
        # 如果 collection 已存在（并发创建），忽略错误
        if "already exists" not in str(e).lower():
            print(f"[split_user_to_user] 目标用户collection处理失败: {e}")

    vector_store_user = Chroma(
        collection_name=user_collection_name,
        embedding_function=embeddings,
        persist_directory=actual_db_path  # 🔥 使用智能检测的路径
    )
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)

    # 并行处理文件
    def process_single_file(f, vector_store_user_from, vector_store_user):
        user_from_doc_path = user_from_dir + "/" + f
        user_doc_path = user_dir + "/" + f
        print(f)

        if os.path.isdir(user_from_doc_path):
            if not f.endswith("_image"):
                return None
            # pdf = util.back_image_path(f)
            if not os.path.exists(user_doc_path):
                os.makedirs(user_doc_path)
            for image_f in os.listdir(user_from_doc_path):
                src_path = user_from_doc_path + "/" + image_f
                tar_path = user_doc_path + '/' + image_f
                shutil.copy(src_path, tar_path)
            # global_var.set_user_image(user_name, pdf, base_64)
            return None

        try:
            shutil.copy(user_from_doc_path, user_doc_path)
            split_docs = util.get_seq_doc_by_path([user_from_doc_path], vector_store_user_from)
            for split_doc in split_docs:
                # split_doc（文本、图片片段）指向PDF路径
                split_doc.metadata["source"] = split_doc.metadata["source"].replace(user_from_dir, user_dir)
                # split_doc（文本、图片片段）真实文件路径，如果存在的话!!!（pdf和图像文本分割后的metadata里都有多项，包括这两个；而txt分割后只有source）
                if "file_path" in split_doc.metadata:
                    split_doc.metadata["file_path"] = split_doc.metadata["file_path"].replace(user_from_dir,
                                                                                              user_dir)
            ids = util.construct_ids(user_doc_path, len(split_docs))
            n_add = len(split_docs) // 55
            for i in range(n_add):
                vector_store_user.add_documents(documents=split_docs[i * 55:(i + 1) * 55],
                                                ids=ids[i * 55:(i + 1) * 55])
                print(f"分割处理分享本子的用户增量文档add_documents批次{i}/{n_add}完成")
                time.sleep(0.5)
            vector_store_user.add_documents(documents=split_docs[n_add * 55:len(split_docs)],
                                            ids=ids[n_add * 55:len(split_docs)])
            # global_var.set_user_split(user_name, f, split_docs)
            return None
        except Exception as e:
            print(e)
            return f

    # 获取所有文件列表
    file_list = os.listdir(user_from_dir + "/")

    # 并行处理所有文件
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for f in file_list:
            future = executor.submit(process_single_file, f, vector_store_user_from, vector_store_user)
            futures.append(future)

        # 收集错误文件
        for future in futures:
            try:
                error_f = future.result()
                if error_f:
                    error_file.append(error_f)
            except Exception as e:
                print(f"处理文件时出错: {e}")
    return error_file

# 配置请求重试策略
def create_retry_session():
    session = requests.Session()

    # 检查 urllib3 版本并使用正确的参数名
    retry_kwargs = {
        'total': 3,
        'backoff_factor': 1,
        'status_forcelist': [429, 500, 502, 503, 504],
    }

    # 尝试使用新版本的参数名
    try:
        retry_strategy = Retry(
            **retry_kwargs,
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
    except TypeError:
        # 如果失败，使用旧版本的参数名
        retry_strategy = Retry(
            **retry_kwargs,
            method_whitelist=["HEAD", "GET", "OPTIONS"]
        )

    # retry_strategy = Retry(
    #     total=3,
    #     backoff_factor=1,
    #     status_forcelist=[429, 500, 502, 503, 504],
    #     allowed_methods=["HEAD", "GET", "OPTIONS"]
    # )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

# 使用重试会话替换默认的requests
requests_session = create_retry_session()