import os
import pickle
import hashlib
from langchain.schema import Document


class DocumentSplitCache:
    """简单的文档分割缓存工具"""

    def __init__(self, cache_dir="./document_split_cache"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def get_file_hash(self, file_path):
        """计算文件哈希值"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except:
            return None

    def get_cache_path(self, user_name, document_name):
        """获取缓存文件路径"""
        # 创建用户目录
        user_dir = os.path.join(self.cache_dir, user_name)
        os.makedirs(user_dir, exist_ok=True)

        # 清理文件名，避免特殊字符
        safe_name = "".join(c for c in document_name if c.isalnum() or c in (' ', '_', '-', '.')).strip()
        return os.path.join(user_dir, f"{safe_name}.pkl")

    def load_split_docs(self, user_name, document_name, file_path):
        """加载文档分割缓存"""
        cache_path = self.get_cache_path(user_name, document_name)

        if not os.path.exists(cache_path):
            return None

        try:
            with open(cache_path, 'rb') as f:
                cache_data = pickle.load(f)

            # 检查文件是否已变更
            current_hash = self.get_file_hash(file_path)
            if current_hash != cache_data.get('file_hash'):
                # 文件已变更，删除旧缓存
                os.remove(cache_path)
                return None

            # 恢复Document对象
            split_docs = []
            for doc_data in cache_data['split_docs']:
                split_docs.append(Document(
                    page_content=doc_data['page_content'],
                    metadata=doc_data['metadata']
                ))

            print(f"从缓存加载文档分割: {user_name}/{document_name}")
            return split_docs

        except Exception as e:
            print(f"加载缓存失败: {e}")
            return None

    def save_split_docs(self, user_name, document_name, file_path, split_docs):
        """保存文档分割缓存"""
        try:
            cache_path = self.get_cache_path(user_name, document_name)
            file_hash = self.get_file_hash(file_path)

            # 序列化Document对象
            docs_data = []
            for doc in split_docs:
                docs_data.append({
                    'page_content': doc.page_content,
                    'metadata': doc.metadata
                })

            cache_data = {
                'file_hash': file_hash,
                'split_docs': docs_data
            }

            with open(cache_path, 'wb') as f:
                pickle.dump(cache_data, f)

            print(f"保存文档分割缓存: {user_name}/{document_name}")
            return True

        except Exception as e:
            print(f"保存缓存失败: {e}")
            return False


# 全局缓存实例
doc_cache = DocumentSplitCache()
