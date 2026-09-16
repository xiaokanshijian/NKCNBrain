import numpy as np
import re
import json
import hashlib
from typing import List, Dict, Tuple, Any
from collections import Counter, defaultdict
from dataclasses import dataclass
import math
import random
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
import jieba
import jieba.analyse
import warnings
warnings.filterwarnings('ignore')

# ==================== 嵌入模型选择 ====================

class EmbeddingModel:
    """统一的嵌入模型管理 - 使用固定维度的向量化方法"""
    def __init__(self, use_transformer=False, model_name=None, vector_dim=None):
        self.use_transformer = use_transformer
        self.vector_dim = vector_dim if vector_dim is not None else 300  # 默认300维
        self.cache = {}
        
        if use_transformer:
            try:
                # 尝试使用transformers库
                from transformers import AutoTokenizer, AutoModel
                import torch
                self.tokenizer = AutoTokenizer.from_pretrained(model_name or "bert-base-chinese")
                self.model = AutoModel.from_pretrained(model_name or "bert-base-chinese")
                self.model.eval()
                self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                self.model.to(self.device)
            except ImportError:
                print("transformers库不可用，切换到词向量模式")
                self.use_transformer = False
        
        if not self.use_transformer:
            # 使用简单的词向量方法，确保维度固定
            self.word_vectors = {}
            self.idf_weights = {}
    
    def embed(self, text: str) -> np.ndarray:
        """嵌入单个文本"""
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        if text_hash in self.cache:
            return self.cache[text_hash]
        
        if self.use_transformer:
            embedding = self._embed_transformer(text)
        else:
            embedding = self._embed_simple(text)
        
        self.cache[text_hash] = embedding
        return embedding
    
    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """批量嵌入"""
        embeddings = []
        for text in texts:
            embeddings.append(self.embed(text))
        return np.array(embeddings)
    
    def _embed_transformer(self, text: str) -> np.ndarray:
        """使用Transformer模型嵌入"""
        import torch
        
        # 截断文本避免超过最大长度
        max_length = 512
        inputs = self.tokenizer(
            text[:1000], 
            return_tensors="pt", 
            truncation=True, 
            max_length=max_length,
            padding=True
        )
        
        inputs = {k: v.to(self.device) for k, v in inputs.items()}
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            # 使用[CLS]令牌的表示或平均池化
            embeddings = outputs.last_hidden_state.mean(dim=1).cpu().numpy()
        
        return embeddings[0]
    
    def _embed_simple(self, text: str) -> np.ndarray:
        """使用简单的固定维度词向量"""
        # 分词并提取关键词
        words = list(jieba.cut(text))
        # 同时提取TF-IDF关键词增加语义信息
        try:
            keywords = jieba.analyse.extract_tags(text, topK=20, withWeight=True)
            keyword_dict = dict(keywords)
        except:
            keyword_dict = {}
        
        # 为每个词生成或获取向量
        word_vecs = []
        weights = []
        
        for word in words[:200]:  # 增加词数限制到200
            if word.strip():
                if word not in self.word_vectors:
                    # 为新词生成稳定的向量
                    np.random.seed(hash(word) % 2**32)
                    self.word_vectors[word] = np.random.randn(self.vector_dim) * 0.1
                
                # 获取词向量
                vec = self.word_vectors[word]
                word_vecs.append(vec)
                
                # 使用TF-IDF权重或默认权重
                weight = keyword_dict.get(word, 0.1) + 0.1
                weights.append(weight)
        
        if not word_vecs:
            # 如果没有词，返回小的随机向量
            np.random.seed(hash(text) % 2**32)
            return np.random.randn(self.vector_dim) * 0.01
        
        # 计算加权平均向量
        weights = np.array(weights)
        weights = weights / np.sum(weights)  # 归一化权重
        
        avg_vec = np.average(word_vecs, axis=0, weights=weights)
        
        # 添加一些文本特征
        text_features = np.zeros(10)
        text_features[0] = len(text) / 1000.0  # 文本长度特征
        text_features[1] = len(words) / 100.0  # 词数特征
        text_features[2] = len(set(words)) / len(words) if words else 0  # 词汇多样性
        
        # 将特征融合到向量中
        avg_vec[:10] = avg_vec[:10] * 0.9 + text_features * 0.1
        
        # 归一化
        norm = np.linalg.norm(avg_vec)
        if norm > 1e-6:
            avg_vec = avg_vec / norm
        
        return avg_vec

# ==================== 简化的文本相似度计算 ====================

class SimpleSimilarity:
    """不依赖深度学习的相似度计算"""
    
    @staticmethod
    def jaccard_similarity(text1: str, text2: str) -> float:
        """Jaccard相似度"""
        words1 = set(jieba.cut(text1))
        words2 = set(jieba.cut(text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    @staticmethod
    def keyword_overlap(text1: str, text2: str, topk: int = 10) -> float:
        """关键词重叠度"""
        try:
            keywords1 = set(jieba.analyse.extract_tags(text1, topK=topk))
            keywords2 = set(jieba.analyse.extract_tags(text2, topK=topk))
            
            if not keywords1 or not keywords2:
                return 0.0
            
            overlap = len(keywords1.intersection(keywords2))
            return overlap / min(len(keywords1), len(keywords2))
        except:
            return 0.0
    
    @staticmethod
    def edit_distance_similarity(text1: str, text2: str) -> float:
        """基于编辑距离的相似度"""
        # 为了效率，只比较前200个字符
        text1 = text1[:200]
        text2 = text2[:200]
        
        if not text1 or not text2:
            return 0.0
        
        len1, len2 = len(text1), len(text2)
        max_len = max(len1, len2)
        
        if max_len == 0:
            return 1.0
        
        # 简化的编辑距离
        common_chars = 0
        for c in set(text1):
            common_chars += min(text1.count(c), text2.count(c))
        
        return common_chars / max_len
    
    @staticmethod
    def semantic_similarity(text1: str, text2: str) -> float:
        """语义相似度 - 基于共同实体和数字"""
        # 提取实体和数字
        entities1 = set(extract_entities(text1))
        entities2 = set(extract_entities(text2))
        numbers1 = set(extract_numbers(text1))
        numbers2 = set(extract_numbers(text2))
        
        # 合并所有特征
        features1 = entities1.union(numbers1)
        features2 = entities2.union(numbers2)
        
        if not features1 and not features2:
            return 0.5
        elif not features1 or not features2:
            return 0.0
        
        # 计算交集
        common = features1.intersection(features2)
        union = features1.union(features2)
        
        return len(common) / len(union) if union else 0.0
    
    @staticmethod
    def calculate_similarity(text1: str, text2: str, method: str = "mixed") -> float:
        """综合相似度计算"""
        if method == "jaccard":
            return SimpleSimilarity.jaccard_similarity(text1, text2)
        elif method == "keyword":
            return SimpleSimilarity.keyword_overlap(text1, text2)
        elif method == "semantic":
            return SimpleSimilarity.semantic_similarity(text1, text2)
        else:  # mixed - 使用多种方法的加权平均
            jaccard = SimpleSimilarity.jaccard_similarity(text1, text2)
            keyword = SimpleSimilarity.keyword_overlap(text1, text2)
            edit = SimpleSimilarity.edit_distance_similarity(text1, text2)
            semantic = SimpleSimilarity.semantic_similarity(text1, text2)
            
            # 动态权重：如果某个方法得分特别高，增加其权重
            scores = [jaccard, keyword, edit, semantic]
            weights = [0.25, 0.35, 0.15, 0.25]
            
            # 如果有方法得分超过0.8，增加其权重
            for i, score in enumerate(scores):
                if score > 0.8:
                    weights[i] *= 1.5
            
            # 归一化权重
            total_weight = sum(weights)
            weights = [w/total_weight for w in weights]
            
            return sum(score * weight for score, weight in zip(scores, weights))

# 全局嵌入模型实例
embedding_model = None
simple_similarity = SimpleSimilarity()

def init_embedding_model(use_transformer=False, model_name=None, vector_dim=None):
    """初始化嵌入模型"""
    global embedding_model
    # 确保有默认值
    if vector_dim is None:
        vector_dim = 300
    embedding_model = EmbeddingModel(use_transformer=use_transformer, model_name=model_name, vector_dim=vector_dim)

# 默认初始化（使用简单词向量，300维）
init_embedding_model(use_transformer=False)

# ==================== 1. 准确性评分相关函数 ====================

def extract_facts(text: str) -> List[str]:
    """从文本中提取事实性陈述"""
    facts = []
    sentences = re.split(r'[。！？]', text)
    
    for sent in sentences:
        if not sent.strip():
            continue
        
        # 识别包含事实性信息的句子
        if any(pattern in sent for pattern in ['是', '有', '包含', '位于', '等于', '为']):
            facts.append(sent.strip())
        elif re.search(r'\d+', sent):  # 包含数字
            facts.append(sent.strip())
        elif re.search(r'[A-Z]', sent):  # 包含大写字母
            facts.append(sent.strip())
    
    return facts

def extract_entities(text: str) -> List[str]:
    """提取文本中的实体"""
    entities = []
    
    try:
        # 使用jieba进行词性标注
        import jieba.posseg as pseg
        words = pseg.cut(text)
        
        for word, flag in words:
            # nr: 人名, ns: 地名, nt: 组织机构名, nz: 其他专名
            if flag in ['nr', 'ns', 'nt', 'nz']:
                entities.append(word)
    except:
        # 降级到简单的实体识别
        # 提取被书名号、引号包围的内容
        patterns = [
            r'《([^》]+)》',
            r'"([^"]+)"',
            r'「([^」]+)」',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            entities.extend(matches)
    
    return entities

def extract_numbers(text: str) -> List[str]:
    """提取文本中的数值信息"""
    patterns = [
        r'\d+\.?\d*%',  # 百分比
        r'\d+\.?\d*',   # 普通数字
        r'[一二三四五六七八九十百千万亿]+',  # 中文数字
    ]
    
    numbers = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        numbers.extend(matches)
    
    return numbers

def detect_hallucination(response: str, rag_docs: str) -> float:
    """检测幻觉内容"""
    response_entities = extract_entities(response)
    response_numbers = extract_numbers(response)
    
    rag_entities = extract_entities(rag_docs)
    rag_numbers = extract_numbers(rag_docs)
    
    hallucinated_entities = set(response_entities) - set(rag_entities)
    hallucinated_numbers = set(response_numbers) - set(rag_numbers)
    
    total_items = len(response_entities) + len(response_numbers)
    if total_items == 0:
        return 0.0
    
    hallucinated_items = len(hallucinated_entities) + len(hallucinated_numbers)
    return min(1.0, hallucinated_items / total_items)

def key_info_coverage(response: str, rag_docs: str, user_query: str) -> float:
    """评估关键信息覆盖率"""
    try:
        query_keywords = jieba.analyse.extract_tags(user_query, topK=5)
        rag_keywords = jieba.analyse.extract_tags(rag_docs, topK=10)
        
        relevant_keywords = [
            kw for kw in rag_keywords 
            if any(qk in kw or kw in qk for qk in query_keywords)
        ]
        
        if not relevant_keywords:
            return 1.0
        
        covered = sum(1 for kw in relevant_keywords if kw in response)
        return covered / len(relevant_keywords)
    except:
        return 0.5  # 默认值

def accuracy_score(response: str, rag_docs: str, user_query: str) -> float:
    """综合评估准确性"""
    # 如果RAG文档为空或太短，返回低分
    if not rag_docs or len(rag_docs.strip()) < 20:
        return 0.3
    
    # 如果response太短，也要惩罚
    if len(response.strip()) < 30:
        base_penalty = 0.8
    else:
        base_penalty = 1.0

    # 1. 事实一致性
    response_facts = extract_facts(response)
    rag_facts = extract_facts(rag_docs)
    
    # 如果没有提取到事实，检查关键词重叠度
    if not response_facts or not rag_facts:
        # 使用关键词重叠作为备用方案
        response_keywords = set(jieba.analyse.extract_tags(response, topK=10))
        rag_keywords = set(jieba.analyse.extract_tags(rag_docs, topK=10))
        
        if response_keywords and rag_keywords:
            keyword_overlap = len(response_keywords.intersection(rag_keywords)) / len(rag_keywords)
            fact_consistency = keyword_overlap
        else:
            fact_consistency = 0.5
    else:
        # 原有逻辑
        if embedding_model:
            response_embed = embedding_model.embed(" ".join(response_facts))
            rag_embed = embedding_model.embed(" ".join(rag_facts))
            fact_consistency = float(cosine_similarity([response_embed], [rag_embed])[0][0])
        else:
            fact_consistency = simple_similarity.calculate_similarity(
                " ".join(response_facts), 
                " ".join(rag_facts)
            )
    
    # 添加语义相似度作为补充
    if embedding_model:
        # 直接计算response和rag_docs的整体相似度
        response_embed = embedding_model.embed(response[:500])
        rag_embed = embedding_model.embed(rag_docs[:500])
        semantic_similarity = float(cosine_similarity([response_embed], [rag_embed])[0][0])
        
        # 如果语义相似度高但事实提取失败，使用语义相似度
        if semantic_similarity > 0.7 and fact_consistency < 0.3:
            fact_consistency = semantic_similarity * 0.9

    # 多领域专业内容检测和处理
    domain_patterns = {
        # IT技术领域
        'tech': {
            'terms': ['错误', '代码', '0x', '驱动', '内存', '系统', '命令', 'bug', '蓝屏', '安装', '配置', 'API'],
            'solutions': ['更新', '检查', '运行', '修复', '重装', '备份', '调试', '重启', '设置', '优化']
        },
        # 医疗健康
        'medical': {
            'terms': ['症状', '诊断', '治疗', '药物', '病', '疼痛', '发热', '过敏', '感染', '炎症'],
            'solutions': ['服用', '检查', '就医', '休息', '避免', '预防', '康复', '用药', '手术', '理疗']
        },
        # 金融投资
        'finance': {
            'terms': ['投资', '股票', '基金', '收益', '风险', '市场', '利率', '资产', '债券', 'PE'],
            'solutions': ['配置', '买入', '卖出', '持有', '分散', '对冲', '定投', '止损', '分析', '评估']
        },
        # 法律咨询
        'legal': {
            'terms': ['合同', '法律', '权益', '诉讼', '条款', '责任', '赔偿', '仲裁', '违约', '证据'],
            'solutions': ['起诉', '协商', '调解', '申请', '维权', '举证', '上诉', '立案', '咨询', '代理']
        },
        # 教育培训
        'education': {
            'terms': ['课程', '学习', '培训', '考试', '作业', '成绩', '学分', '专业', '导师', '论文'],
            'solutions': ['练习', '复习', '报名', '选课', '辅导', '提升', '巩固', '预习', '测试', '评估']
        },
        # 电商客服
        'ecommerce': {
            'terms': ['订单', '发货', '退款', '物流', '商品', '售后', '快递', '支付', '优惠', '积分'],
            'solutions': ['退货', '换货', '补发', '赔偿', '处理', '跟踪', '申请', '联系', '反馈', '评价']
        },
        # 旅游规划
        'travel': {
            'terms': ['行程', '景点', '酒店', '机票', '签证', '导游', '路线', '预订', '交通', '住宿'],
            'solutions': ['预订', '安排', '规划', '推荐', '选择', '准备', '办理', '咨询', '确认', '取消']
        }
    }
    
    # 检测属于哪个领域
    detected_domain = None
    max_matches = 0
    
    for domain, patterns in domain_patterns.items():
        # 计算匹配的术语数量
        term_matches = sum(1 for term in patterns['terms'] 
                          if term in response or term in rag_docs)
        if term_matches > max_matches:
            max_matches = term_matches
            detected_domain = domain
    
    # 如果检测到专业领域（至少匹配2个术语）
    if detected_domain and max_matches >= 2:
        domain_info = domain_patterns[detected_domain]
        
        # 检查解决方案关键词的匹配
        response_solutions = sum(1 for kw in domain_info['solutions'] if kw in response)
        rag_solutions = sum(1 for kw in domain_info['solutions'] if kw in rag_docs)
        
        # 检查专业术语的匹配
        response_terms = sum(1 for term in domain_info['terms'] if term in response)
        rag_terms = sum(1 for term in domain_info['terms'] if term in rag_docs)
        
        # 计算领域匹配度
        if response_solutions > 0 and rag_solutions > 0:
            # 解决方案都有提到
            solution_match = min(response_solutions, rag_solutions) / max(response_solutions, rag_solutions)
            fact_consistency = max(fact_consistency, 0.5 + solution_match * 0.3)
        
        if response_terms >= 2 and rag_terms >= 2:
            # 专业术语都有使用
            term_match = min(response_terms, rag_terms) / max(response_terms, rag_terms)
            fact_consistency = max(fact_consistency, 0.4 + term_match * 0.3)
    
    # 通用改进：如果response和rag_docs都很长且有内容
    if len(response) > 200 and len(rag_docs) > 200:
        # 使用更宽松的关键词匹配
        response_keywords = set(jieba.analyse.extract_tags(response, topK=15))
        rag_keywords = set(jieba.analyse.extract_tags(rag_docs, topK=15))
        
        if response_keywords and rag_keywords:
            keyword_overlap = len(response_keywords.intersection(rag_keywords)) / len(rag_keywords)
            # 如果关键词重叠度高，提升基础分
            if keyword_overlap > 0.5:
                fact_consistency = max(fact_consistency, keyword_overlap)
    
    # ... 继续原有的幻觉检测和覆盖率计算
    # 2. 幻觉检测
    hallucination_penalty = detect_hallucination(response, rag_docs)
    
    # 3. 覆盖率
    coverage = key_info_coverage(response, rag_docs, user_query)
    
    # 综合得分
    # score = 0.5 * fact_consistency + 0.3 * (1 - hallucination_penalty) + 0.2 * coverage
    # 调整权重，减少幻觉惩罚的影响
    score = 0.65 * fact_consistency + 0.15 * (1 - hallucination_penalty) + 0.2 * coverage
    score = score * base_penalty
    return max(0.1, min(1, score))  # 最低0.1

# ==================== 2. 上下文精准性评分相关函数 ====================

def split_context(context: str) -> Tuple[str, str, str]:
    """将上下文分割为系统提示词、对话历史和RAG内容"""
    parts = {
        'system_prompt': '',
        'history': '',
        'rag_content': ''
    }
    
    # 尝试通过标记分割
    if '<system>' in context and '</system>' in context:
        system_match = re.search(r'<system>(.*?)</system>', context, re.DOTALL)
        if system_match:
            parts['system_prompt'] = system_match.group(1)
    
    if '<history>' in context and '</history>' in context:
        history_match = re.search(r'<history>(.*?)</history>', context, re.DOTALL)
        if history_match:
            parts['history'] = history_match.group(1)
    
    if '<rag>' in context and '</rag>' in context:
        rag_match = re.search(r'<rag>(.*?)</rag>', context, re.DOTALL)
        if rag_match:
            parts['rag_content'] = rag_match.group(1)
    
    # 如果没有标记，使用简单的长度分割
    if not any(parts.values()):
        lines = context.split('\n')
        total_lines = len(lines)
        if total_lines > 0:
            third = total_lines // 3
            parts['system_prompt'] = '\n'.join(lines[:third])
            parts['history'] = '\n'.join(lines[third:2*third])
            parts['rag_content'] = '\n'.join(lines[2*third:])
    
    return parts['system_prompt'], parts['history'], parts['rag_content']

def random_sample_chunks(context: str, n: int = 3, chunk_size: int = 100) -> List[str]:
    """从上下文中随机抽取文本块"""
    words = list(jieba.cut(context))
    chunks = []
    
    if len(words) < chunk_size:
        return [context]
    
    for _ in range(min(n, len(words) // chunk_size)):
        start = random.randint(0, max(0, len(words) - chunk_size))
        chunk = ''.join(words[start:start + chunk_size])
        chunks.append(chunk)
    
    return chunks

def context_precision_score(context: str, user_query: str) -> float:
    """多维度评估上下文精准性 - 增强版"""
    system_prompt, history, rag_content = split_context(context)
    
    # 计算上下文的丰富度指标
    context_length = len(context)
    context_richness = min(1.0, context_length / 1000)  # 每1000字符得满分
    
    # 2.1 整体相关性
    context_preview = context[:2000] if len(context) > 2000 else context
    
    # 提取查询关键词
    query_keywords = set(jieba.analyse.extract_tags(user_query, topK=10))
    context_keywords = set(jieba.analyse.extract_tags(context_preview, topK=30))
    
    # 关键词覆盖率
    keyword_coverage = len(query_keywords.intersection(context_keywords)) / len(query_keywords) if query_keywords else 0.5
    
    # 语义相似度
    if embedding_model:
        context_embed = embedding_model.embed(context_preview)
        query_embed = embedding_model.embed(user_query)
        vector_sim = float(cosine_similarity([context_embed], [query_embed])[0][0])
    else:
        vector_sim = 0.5
    
    text_sim = simple_similarity.calculate_similarity(context_preview, user_query)
    
    # 综合整体相关性（提高基础分）
    overall_relevance = 0.3 * keyword_coverage + 0.3 * vector_sim + 0.4 * text_sim
    
    # 2.2 RAG内容相关性（重点评估）
    if rag_content.strip():
        rag_keywords = set(jieba.analyse.extract_tags(rag_content, topK=20))
        rag_coverage = len(query_keywords.intersection(rag_keywords)) / len(query_keywords) if query_keywords else 0.5
        
        if embedding_model:
            rag_embed = embedding_model.embed(rag_content[:1000])
            rag_sim = float(cosine_similarity([rag_embed], [query_embed])[0][0])
        else:
            rag_sim = simple_similarity.calculate_similarity(rag_content[:1000], user_query)
        
        rag_relevance = 0.5 * rag_coverage + 0.5 * rag_sim
    else:
        rag_relevance = 0.3
    
    # 2.3 历史对话相关性
    if history.strip():
        # 检查历史对话是否与当前查询相关
        history_keywords = set(jieba.analyse.extract_tags(history, topK=15))
        history_coverage = len(query_keywords.intersection(history_keywords)) / len(query_keywords) if query_keywords else 0.3
        
        history_relevance = history_coverage
    else:
        history_relevance = 0.3
    
    # 2.4 滑动窗口分析（简化以提高效率）
    words = list(jieba.cut(context))
    window_size = min(80, max(20, len(words) // 10))
    stride = max(40, window_size // 2)
    
    high_relevance_count = 0
    total_windows = 0
    
    for i in range(0, max(1, len(words) - window_size + 1), stride):
        window = ''.join(words[i:i+window_size])
        if window.strip():
            # 快速检查是否包含查询关键词
            window_score = sum(1 for kw in query_keywords if kw in window) / len(query_keywords) if query_keywords else 0.3
            if window_score > 0.5:
                high_relevance_count += 1
            total_windows += 1
    
    window_relevance = high_relevance_count / total_windows if total_windows > 0 else 0.5
    
    # 2.5 结构完整性
    has_system = 1.0 if system_prompt.strip() else 0.5
    has_history = 1.0 if history.strip() else 0.7
    has_rag = 1.0 if rag_content.strip() else 0.3
    
    structure_score = (has_system * 0.2 + has_history * 0.2 + has_rag * 0.6)
    
    # 综合得分（优化权重分配）
    if context_length < 100:
        # 极简上下文的评分策略
        precision_score = (
            0.40 * overall_relevance +
            0.40 * rag_relevance +
            0.20 * structure_score
        )
        # 对极简内容的惩罚
        precision_score = precision_score * 0.9
    else:
        # 正常或丰富上下文的评分策略
        precision_score = (
            0.20 * overall_relevance +      # 整体相关性
            0.35 * rag_relevance +          # RAG相关性（最重要）
            0.10 * history_relevance +       # 历史相关性
            0.15 * window_relevance +        # 窗口相关性
            0.10 * structure_score +         # 结构完整性
            0.10 * context_richness         # 内容丰富度奖励
        )
    
    # 基础分数调整（提高整体分数）
    precision_score = 0.35 + 0.65 * precision_score
    
    return max(0, min(1, precision_score))

# ==================== 3. 完整多样性评分相关函数 ====================

def split_into_chunks(text: str, chunk_size: int = 100) -> List[str]:
    """将文本分割成块"""
    words = list(jieba.cut(text))
    chunks = []
    
    for i in range(0, len(words), chunk_size):
        chunk = ''.join(words[i:i+chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    
    return chunks if chunks else [text]

def calculate_semantic_diversity(chunks: List[str]) -> float:
    """计算语义多样性"""
    if len(chunks) < 2:
        return 1.0
    
    # 限制chunk数量
    chunks = chunks[:10]
    
    similarities = []
    for i in range(len(chunks)):
        for j in range(i+1, len(chunks)):
            if embedding_model:
                embed1 = embedding_model.embed(chunks[i])
                embed2 = embedding_model.embed(chunks[j])
                sim = float(cosine_similarity([embed1], [embed2])[0][0])
            else:
                sim = simple_similarity.calculate_similarity(chunks[i], chunks[j])
            
            similarities.append(sim)
    
    if not similarities:
        return 1.0
    
    avg_similarity = np.mean(similarities)
    diversity = 1 - avg_similarity
    
    return 0.3 + 0.7 * diversity

def calculate_information_entropy(text: str) -> float:
    """计算信息熵"""
    words = list(jieba.cut(text))
    word_freq = Counter(words)
    total_words = len(words)
    
    if total_words == 0:
        return 0.0
    
    entropy = 0
    for count in word_freq.values():
        p = count / total_words
        if p > 0:
            entropy -= p * math.log2(p)
    
    max_entropy = math.log2(min(total_words, 100))  # 限制最大熵
    if max_entropy > 0:
        normalized_entropy = entropy / max_entropy
    else:
        normalized_entropy = 0
    
    return min(1.0, normalized_entropy)

def extract_topics(text: str, topK: int = 10) -> List[str]:
    """提取文本主题"""
    try:
        keywords = jieba.analyse.extract_tags(text, topK=topK, withWeight=False)
        return keywords
    except:
        return []

def max_expected_topics(user_query: str) -> int:
    """估算期望的主题数量"""
    query_length = len(user_query)
    
    if query_length < 20:
        return 3
    elif query_length < 50:
        return 5
    elif query_length < 100:
        return 8
    else:
        return 10

def completeness_diversity_score(context: str, user_query: str) -> float:
    """评估完整性和多样性"""
    chunks = split_into_chunks(context)
    
    relevance_scores = []
    for chunk in chunks[:20]:  # 限制数量
        if embedding_model:
            chunk_embed = embedding_model.embed(chunk)
            query_embed = embedding_model.embed(user_query)
            score = float(cosine_similarity([chunk_embed], [query_embed])[0][0])
        else:
            score = simple_similarity.calculate_similarity(chunk, user_query)
        
        relevance_scores.append(score)
    
    if not relevance_scores:
        return 0.5
    
    # 相关度分布
    relevance_distribution = {
        'high': sum(s > 0.8 for s in relevance_scores) / len(relevance_scores),
        'medium': sum(0.4 <= s <= 0.8 for s in relevance_scores) / len(relevance_scores),
        'low': sum(0.2 <= s < 0.4 for s in relevance_scores) / len(relevance_scores),
        'noise': sum(s < 0.2 for s in relevance_scores) / len(relevance_scores)
    }
    
    ideal_distribution = {'high': 0.3, 'medium': 0.5, 'low': 0.15, 'noise': 0.05}
    distribution_score = 1 - sum(
        abs(relevance_distribution[k] - ideal_distribution[k]) 
        for k in ideal_distribution
    ) / 2
    
    diversity_score = calculate_semantic_diversity(chunks)
    entropy_score = calculate_information_entropy(context)
    
    topics = extract_topics(context)
    expected_topics = max_expected_topics(user_query)
    topic_coverage = len(topics) / expected_topics if expected_topics > 0 else 1.0
    
    final_score = (
        0.35 * distribution_score +
        0.25 * diversity_score +
        0.20 * entropy_score +
        0.20 * min(topic_coverage, 1.0)
    )
    
    return max(0, min(1, final_score))

# ==================== 4. 上下文健康监控相关函数 ====================

def calculate_noise_ratio(conversation_history: str) -> float:
    """计算噪声比例"""
    lines = conversation_history.split('\n')
    if not lines:
        return 0
    
    noise_patterns = [
        r'^\s*$',  # 空行
        r'^[^\u4e00-\u9fa5a-zA-Z0-9]+$',  # 纯符号行
        r'^.{1,3}$',  # 过短的行
    ]
    
    noise_count = 0
    for line in lines:
        if any(re.match(pattern, line) for pattern in noise_patterns):
            noise_count += 1
    
    return noise_count / len(lines)

def calculate_coherence(conversation_history: str) -> float:
    """计算对话连贯性 - 优化版"""
    # 按换行符和句号分割
    sentences = re.split(r'[。！？\n]+', conversation_history)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]
    
    # 短文本优势太大，需要平衡
    if len(sentences) < 2:
        return 0.5  # 从0.8降低到0.5，避免极短文本得高分
    
    # 检测对话结构
    has_dialog_structure = any('用户' in s or '助手' in s for s in sentences)
    structure_bonus = 0.15 if has_dialog_structure else 0
    
    # 对长文本更友好
    if len(conversation_history) > 500:
        # 长文本基础分提高
        base_score = 0.4
        # 只比较部分句子对，避免过度惩罚
        max_pairs = min(10, len(sentences) - 1)
    else:
        base_score = 0.3
        max_pairs = min(20, len(sentences) - 1)

    # 对不同类型内容采用不同策略
    # 增强结构化内容检测
    structure_patterns = [
        r'^\d+[\.、]',                    # 数字编号：1. 1、
        r'^[•·▪➢➤]',                     # 项目符号
        r'^[①②③④⑤⑥⑦⑧⑨⑩]',            # 圆圈数字
        r'^[A-Za-z]\.',                   # 字母编号：A. B.
        r'^第[一二三四五六七八九十\d]+[章节条项]', # 中文编号
        r'^[\-\*\+]\s',                   # 列表符号：- * +
        r'^\[[\dA-Za-z]+\]',              # 方括号编号：[1] [A]
    ]

    # 增强对话形式检测
    dialog_indicators = [
        '用户:', 'User:', '人类:', 'Human:', '提问:', '回答:', 'Q:',
        '助手:', 'Assistant:', 'AI:', '机器人:', '系统:', 'A:',
        '客服:', 'Customer:', 'Support:',
        '用户：', '人类：', '提问：', '回答：', '助手：', '机器人：', '系统：', '客服：'
    ]

    # 计算结构化程度
    structure_score = 0
    lines = conversation_history.split('\n')
    non_empty_lines = [line.strip() for line in lines if line.strip()]

    for line in non_empty_lines:
        for pattern in structure_patterns:
            if re.search(pattern, line):
                structure_score += 1
                break

    structure_ratio = structure_score / len(non_empty_lines) if non_empty_lines else 0

    # 计算对话特征强度
    dialog_score = sum(1 for indicator in dialog_indicators if indicator in conversation_history)

    # 智能评分策略
    if dialog_score >= 3:  # 明显对话特征
        base_score = 0.55
    elif dialog_score >= 1:  # 轻微对话特征
        base_score = 0.52
    elif structure_ratio > 0.6:  # 高度结构化
        base_score = 0.5
    elif structure_ratio > 0.3:  # 中等结构化
        base_score = 0.45

    coherence_scores = []
    
    # 限制比较的句子对数量，避免计算过慢
    # max_pairs = min(20, len(sentences) - 1)
    
    for i in range(max_pairs):
        if i < len(sentences) - 1 and sentences[i] and sentences[i+1]:
            # 使用多种方法计算相似度
            
            # 1. 关键词重叠
            keywords1 = set(jieba.cut(sentences[i]))
            keywords2 = set(jieba.cut(sentences[i+1]))
            keyword_overlap = len(keywords1.intersection(keywords2)) / max(len(keywords1), len(keywords2), 1)
            
            # 2. 语义相似度
            if embedding_model:
                embed1 = embedding_model.embed(sentences[i])
                embed2 = embedding_model.embed(sentences[i+1])
                vec_sim = float(cosine_similarity([embed1], [embed2])[0][0])
            else:
                vec_sim = simple_similarity.calculate_similarity(sentences[i], sentences[i+1])
            
            # 3. 主题连续性（检查是否有共同的实体或概念）
            entities1 = set(extract_entities(sentences[i]))
            entities2 = set(extract_entities(sentences[i+1]))
            entity_continuity = 1.0 if entities1.intersection(entities2) else 0.3
            
            # 综合得分
            score = 0.3 * keyword_overlap + 0.5 * vec_sim + 0.2 * entity_continuity
            coherence_scores.append(score)
    
    if not coherence_scores:
        # return 0.5
        return 0.4 + structure_bonus
    
    # 计算平均连贯性，但对过低的分数进行平滑
    avg_coherence = np.mean(coherence_scores)
    
    # 基础分数调整，避免过低
    # adjusted_coherence = 0.3 + 0.7 * avg_coherence
    # 更平衡的调整
    adjusted_coherence = base_score + 0.55 * avg_coherence
    
    return min(1.0, adjusted_coherence)

def calculate_recency_weight(conversation_history: str) -> float:
    """计算新鲜度权重 - 优化版"""
    lines = conversation_history.split('\n')
    lines = [l for l in lines if l.strip()]  # 过滤空行
    
    if not lines:
        return 1.0
    
    # 分析内容结构
    total_length = len(conversation_history)
    
    # 1. 计算最近内容的比重
    if total_length > 0:
        recent_ratio = len(lines[-min(5, len(lines)):]) / len(lines)
    else:
        recent_ratio = 1.0
    
    # 2. 内容质量评分
    quality_scores = []
    weights = np.linspace(0.3, 1.0, len(lines))  # 越新的内容权重越高
    
    for i, line in enumerate(lines):
        if line.strip():
            # 质量指标：长度、信息密度、关键词数量
            length_score = min(1.0, len(line) / 100)
            
            # 信息密度：实体和数字的数量
            entities = extract_entities(line)
            numbers = extract_numbers(line)
            info_density = min(1.0, (len(entities) + len(numbers)) / 5)
            
            # 关键词数量
            keywords = jieba.analyse.extract_tags(line, topK=5)
            keyword_score = min(1.0, len(keywords) / 3)
            
            quality = (length_score * 0.4 + info_density * 0.3 + keyword_score * 0.3)
            quality_scores.append(weights[i] * quality)
    
    if not quality_scores:
        return 0.5
    
    # 3. 计算信息衰减（检查是否有重复内容）
    unique_lines = set(lines)
    uniqueness_ratio = len(unique_lines) / len(lines)
    
    # 综合新鲜度得分
    freshness = (
        0.3 * recent_ratio +           # 最近内容比重
        0.4 * np.mean(quality_scores) +  # 加权质量分
        0.3 * uniqueness_ratio          # 内容独特性
    )
    
    # 基础分数调整
    adjusted_freshness = 0.4 + 0.6 * freshness
    
    return min(1.0, adjusted_freshness)

def calculate_complexity(text: str) -> float:
    """计算内容复杂度 - 优化版"""
    if not text or len(text) < 10:
        return 0.1
    
    # 检测是否为噪声内容
    # 噪声模式列表
    noise_patterns = [
        r'[？！]{3,}',          # 连续问号/感叹号 
        r'~{2,}',               # 连续波浪号
        r'ERROR|error',         # 错误提示
        r'啊{2,}',              # 重复字符
        r'emmm+',               # 语气词
    ]

    # 特殊符号模式（单独处理）
    special_char_pattern = r'[!@#$%^&*()_+\-=\[\]{}\\|;:\'",.<>/?]{4,}'  # 连续4个及以上特殊符号

    # 计算噪声匹配总数（除特殊符号外）
    total_noise_matches = 0
    for pattern in noise_patterns:
        matches = re.findall(pattern, text)
        total_noise_matches += len(matches)

    # 计算特殊符号匹配次数
    special_char_matches = len(re.findall(special_char_pattern, text))

    # 计算文本长度
    text_length = len(text)

    # 根据文本长度设置不同的阈值
    if text_length > 500:  # 长文本
        noise_threshold = 6
        special_threshold = 4
    elif text_length > 100:  # 中等文本
        noise_threshold = 4
        special_threshold = 2
    else:  # 短文本
        noise_threshold = 3
        special_threshold = 1

    # 噪声检测逻辑
    if total_noise_matches >= noise_threshold or special_char_matches >= special_threshold:
        return 0.1  # 噪声内容直接返回低复杂度
    
    # 检查无意义重复
    lines = text.split('\n')
    non_empty_lines = [line.strip() for line in lines if line.strip()]

    if len(non_empty_lines) >= 8:  # 只在有足够行数时检查
        unique_lines = set(non_empty_lines)
        repetition_ratio = len(unique_lines) / len(non_empty_lines)
        
        if repetition_ratio < 0.1:  # 超过90%重复
            return 0.05
        elif repetition_ratio < 0.2:  # 80%-90%重复
            return 0.1
        elif repetition_ratio < 0.3:  # 70%-80%重复
            return 0.15
    
    # 检查是否有实质内容
    chinese_ratio = len(re.findall(r'[\u4e00-\u9fa5]', text)) / len(text)
    if chinese_ratio < 0.3:  # 中文比例太低
        complexity_penalty = 0.5
    else:
        complexity_penalty = 1.0
    
    # 1. 实体密度（每100字符的实体数）
    entities = extract_entities(text)
    entity_density = min(1.0, len(entities) / max(1, len(text) / 100))
    
    # 2. 数据密度（数字、百分比等）
    numbers = extract_numbers(text)
    data_density = min(1.0, len(numbers) / max(1, len(text) / 100))
    
    # 3. 结构化程度
    structure_markers = ['1.', '2.', '3.', '-', '•', '：', '(%)', '/', '|']
    structure_count = sum(1 for marker in structure_markers if marker in text)
    structure_score = min(1.0, structure_count / 5)  # 5个标记得满分
    
    # 4. 词汇多样性
    words = list(jieba.cut(text))
    unique_words = set(words)
    vocab_diversity = len(unique_words) / len(words) if words else 0
    
    # 5. 关键词密度
    try:
        keywords = jieba.analyse.extract_tags(text, topK=15)
        keyword_density = min(1.0, len(keywords) / 10)
    except:
        keyword_density = 0.3
    
    # 综合复杂度得分
    complexity = (
        0.25 * entity_density +
        0.25 * data_density +
        0.20 * structure_score +
        0.15 * vocab_diversity +
        0.15 * keyword_density
    ) * complexity_penalty
    
    # 检测代码内容
    code_indicators = ['def ', 'async ', 'import ', 'class ', 'function', '```', 'try:', 'except:']
    code_count = sum(1 for ind in code_indicators if ind in text)
    if code_count >= 4:
        # 代码内容基础复杂度不低于0.4
        return max(0.4, complexity)
    
    # 检测数学内容
    math_indicators = ['P(', '×', '÷', '∑', '∫', '=', 'log', 'sin', 'cos', '%']
    math_count = sum(1 for ind in math_indicators if ind in text)
    if math_count >= 5:
        # 数学内容基础复杂度不低于0.4
        return max(0.4, complexity)
    
    # 检测学术指标
    academic_indicators = ['p<', 'CI:', 'n=', '%)', 'et al.', '研究', '实验', '结果表明']
    academic_count = sum(1 for ind in academic_indicators if ind in text)
    if academic_count >= 3:
        # 学术内容基础复杂度不低于0.4
        return max(0.4, complexity)

    return min(1.0, complexity)

def context_health_monitor(conversation_history: str, max_context_length: int = 4000) -> Tuple[Dict[str, float], Dict[str, float]]:
    """监控上下文健康度"""
    current_length = len(conversation_history)
    
    indicators = {
        'length_ratio': min(1.0, current_length / max_context_length),
        'noise_ratio': calculate_noise_ratio(conversation_history),
        'coherence_score': calculate_coherence(conversation_history),
        'complexity': calculate_complexity(conversation_history)
    }
    
    # 动态调整权重
    if indicators['complexity'] > 0.7:
        # 高复杂度内容，准确性更重要
        weights = {'accuracy': 0.45, 'precision': 0.3, 'diversity': 0.25}
    elif indicators['complexity'] < 0.3:  
        # 低复杂度内容，精准性更重要
        weights = {'accuracy': 0.3, 'precision': 0.45, 'diversity': 0.25}
    elif indicators['noise_ratio'] > 0.3:
        # 高噪声，降低所有权重
        weights = {'accuracy': 0.35, 'precision': 0.35, 'diversity': 0.3}
    else:
        # 正常情况
        weights = {'accuracy': 0.38, 'precision': 0.35, 'diversity': 0.27}
    
    return weights, indicators

# ==================== 5. 主评估类 ====================

class ContextQualityEvaluator:
    """上下文质量评估器主类"""
    
    def __init__(self, use_transformer: bool = False, embedding_model_name: str = None, vector_dim: int = 300):
        """
        初始化评估器
        
        Args:
            use_transformer: 是否使用Transformer模型（需要transformers库）
            embedding_model_name: 模型名称
            vector_dim: 向量维度（仅在非transformer模式下使用，默认300）
        """
        global embedding_model
        # 确保向量维度始终有值
        if vector_dim is None:
            vector_dim = 300
        init_embedding_model(use_transformer=use_transformer, model_name=embedding_model_name, vector_dim=vector_dim)
        
        self.weights = {
            'subjective': 0.4,
            'objective': 0.6
        }
        
        self.thresholds = {
            'excellent': 0.85,
            'good': 0.70,
            'fair': 0.50,
            'poor': 0.30
        }
    
    def evaluate(self, 
                response: str, 
                context: str, 
                user_query: str, 
                rag_docs: str, 
                red_blue_score: float) -> Dict[str, Any]:
        """
        综合评估方法 - 增强区分度版
        """
        try:
            # 客观评分计算
            accuracy = accuracy_score(response, rag_docs, user_query)
            precision = context_precision_score(context, user_query)
            diversity = completeness_diversity_score(context, user_query)
            
            # 动态权重和健康度
            obj_weights, health = context_health_monitor(context)
            
            # 内容长度和复杂度
            content_length = len(context)
            complexity = health.get('complexity', 0.1)
            
            # === 激进的区分策略 ===
            
            # 1. 对极短内容的严格惩罚
            if content_length < 200:
                length_penalty = 0.85  # 15%惩罚
                accuracy = accuracy * length_penalty
                precision = precision * length_penalty  
                diversity = diversity * length_penalty
                
                # 复杂度低的额外惩罚
                if complexity < 0.2:
                    complexity_penalty = 0.9
                    accuracy = accuracy * complexity_penalty
                    precision = precision * complexity_penalty
                    diversity = diversity * complexity_penalty
            
            # 2. 对中等内容的轻微调整
            elif content_length < 600:
                length_penalty = 0.95  # 5%惩罚
                accuracy = accuracy * length_penalty
                precision = precision * length_penalty
                diversity = diversity * length_penalty
            
            # 3. 对丰富内容的奖励
            elif content_length > 1000:
                # 基础奖励
                length_bonus = 1.08  # 8%奖励
                
                # 如果各项指标都不错，额外奖励
                if accuracy > 0.7 and precision > 0.5 and diversity > 0.6:
                    quality_bonus = 1.05  # 额外5%
                    accuracy = min(0.95, accuracy * length_bonus * quality_bonus)
                    precision = min(0.90, precision * length_bonus * quality_bonus)
                    diversity = min(0.95, diversity * length_bonus * quality_bonus)
                else:
                    accuracy = min(0.90, accuracy * length_bonus)
                    precision = min(0.85, precision * length_bonus)
                    diversity = min(0.90, diversity * length_bonus)
                
                # 高复杂度额外奖励
                if complexity > 0.5:
                    complexity_bonus = 1.03
                    accuracy = min(0.95, accuracy * complexity_bonus)
                    precision = min(0.90, precision * complexity_bonus)
                    diversity = min(0.95, diversity * complexity_bonus)
            
            # 4. 基于健康度的额外调整
            complexity = health.get('complexity', 0.1)
            coherence = health.get('coherence_score', 0.5)
            
            # 新鲜度和连贯性都好的奖励
            if complexity > 0.6 and coherence > 0.5:
                health_bonus = 1.02
                precision = min(0.95, precision * health_bonus)
                accuracy = min(0.95, accuracy * health_bonus)
            
            # 5. 计算客观总分
            objective_score = (
                obj_weights['accuracy'] * accuracy +
                obj_weights['precision'] * precision +
                obj_weights['diversity'] * diversity
            )
            
            # 6. 动态调整主客观权重（根据内容质量）
            if content_length < 300 and complexity < 0.3:
                # 简单内容，降低主观分影响
                final_weights = {'subjective': 0.30, 'objective': 0.70}
            elif content_length > 1000 and complexity > 0.5:
                # 复杂丰富内容，平衡主客观
                final_weights = {'subjective': 0.45, 'objective': 0.55}
            else:
                # 正常情况
                final_weights = {'subjective': 0.40, 'objective': 0.60}
            
            # 7. 计算最终得分
            final_score = (
                final_weights['subjective'] * red_blue_score +
                final_weights['objective'] * objective_score
            )
            
            # 8. 最后的区分度增强
            # 对极短劣质内容更严格
            if content_length < 100 and complexity < 0.3:
                final_score = final_score * 0.7  # 30%惩罚
                final_score = min(0.55, final_score)  # 上限0.55
            # 对中等质量内容
            elif 100 <= content_length < 500:
                if complexity < 0.4 and accuracy < 0.5:
                    final_score = final_score * 0.85  # 15%惩罚
            # 对高质量内容更大奖励
            elif content_length > 1000:
                if complexity > 0.7 and accuracy > 0.6:
                    final_score = final_score * 1.2  # 20%奖励
                    final_score = max(0.75, final_score)  # 下限0.75
                elif complexity > 0.5:
                    final_score = final_score * 1.1  # 10%奖励
                
                # 如果客观分高，进一步提升
                if objective_score > 0.7:
                    final_score = min(0.8, final_score * 1.05)

            # 对excellent内容更激进的奖励
            if content_length > 1000 and complexity > 0.8:
                # 超长且复杂的优质内容
                if accuracy > 0.4 and precision > 0.4:  # 降低阈值
                    bonus = 1.25
                    final_score = final_score * bonus
                    final_score = max(0.8, min(0.95, final_score))  # 保证在0.8-0.95之间

            # 对医疗、金融、旅游、教育等专业领域的奖励
            professional_indicators = ['诊断', '治疗', '症状', '投资', '分析', '市场', '行程', '景点', '教育', '模型', '法律', '法则']
            is_professional = any(ind in response for ind in professional_indicators)
            
            if is_professional and complexity > 0.8:
                final_score = final_score * 1.06  # 6%专业内容奖励

            # 评级
            rating = self._get_rating(final_score)
            
            # 生成建议
            recommendations = self._generate_recommendations(health, accuracy, precision, diversity)
            
            return {
                'final_score': round(final_score, 3),
                'rating': rating,
                'breakdown': {
                    'subjective': round(red_blue_score, 3),
                    'objective': round(objective_score, 3),
                    'accuracy': round(accuracy, 3),
                    'precision': round(precision, 3),
                    'diversity': round(diversity, 3)
                },
                'context_health': {
                    k: round(v, 3) for k, v in health.items()
                },
                'dynamic_weights': {
                    k: round(v, 3) for k, v in obj_weights.items()
                },
                'final_weights_used': {
                    k: round(v, 3) for k, v in final_weights.items()
                },
                'content_length': content_length,
                'recommendations': recommendations
            }
            
        except Exception as e:
            print(f"评估过程中出现错误: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'final_score': red_blue_score,
                'rating': self._get_rating(red_blue_score),
                'error': str(e),
                'breakdown': {
                    'subjective': round(red_blue_score, 3),
                    'objective': 0.5
                },
                'recommendations': ["评估过程出错，请检查输入数据"]
            }
    
    def _get_rating(self, score: float) -> str:
        """根据分数返回评级"""
        if score >= self.thresholds['excellent']:
            return '优秀'
        elif score >= self.thresholds['good']:
            return '良好'
        elif score >= self.thresholds['fair']:
            return '中等'
        elif score >= self.thresholds['poor']:
            return '较差'
        else:
            return '很差'
    
    def _generate_recommendations(self, 
                                 health: Dict[str, float],
                                 accuracy: float,
                                 precision: float,
                                 diversity: float) -> List[str]:
        """生成改进建议 - 智能版"""
        recommendations = []
        
        # 计算整体质量等级
        overall_score = (accuracy + precision + diversity) / 3
        
        # 根据整体分数给出总体评价
        if overall_score > 0.75:
            recommendations.append("🏆 整体表现优秀！继续保持当前策略")
        elif overall_score > 0.6:
            recommendations.append("👍 整体表现良好，仍有优化空间")
        elif overall_score > 0.45:
            recommendations.append("📈 整体表现中等，建议重点优化薄弱环节")
        else:
            recommendations.append("⚠️ 需要全面改进上下文质量")
        
        # 内容量相关建议
        length_ratio = health.get('length_ratio', 0)
        if length_ratio < 0.05:
            recommendations.append(f"📝 内容极少（仅使用{length_ratio:.1%}），建议：\n" +
                                "   - 添加更多对话历史\n" +
                                "   - 丰富RAG文档内容\n" +
                                "   - 提供更详细的系统提示")
        elif length_ratio < 0.2:
            recommendations.append(f"💡 上下文使用率仅{length_ratio:.1%}，可以添加更多相关信息")
        elif length_ratio > 0.8:
            recommendations.append(f"⚠️ 上下文使用率达到{length_ratio:.1%}，建议精简内容或开启新对话")
        
        # 噪声相关建议
        noise_ratio = health.get('noise_ratio', 0)
        if noise_ratio < 0.05:
            recommendations.append(f"✅ 内容纯净度良好（噪声仅{noise_ratio:.1%}）")
        elif noise_ratio > 0.2:
            recommendations.append(f"🔧 噪声比例{noise_ratio:.1%}偏高，建议过滤无关内容")
        
        # 连贯性建议（根据具体分数给出不同建议）
        coherence = health.get('coherence_score', 1)
        if coherence < 0.35:
            recommendations.append(f"❌ 连贯性严重不足（{coherence:.1%}），建议：\n" +
                                "   - 重新组织对话流程\n" +
                                "   - 确保问答之间的逻辑关联\n" +
                                "   - 避免主题突然跳跃")
        elif coherence < 0.5:
            recommendations.append(f"📝 连贯性得分{coherence:.1%}偏低，建议：\n" +
                                "   - 确保对话上下文逻辑连贯\n" +
                                "   - 保持主题的一致性\n" +
                                "   - 使用过渡词连接不同部分")
        elif coherence > 0.7:
            recommendations.append(f"✨ 对话连贯性良好（{coherence:.1%}）")
        
        # 添加复杂度建议
        complexity = health.get('complexity', 0.5)
        if complexity < 0.3:
            recommendations.append(f"📊 内容复杂度较低（{complexity:.1%}），建议：\n" +
                                "   - 添加更多具体数据和实体信息\n" +
                                "   - 增加结构化内容（列表、分类等）\n" +
                                "   - 丰富词汇和关键概念")
        elif complexity > 0.7:
            recommendations.append(f"💎 内容复杂度良好（{complexity:.1%}），信息密度适中")
        elif complexity > 0.9:
            recommendations.append(f"⚠️ 内容过于复杂（{complexity:.1%}），可能需要简化")
        
        # 准确性建议
        if accuracy > 0.85:
            recommendations.append(f"🎯 准确性表现优秀（{accuracy:.1%}）")
        elif accuracy > 0.7:
            recommendations.append(f"✅ 准确性良好（{accuracy:.1%}），继续保持")
        elif accuracy < 0.6:
            recommendations.append(f"❌ 准确性{accuracy:.1%}不足，建议：\n" +
                                "   - 检查RAG文档质量\n" +
                                "   - 确保回答基于文档事实\n" +
                                "   - 避免添加未验证的信息")
        
        # 精准性建议（区分不同级别）
        if precision < 0.4:
            recommendations.append(f"🎲 精准性{precision:.1%}较低，建议：\n" +
                                "   - 增强RAG内容与查询的相关性\n" +
                                "   - 优化关键词匹配\n" +
                                "   - 考虑使用BERT等预训练模型")
        elif precision < 0.6:
            recommendations.append(f"🎲 精准性{precision:.1%}有待提升，建议：\n" +
                                "   - 使用更相关的RAG文档\n" +
                                "   - 优化检索策略\n" +
                                "   - 考虑使用更好的嵌入模型")
        elif precision > 0.7:
            recommendations.append(f"🎯 上下文精准性优秀（{precision:.1%}）")
        
        # 多样性建议
        if diversity < 0.4:
            recommendations.append(f"📊 多样性{diversity:.1%}过低，内容可能过于单一")
        elif diversity > 0.9:
            recommendations.append(f"⚡ 内容过于分散（多样性{diversity:.1%}），建议聚焦核心主题")
        elif 0.6 <= diversity <= 0.8:
            recommendations.append(f"🌈 信息多样性均衡（{diversity:.1%}）")
        
        # 复杂度建议
        complexity = health.get('complexity', 0.5)
        if complexity < 0.3 and length_ratio > 0.1:
            recommendations.append("💭 内容复杂度较低，可以增加更多实体、数据和结构化信息")
        elif complexity > 0.7:
            recommendations.append(f"🧩 内容复杂度良好（包含丰富的实体和数据）")
        
        # 优先改进项
        scores = {
            '准确性': accuracy,
            '精准性': precision, 
            '多样性': diversity,
            '连贯性': coherence,
            '复杂度': complexity
        }
        
        # 找出最低的两项
        sorted_scores = sorted(scores.items(), key=lambda x: x[1])
        weakest = sorted_scores[0]
        second_weakest = sorted_scores[1]
        
        if weakest[1] < 0.5:
            recommendations.append(f"\n🔥 **优先改进项：{weakest[0]}** (当前仅{weakest[1]:.1%})")
            if second_weakest[1] < 0.6:
                recommendations.append(f"⚡ **次要改进项：{second_weakest[0]}** (当前{second_weakest[1]:.1%})")
        
        return recommendations if recommendations else ["✅ 当前上下文质量良好，保持现有策略"]

# ==================== 使用示例 ====================

def example_usage():
    """使用示例"""
    print("初始化评估器...")
    
    # 使用简单词向量版本（不需要额外依赖）
    evaluator = ContextQualityEvaluator(use_transformer=False, vector_dim=300)
    
    # 模拟数据
    response = "根据文档，该产品的年销售额为1000万元，主要用户群体是25-35岁的年轻人。"
    
    context = """<system>你是一个专业的客服助手</system>
<history>用户：请介绍一下你们的产品
助手：我们的产品是一款智能家居设备</history>
<rag>产品年销售额达到1000万元，目标用户为25-35岁年轻群体，产品特点包括智能控制、节能环保等。</rag>"""
    
    user_query = "你们产品的销售情况和用户群体是怎样的？"
    rag_docs = "产品年销售额达到1000万元，目标用户为25-35岁年轻群体。"
    red_blue_score = 0.8  # 假设的主观评分
    
    print("开始评估...")
    
    # 执行评估
    result = evaluator.evaluate(response, context, user_query, rag_docs, red_blue_score)
    
    # 打印结果
    print("\n评估结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    return result


def test_with_richer_data():
    """使用示例 - 丰富数据测试"""
    print("\n" + "="*60)
    print("测试2：丰富数据测试")
    print("="*60)
    print("初始化评估器...")
    
    # 显式指定向量维度
    evaluator = ContextQualityEvaluator(use_transformer=False, vector_dim=300)
    
    # 更丰富的测试数据
    response = """
    根据我们的数据分析，该智能家居产品在2024年的年销售额达到了1000万元，
    相比去年增长了25%。我们的主要用户群体是25-35岁的年轻职场人士，
    他们注重生活品质，对智能科技产品接受度高。产品的核心优势包括
    智能语音控制、节能环保设计，以及与主流智能生态系统的兼容性。
    用户满意度达到4.8分（满分5分），复购率高达45%。
    """
    
    context = """<s>你是一个专业的智能家居产品客服助手，需要准确回答用户关于产品的各种问题。
    你应该基于事实数据，提供专业、准确、有帮助的回答。</s>
<history>
用户：你们是做什么的？
助手：我们是一家专注于智能家居解决方案的科技公司，致力于让每个家庭享受智能生活。
用户：有哪些产品？
助手：我们主要提供智能灯具、智能插座、智能门锁、智能窗帘等全系列智能家居产品。
用户：产品有什么特点？
助手：我们的产品特点是安装简单、使用方便、节能环保，并且支持多种智能平台互联。
用户：价格贵吗？
助手：我们的产品定价合理，性价比很高，而且经常有优惠活动。
</history>
<rag>
根据2024年最新市场报告和内部数据分析：

1. 销售业绩：
   - 年销售额：1000万元人民币
   - 同比增长：25%
   - 季度环比增长：8%
   - 市场份额：区域市场占比12%

2. 用户画像：
   - 年龄分布：25-35岁占60%，36-45岁占30%
   - 教育程度：本科以上学历占70%
   - 地域分布：一线城市40%，二线城市35%，三线及以下25%
   - 职业特征：IT行业30%，金融行业25%，教育行业20%

3. 产品特点与优势：
   - 智能语音控制：支持小爱同学、天猫精灵、Siri、Alexa等主流语音助手
   - 节能环保：通过智能调节可节省30-40%的电能，获得国家能效认证
   - 易于安装：无需专业人员，普通用户10分钟即可完成安装，提供详细视频教程
   - 生态兼容：支持米家、HomeKit、Google Home、IFTTT等平台
   - 安全可靠：通过国家3C认证，支持本地存储，保护用户隐私

4. 用户反馈：
   - 满意度评分：4.8/5.0
   - 复购率：45%
   - NPS净推荐值：72
   - 主要好评点：易用性、稳定性、售后服务
</rag>"""
    
    user_query = "请详细介绍一下你们产品的销售情况、用户群体特征以及产品优势？我想了解具体的数据和特点。"
    
    rag_docs = """
    2024年产品销售额1000万元，同比增长25%，季度环比增长8%。
    用户主要是25-35岁的年轻职场人士，占比60%，本科学历以上占70%，主要分布在一二线城市。
    产品支持多种语音控制，可节能30-40%，安装简单只需10分钟，兼容各大智能平台。
    用户满意度4.8分，复购率45%，NPS值72。
    """
    
    red_blue_score = 0.85  # 假设的主观评分（更高因为回答更完整）
    
    print("开始评估...")
    
    # 执行评估
    result = evaluator.evaluate(response, context, user_query, rag_docs, red_blue_score)
    
    # 打印结果
    print("\n评估结果：")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    # 对比分析
    print("\n" + "-"*40)
    print("关键指标解读：")
    print("-"*40)
    
    breakdown = result['breakdown']
    health = result['context_health']
    
    print(f"📊 准确性: {breakdown['accuracy']:.1%} - ", end="")
    if breakdown['accuracy'] >= 0.8:
        print("✅ 优秀，回答与文档高度一致")
    elif breakdown['accuracy'] >= 0.6:
        print("⚠️ 良好，基本符合文档内容")
    else:
        print("❌ 需改进，存在偏差")
    
    print(f"🎯 精准性: {breakdown['precision']:.1%} - ", end="")
    if breakdown['precision'] >= 0.7:
        print("✅ 优秀，上下文高度相关")
    elif breakdown['precision'] >= 0.5:
        print("⚠️ 良好，相关性适中")
    else:
        print("❌ 需改进，相关性较低")
    
    print(f"🌈 多样性: {breakdown['diversity']:.1%} - ", end="")
    if 0.6 <= breakdown['diversity'] <= 0.85:
        print("✅ 理想，信息分布均衡")
    elif breakdown['diversity'] < 0.6:
        print("⚠️ 过于单一，需增加信息维度")
    else:
        print("⚠️ 过于分散，需聚焦核心信息")
    
    # print(f"💊 健康度: 连贯性{health['coherence_score']:.1%}, 新鲜度{health['freshness']:.1%}")
    print(f"💊 健康度: 连贯性{health['coherence_score']:.1%}")
    
    return result  # 确保返回结果

# if __name__ == "__main__":
#     # 运行两个测试
#     print("🚀 开始上下文质量评测系统测试")
    
#     try:
#         # 测试1：简单数据
#         result1 = example_usage()
        
#         if result1 is None:
#             print("\n❌ 错误：测试1未返回结果")
#             exit(1)
            
#         # 测试2：丰富数据
#         result2 = test_with_richer_data()
        
#         if result2 is None:
#             print("\n❌ 错误：测试2未返回结果")
#             exit(1)
        
#         # 对比总结
#         print("\n" + "="*60)
#         print("📈 测试对比总结")
#         print("="*60)
        
#         # 显示内容长度
#         print(f"测试1内容长度: {result1.get('content_length', 'N/A')} 字符")
#         print(f"测试2内容长度: {result2.get('content_length', 'N/A')} 字符")
#         print("")
        
#         print(f"简单数据测试 - 最终得分: {result1['final_score']:.3f} ({result1['rating']})")
#         print(f"丰富数据测试 - 最终得分: {result2['final_score']:.3f} ({result2['rating']})")
        
#         score_diff = result2['final_score'] - result1['final_score']
        
#         # 详细对比
#         print("\n" + "-"*40)
#         print("📊 关键指标对比：")
#         print("-"*40)
        
#         metrics = [
#             ('准确性', 'accuracy'),
#             ('精准性', 'precision'),
#             ('多样性', 'diversity')
#         ]
        
#         improvements = 0
#         degradations = 0
#         for name, key in metrics:
#             val1 = result1['breakdown'][key]
#             val2 = result2['breakdown'][key]
#             diff = val2 - val1
            
#             if diff > 0.05:
#                 symbol = "📈"
#                 improvements += 1
#             elif diff < -0.05:
#                 symbol = "📉"
#                 degradations += 1
#             else:
#                 symbol = "→"
                
#             print(f"{name}: {val1:.1%} → {val2:.1%} {symbol} ({diff:+.1%})")
        
#         # 健康度对比
#         print("\n" + "-"*40)
#         print("💊 健康度对比：")
#         print("-"*40)
        
#         health_metrics = [
#             ('连贯性', 'coherence_score'),
#             ('复杂度', 'complexity')
#         ]
        
#         for name, key in health_metrics:
#             val1 = result1['context_health'].get(key, 0)
#             val2 = result2['context_health'].get(key, 0)
#             diff = val2 - val1
            
#             if diff > 0.05:
#                 symbol = "📈"
#             elif diff < -0.05:
#                 symbol = "📉"
#             else:
#                 symbol = "→"
                
#             print(f"{name}: {val1:.1%} → {val2:.1%} {symbol} ({diff:+.1%})")
        
#         # 总体结论
#         print("\n" + "="*60)
#         print("💡 分析结论：")
#         print("="*60)
        
#         if score_diff > 0.1:
#             print(f"✅ **成功**：丰富数据显著提升了评分 (+{score_diff:.1%})")
#             print(f"   - {improvements}个指标改善，{degradations}个指标下降")
#             print("   - 系统能够正确识别和奖励高质量的丰富内容")
#         elif score_diff > 0.05:
#             print(f"📈 **良好**：丰富数据提升了评分 (+{score_diff:.1%})")
#             print(f"   - {improvements}个指标改善")
#             print("   - 区分度存在但可以进一步优化")
#         elif score_diff > -0.03:
#             print(f"⚠️ **警告**：两种数据的评分过于接近（差异仅 {score_diff:+.1%}）")
#             print("   - 需要进一步调整算法参数增加区分度")
#         else:
#             print(f"❌ **问题**：丰富数据的评分反而更低 ({score_diff:.1%})")
#             print("   - 算法存在问题，需要重新检查")
        
#         # 健康度分析
#         complexity_diff = result2['context_health'].get('complexity', 0) - result1['context_health'].get('complexity', 0)
#         # freshness_diff = result2['context_health'].get('freshness', 0) - result1['context_health'].get('freshness', 0)
        
#         print("\n" + "-"*40)
#         print("🔍 关键问题诊断：")
#         print("-"*40)
        
#         if abs(complexity_diff) < 0.1:
#             print("❌ 复杂度区分不足：两个测试的复杂度差异太小")
#         else:
#             print(f"✅ 复杂度区分良好：差异 {complexity_diff:+.1%}")
        
#         # 权重使用情况
#         if 'final_weights_used' in result1:
#             print("\n" + "-"*40)
#             print("⚙️ 权重策略：")
#             print("-"*40)
#             print(f"测试1使用权重: 主观{result1['final_weights_used']['subjective']:.1%} / 客观{result1['final_weights_used']['objective']:.1%}")
#             print(f"测试2使用权重: 主观{result2['final_weights_used']['subjective']:.1%} / 客观{result2['final_weights_used']['objective']:.1%}")
        
#         print("\n✨ 测试完成！")
            
#     except Exception as e:
#         print(f"\n❌ 运行出错: {e}")
#         import traceback
#         traceback.print_exc()