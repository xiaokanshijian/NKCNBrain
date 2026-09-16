import base64
import math
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Tuple

from openai import OpenAI

# D 版面自动迭代识字（Gemini）：固定 cloudapi + gemini-3.1-flash-image-preview
_GEMINI_BASE_URL = 'https://chat.cloudapi.vip/v1/'
_GEMINI_API_KEY = os.environ.get("NKCN_LLM_API_KEY", "")

_QWEN_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
_QWEN_BASE_URL = 'https://dashscope.aliyuncs.com/compatible-mode/v1'

# 上下文截断长度（字符）
_GEMINI_CARD_CONTEXT_MAX = 2000
_GEMINI_DOC_CONTEXT_MAX = 4000
_QWEN_CARD_CONTEXT_MAX = 1000
_QWEN_DOC_CONTEXT_MAX = 2000
_MODEL_RETRY_ATTEMPTS = 3


def _gemini_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('ci_snippet_gemini', 'gemini-3.1-flash-image-preview')


def _qwen_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('ci_snippet_qwen', 'qwen3.6-plus')


def _model_role(model: str) -> str:
    name = str(model or '').lower()
    if 'gemini' in name:
        return 'gemini'
    if 'qwen' in name:
        return 'qwen'
    return str(model or '')


def _model_weight(model: str) -> float:
    role = _model_role(model)
    if role == 'gemini':
        return 1.0
    if role == 'qwen':
        return 0.85
    return 0.5

DEFAULT_VOCAB_DIR = Path(__file__).resolve().parents[2] / '裁切识字测试' / 'release' / 'vocab'


RECOGNITION_PROMPT = """你是一位精通汉字字形学和书法鉴定的专家，也擅长根据上下文进行语义推断。

## 任务
下面的图片是从手写笔记/卡片中裁切出来的一小段文字。图片可能非常模糊、潦草。你需要识别出图中写的是什么文字。

## 图片说明
本次请求仅在消息中附带**一张**图片：由当前页原图按版面框裁切得到的局部 PNG。请完全以该图像素为准辨认手写笔画（并未另行提供其它视角或二值化图）。

## 上下文信息
这些手写文字来自以下主题的笔记/卡片，你可以利用这些上下文来缩小候选范围：

### 卡片主题上下文
{card_context}

### 文档内容概要
{doc_context}

## 推理步骤（请严格按以下顺序进行）

### 第一步：整体观察
- 图中大约有几个字符？（注意区分汉字、英文/数字、标点符号如“·”分隔点、“>”、“+”）
- 字符之间有没有明显的间隔或分隔符？

### 第二步：逐字分析字形
从左到右，对每个字符位置：
- 观察该位置的笔画走势：有哪些横、竖、撇、捺、点、折、钩？
- 是什么结构？（独体/左右/上下/包围）
- 能识别出什么偏旁部首？
- 基于纯字形，列出2-4个候选字

### 第三步：结合上下文推断
- 将各位置的候选字组合，看哪种组合在上下文中最有语义意义
- 上下文中提到的关键概念和术语是重要线索
- 草书/行书中常见的简写和连笔也要考虑

### 第四步：输出最终结果
在最后一行，严格按以下格式输出（不要输出其他格式）：
识别结果：<你识别出的文字>

注意：
- 若图中手写为多行，保留换行，与版面阅读顺序一致
- 如果有“·”等分隔符也要包含在结果中，用“·”表示
- 英文字母和数字直接用对应的 ASCII 字符
- 结果中不要带引号或其他额外标记"""


QWEN_HANDWRITING_PROMPT = """你是手写笔记识字助手。图中为原图某一局部裁剪，内容为手写汉字、数字、符号或简易标注。
请只做忠实抄录：图片可能非常模糊、字迹潦草，你需要识别图中的手写内容，按从左到右、从上到下的阅读顺序输出。
看不清或无法确定的笔画不要猜测填充，可用「□」占位单个模糊字符。

## 上下文（仅供参考，以图像为准）
### 卡片主题上下文
{card_context}

### 文档内容概要
{doc_context}

最后一行必须严格按下面格式输出（仅此一行也可）：
识别结果：<你识别出的文字>

若整图无可靠可读手写内容，最后一行输出：
识别结果：（空）

注意：
- 若图中手写为多行，抄录中保留换行，与版面阅读顺序一致
- 如果有“·”等分隔符也要包含在结果中，用“·”表示
- 英文字母和数字直接用对应的 ASCII 字符
- 结果中不要带引号或其他额外标记"""


def _to_data_url(image_path: str) -> str:
    with open(image_path, 'rb') as handle:
        return 'data:image/png;base64,' + base64.b64encode(handle.read()).decode('utf-8')


def _normalize_result_text(text: Any, *, preserve_newlines: bool = False) -> str:
    value = unicodedata.normalize('NFC', str(text or '').strip())
    value = value.replace('，', ',').replace('、', ',').replace('：', ':')
    value = value.replace('→', '>').replace('＞', '>').replace('->', '>').replace('=>', '>').replace('—>', '>')
    value = value.strip('"\'“”‘’「」【】*`#- ')
    if preserve_newlines:
        value = value.replace('\r\n', '\n').replace('\r', '\n')
        lines = []
        for line in value.split('\n'):
            lines.append(re.sub(r'[ \t\u3000]+', ' ', line).strip())
        value = '\n'.join(lines)
        value = re.sub(r'\n{3,}', '\n\n', value)
    else:
        value = re.sub(r'\s+', ' ', value)
    return value.strip()


def _normalize_vocab_key(text: Any) -> str:
    value = _normalize_result_text(text, preserve_newlines=False).lower()
    return re.sub(r'[^0-9a-z\u4e00-\u9fff·>+]+', '', value)


def _extract_result(raw: str) -> str:
    for prefix in ('识别结果：', '识别结果:', '**识别结果：**', '**识别结果:**'):
        if prefix in raw:
            # 保留「识别结果：」之后的完整抄录（可多行），不把换行压成一行
            result = raw.split(prefix, 1)[-1].strip()
            return _normalize_result_text(result, preserve_newlines=True)

    if len(raw) > 200:
        lines = [line.strip() for line in raw.strip().split('\n') if line.strip()]
        for line in reversed(lines[-10:]):
            clean = _normalize_result_text(line, preserve_newlines=False)
            if 1 <= len(clean) <= 30 and not clean.startswith('###'):
                return clean
    return _normalize_result_text(raw.strip().split('\n')[-1].strip(), preserve_newlines=False)


def _postprocess(result: str) -> str:
    value = _normalize_result_text(result, preserve_newlines=True)
    value = re.sub(r'^[\-\+·，。、：:；;！!？?\.,\s]+|[\-\+·，。、：:；;！!？?\.,\s]+$', '', value)
    return _normalize_result_text(value, preserve_newlines=True)


def _get_client(model: str) -> OpenAI:
    role = _model_role(model)
    if role == 'gemini':
        if not _GEMINI_API_KEY:
            raise ValueError('missing_gemini_api_key')
        return OpenAI(api_key=_GEMINI_API_KEY, base_url=_GEMINI_BASE_URL)
    if role == 'qwen':
        if not _QWEN_API_KEY:
            raise ValueError('missing_qwen_api_key')
        return OpenAI(api_key=_QWEN_API_KEY, base_url=_QWEN_BASE_URL)
    raise ValueError(f'不支持的识别模型: {model}')


def _inject_candidate_vocab(prompt_text: str, candidate_vocab_text: str) -> str:
    if not candidate_vocab_text:
        return prompt_text
    vocab_section = (
        '## 候选词汇表\n'
        '以下是此场景的专业术语词表，按字符数分组。图中文字很可能是其中某个词汇（或多个词汇用分隔符连接的组合）：\n\n'
        f'{candidate_vocab_text}\n\n'
        '**提示：在第一步判断字符数量后，优先在对应长度分组中查找匹配的候选词，再结合字形和上下文确认。**\n\n'
    )
    return prompt_text.replace('## 推理步骤', vocab_section + '## 推理步骤', 1)


def _recognize_single_model(
    model: str,
    image_path: str,
    card_context: str,
    doc_context: str,
    candidate_vocab_text: str,
    qwen_prompt_suffix: str = '',
) -> Dict[str, Any]:
    if _model_role(model) == 'qwen':
        prompt_text = QWEN_HANDWRITING_PROMPT.format(
            card_context=(card_context or '（空）')[:_QWEN_CARD_CONTEXT_MAX],
            doc_context=(doc_context or '（空）')[:_QWEN_DOC_CONTEXT_MAX],
        )
        extra = str(qwen_prompt_suffix or '').strip()
        if extra:
            prompt_text = f'{prompt_text}\n\n{extra}'
    else:
        prompt_text = RECOGNITION_PROMPT.format(
            card_context=(card_context or '（空）')[:_GEMINI_CARD_CONTEXT_MAX],
            doc_context=(doc_context or '（空）')[:_GEMINI_DOC_CONTEXT_MAX],
        )
        prompt_text = _inject_candidate_vocab(prompt_text, candidate_vocab_text)

    last_error = ''
    for attempt in range(1, _MODEL_RETRY_ATTEMPTS + 1):
        try:
            client = _get_client(model)
            kwargs: Dict[str, Any] = {
                'model': model,
                'messages': [{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt_text},
                        {'type': 'image_url', 'image_url': {'url': _to_data_url(image_path)}},
                    ],
                }],
                'max_tokens': 2000,
                'temperature': 0,
            }
            if 'qwen' in model.lower():
                kwargs['extra_body'] = {'enable_thinking': False}
            response = client.chat.completions.create(**kwargs)
            raw = response.choices[0].message.content or ''
            result = _postprocess(_extract_result(str(raw)))
            return {
                'success': True,
                'model': model,
                'alias': _model_role(model),
                'result': result,
                'normalized_result': _normalize_vocab_key(result),
                'reasoning': str(raw),
                'error': '',
                'attempts': attempt,
            }
        except Exception as error:
            last_error = str(error)
            if attempt < _MODEL_RETRY_ATTEMPTS:
                time.sleep(0.8 * attempt)
    return {
        'success': False,
        'model': model,
        'alias': _model_role(model),
        'result': '',
        'normalized_result': '',
        'reasoning': '',
        'error': last_error,
        'attempts': _MODEL_RETRY_ATTEMPTS,
    }


def list_scenes(vocab_dir: Path = DEFAULT_VOCAB_DIR) -> List[str]:
    scenes: List[str] = []
    for file_path in sorted(Path(vocab_dir).glob('候选词典_*.txt')):
        name = file_path.stem.replace('候选词典_', '')
        if name not in ('纯词表', '通用核心'):
            scenes.append(name)
    return scenes


def load_scene_vocab(scene: str, vocab_dir: Path = DEFAULT_VOCAB_DIR) -> List[str]:
    path = Path(vocab_dir) / f'候选词典_{scene}.txt'
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def match_scenes(context: str, vocab_dir: Path = DEFAULT_VOCAB_DIR, top_k: int = 2) -> List[Tuple[str, int]]:
    scores: List[Tuple[str, int]] = []
    for scene in list_scenes(vocab_dir):
        terms = load_scene_vocab(scene, vocab_dir)
        hit = sum(1 for term in terms if len(term) >= 2 and term in context)
        scores.append((scene, hit))
    scores.sort(key=lambda item: -item[1])
    return scores[:top_k]


def build_candidate_vocab_payload(
    card_context: str,
    doc_context: str,
    vocab_dir: Path = DEFAULT_VOCAB_DIR,
    top_k: int = 2,
    include_core: bool = True,
) -> Dict[str, Any]:
    merged_context = '\n'.join([str(card_context or ''), str(doc_context or '')]).strip()
    matched = match_scenes(merged_context, vocab_dir, top_k=top_k)
    scenes = [scene for scene, _score in matched]

    all_terms: set[str] = set()
    if include_core:
        all_terms.update(term for term in load_scene_vocab('通用核心', vocab_dir) if len(term) >= 2)
    for scene in scenes:
        all_terms.update(term for term in load_scene_vocab(scene, vocab_dir) if len(term) >= 2)

    groups: Dict[int, List[str]] = defaultdict(list)
    for term in all_terms:
        groups[len(term)].append(term)
    lines: List[str] = []
    for length in sorted(groups.keys()):
        lines.append(f'【{length}字】{"、".join(sorted(groups[length]))}')

    normalized_terms = {_normalize_vocab_key(term) for term in all_terms if _normalize_vocab_key(term)}
    return {
        'text': '\n'.join(lines),
        'terms': sorted(all_terms, key=lambda item: (len(item), item)),
        'normalized_terms': normalized_terms,
        'matched_scenes': scenes,
    }


def recognize_snippet_with_voting(
    image_path: str,
    card_context: str,
    doc_context: str,
    candidate_vocab_text: str,
    max_workers: int = 2,
) -> Dict[str, Any]:
    predictions: Dict[str, Dict[str, Any]] = {}

    def _call(model_name: str) -> Tuple[str, Dict[str, Any]]:
        return model_name, _recognize_single_model(model_name, image_path, card_context, doc_context, candidate_vocab_text)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_call, model_name): model_name for model_name in (_gemini_model(), _qwen_model())}
        for future in as_completed(futures):
            model_name, result = future.result()
            predictions[_model_role(model_name)] = result

    normalized_predictions = {
        alias: _normalize_vocab_key((payload or {}).get('result') or '')
        for alias, payload in predictions.items()
    }
    voted = _weighted_vote({
        'gemini': (predictions.get('gemini') or {}).get('result') or '',
        'qwen': (predictions.get('qwen') or {}).get('result') or '',
    })

    return {
        'predictions': predictions,
        'normalized_predictions': normalized_predictions,
        'agreed': bool(normalized_predictions.get('gemini')) and normalized_predictions.get('gemini') == normalized_predictions.get('qwen'),
        'voted_result': voted,
    }


def _weighted_vote(predictions: Dict[str, str]) -> str:
    counts = Counter(_normalize_result_text(value) for value in predictions.values() if _normalize_result_text(value))
    if counts:
        best, count = counts.most_common(1)[0]
        if count >= 2:
            return best

    scored: Dict[str, float] = {}
    for model_name, prediction in predictions.items():
        normalized = _normalize_result_text(prediction)
        if not normalized:
            continue
        weight = _model_weight(model_name)
        scored[normalized] = scored.get(normalized, 0.0) + weight
    if scored:
        return max(scored, key=scored.get)
    return ''


def _build_char_ngrams(text: str, n: int = 2) -> List[str]:
    normalized = _normalize_vocab_key(text)
    if len(normalized) < n:
        return [normalized] if normalized else []
    return [normalized[index:index + n] for index in range(len(normalized) - n + 1)]


def _lexical_similarity(left: str, right: str) -> float:
    left_key = _normalize_vocab_key(left)
    right_key = _normalize_vocab_key(right)
    if not left_key or not right_key:
        return 0.0
    left_ngrams = set(_build_char_ngrams(left_key, 2))
    right_ngrams = set(_build_char_ngrams(right_key, 2))
    overlap = len(left_ngrams & right_ngrams)
    containment = overlap / max(len(left_ngrams), 1)
    ratio = SequenceMatcher(None, left_key, right_key).ratio()
    return max(containment, ratio)


def _cosine_similarity(left: List[float], right: List[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(float(a) * float(b) for a, b in zip(left, right))
    left_norm = math.sqrt(sum(float(a) * float(a) for a in left))
    right_norm = math.sqrt(sum(float(b) * float(b) for b in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _embedding_similarity(query_text: str, target_text: str) -> float:
    if not query_text or not target_text:
        return 0.0
    try:
        from llm_langchain.parse_input import embeddings

        if embeddings is None:
            return 0.0
        query_vec = embeddings.embed_query(query_text)
        target_vec = embeddings.embed_query(target_text)
        return _cosine_similarity(query_vec, target_vec)
    except Exception as error:
        print(f'[ci_snippet] embedding 相似度计算失败: {error}')
        return 0.0


def score_text_against_contexts(
    text: str,
    card_context: str,
    doc_context: str,
    card_weight: float = 0.7,
    doc_weight: float = 0.3,
    use_embedding: bool = True,
) -> Dict[str, Any]:
    card_semantic = _embedding_similarity(text, card_context) if use_embedding else 0.0
    doc_semantic = _embedding_similarity(text, doc_context) if use_embedding else 0.0
    card_lexical = _lexical_similarity(text, card_context)
    doc_lexical = _lexical_similarity(text, doc_context)

    card_score = card_semantic if card_semantic > 0 else card_lexical
    doc_score = doc_semantic if doc_semantic > 0 else doc_lexical
    weighted = card_weight * card_score + doc_weight * doc_score
    return {
        'card_semantic': round(card_semantic, 4),
        'doc_semantic': round(doc_semantic, 4),
        'card_lexical': round(card_lexical, 4),
        'doc_lexical': round(doc_lexical, 4),
        'card_score': round(card_score, 4),
        'doc_score': round(doc_score, 4),
        'weighted_score': round(weighted, 4),
    }