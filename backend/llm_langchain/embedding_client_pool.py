# 简单的Embedding客户端复用池 - 临时方案
import threading
from openai import OpenAI
import time

class EmbeddingClientPool:
    """简单的Embedding客户端复用池"""
    
    def __init__(self):
        self._client = None
        self._lock = threading.Lock()
        self._created_at = None
        self._api_key = None
        self._base_url = None
        
    def get_client(self, api_key: str, base_url: str):
        """获取复用的OpenAI客户端"""
        with self._lock:
            # 如果客户端不存在或配置变化，创建新客户端
            if (self._client is None or 
                self._api_key != api_key or 
                self._base_url != base_url):
                
                print(f"[EmbeddingPool] 创建新的OpenAI客户端: {base_url}")
                self._client = OpenAI(
                    api_key=api_key,
                    base_url=base_url,
                    timeout=120,  # 增加超时时间
                    max_retries=3,  # 设置重试次数
                    default_headers={"x-foo": "true"}
                )
                self._api_key = api_key
                self._base_url = base_url
                self._created_at = time.time()
            else:
                print(f"[EmbeddingPool] 复用现有OpenAI客户端: {base_url}")
                
            return self._client
    
    def get_stats(self):
        """获取客户端状态"""
        with self._lock:
            return {
                'has_client': self._client is not None,
                'base_url': self._base_url,
                'created_at': self._created_at,
                'uptime': time.time() - self._created_at if self._created_at else 0
            }

# 全局单例
_embedding_pool = EmbeddingClientPool()

def get_embedding_client(api_key: str, base_url: str):
    """获取Embedding客户端（复用连接）"""
    return _embedding_pool.get_client(api_key, base_url)

def get_embedding_pool_stats():
    """获取连接池状态"""
    return _embedding_pool.get_stats() 