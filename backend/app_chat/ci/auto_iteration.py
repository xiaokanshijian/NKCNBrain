import base64
import copy
import importlib.util
import json
import io
import math
import os
import re
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import urlopen

from openai import OpenAI
from PIL import Image, ImageDraw

from app_chat.ci._context import _filter_user_selected_context, _gather_notebook_context
from app_chat.ci._llm import (
    _CI_IMAGE_INLINE_MAX_MB,
    _call_claude4_sonnet_vision_llm,
    _call_qwen35_m_layer_llm,
    _call_qwen35_plus_m_layer_llm,
    _call_qwen_vl_flash_fast,
    _image_path_to_base64_url,
    _normalize_llm_response_text,
    _parse_llm_json,
    _repair_json_locally,
)
from app_chat.ci.snippet_recognizer import (
    _normalize_vocab_key,
    _qwen_model,
    _recognize_single_model,
    build_candidate_vocab_payload,
    recognize_snippet_with_voting,
    score_text_against_contexts,
)
from app_chat.ci._utils import _now_iso, _truncate_text, _update_task
from app_chat.ci.overlay_layer import _load_ci_context, _update_overlay_item
from app_chat.ci.r_layer import (
    SECTION_COMPLETED,
    SECTION_FAILED,
    SECTION_FINALIZING,
    SECTION_PREPARING,
    _GEMINI_REPRO_API_KEY,
    _GEMINI_REPRO_BASE_URL,
    _GEMINI_REPRO_TIMEOUT,
    _extract_repro_base64,
    _extract_repro_base64_from_completion,
    _decode_inline_image_bytes,
    _analysis_units_from_manifest,
    _append_reproduction_rollback_snapshot,
    _iterate_reproduction_image,
    _normalize_edit_region,
    _normalize_reproduction_iter_context,
    _region_to_pixel_box,
    _resample_lanczos,
    _sanitize_reproduction_item_for_response,
    _set_reproduction_iterating,
    _update_single_r_layer_item,
)
from llm_langchain.pdf_ocr_utils import run_remote_ocr_asset


SECTION_RECOGNIZING = '局部识别中'
SECTION_PLANNING = '自动规划中'
SECTION_ITERATING = '局部迭代中'

_AUTO_ITERATION_VERSION = 1
_AUTO_RECOGNITION_SOURCE = 'reproduction_ocr_v1'
_AUTO_RECOGNITION_SOURCE_LLM = 'reproduction_vision_llm_v1'
_AUTO_OCR_TMP_DIRNAME = 'auto_iter_tmp'
_AUTO_MAX_BATCH_SIZE = 9
_AUTO_MAX_BATCH_SIZE_LITE = 18
_AUTO_LOCAL_CANDIDATE_DEFAULT = 'gemini-3.1-flash-image-preview'


def _auto_local_candidate_model() -> str:
    from app_chat.scene_models import get_scene_value
    return get_scene_value('ci_auto_local_image', _AUTO_LOCAL_CANDIDATE_DEFAULT)


def _auto_ci_sm(key, default):
    from app_chat.scene_models import get_scene_value
    return get_scene_value(key, default)
_AUTO_CANDIDATE_DEBUG_DIRNAME = 'auto_iter_candidate_debug'
_AUTO_CANDIDATE_RETRY_ATTEMPTS = 3
_AUTO_REGION_PLAN_TIMEOUT = 45
_AUTO_REGION_OCR_FALLBACK_TIMEOUT = 45
_AUTO_CONTEXT_CHUNK_SIZE = 260
_AUTO_CONTEXT_CHUNK_OVERLAP = 40
_AUTO_MODE_SEMI = 'semi'
_AUTO_MODE_FULL = 'full'
_AUTO_MODE_FULL_LITE = 'full_lite'
_AUTO_SELECTION_SOURCE_CURSOR = 'cursor'
_AUTO_SELECTION_SOURCE_MANUAL = 'manual'
_AUTO_CARD_CONTEXT_WEIGHT = 0.7
_AUTO_DOC_CONTEXT_WEIGHT = 0.3
# 双模型均未命中候选词表时：若任一侧「可见字」超过该长度，不按黑区（词表偏短语、长句难命中），改按灰区并保留加权选文（默认 6 字，可设 NKCN_CI_LONG_SNIPPET_GRAY_MIN_CHARS）
_AUTO_LONG_SNIPPET_GRAY_MIN_CHARS = int(os.environ.get('NKCN_CI_LONG_SNIPPET_GRAY_MIN_CHARS', '6') or '6')
# 与候选词 fuzzy 比对：很高 / 较高（用于白灰黑分档，可调）
_AUTO_VOCAB_SIM_VERY_HIGH = float(os.environ.get('NKCN_CI_VOCAB_SIM_VERY_HIGH', '0.88') or '0.88')
_AUTO_VOCAB_SIM_HIGH = float(os.environ.get('NKCN_CI_VOCAB_SIM_HIGH', '0.72') or '0.72')
# D 版面识字审计（追加写入分析工作区，便于线下核查）
_D_REGION_AUDIT_SUBDIR = 'ci_audit'
_D_REGION_AUDIT_FILENAME = 'd_region_recognition_audit.jsonl'
_D_REGION_CONFIDENCE_FILENAME = 'd_region_confidence_scores.json'
_D_REGION_AUTO_PICK_LOG_FILENAME = 'd_region_auto_iter_used.json'
_JUDGE_GEMINI_BASE = 'https://www.dmxapi.cn/v1'
_JUDGE_GEMINI_KEY = os.environ.get('NKCN_DMT_GEMINI_API_KEY') or os.environ.get("DMX_API_KEY", "")
_JUDGE_QWEN_BASE = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
_JUDGE_QWEN_KEY = os.environ.get('DEEPSEEK_API_KEY_ALI') or os.environ.get('DASHSCOPE_API_KEY') or os.environ.get('NKCN_SNIPPET_QWEN_API_KEY') or os.environ.get("DASHSCOPE_API_KEY", "")
_JUDGE_RETRY_ATTEMPTS = 3


def _vocab_relax_substring_enabled() -> bool:
    """候选词命中：是否允许规范串「包含」某词即算命中（缓解整句无法整段对齐词表）。默认开；设 NKCN_CI_SNIPPET_VOCAB_RELAX_SUBSTRING=0 关闭。"""
    v = (os.environ.get('NKCN_CI_SNIPPET_VOCAB_RELAX_SUBSTRING') or '1').strip().lower()
    return v not in ('0', 'false', 'off', 'no')


def _norm_hits_candidate_vocab(norm: str, terms: set) -> bool:
    """norm 与 candidate_vocab 的 normalized_terms 同属 snippet_recognizer._normalize_vocab_key 空间。"""
    if not norm or not terms:
        return False
    if norm in terms:
        return True
    if not _vocab_relax_substring_enabled():
        return False
    for t in terms:
        ts = str(t).strip()
        if len(ts) >= 2 and ts in norm:
            return True
    return False


def _best_vocab_similarity_to_terms(norm: str, terms: set) -> float:
    """与候选词表每条算相似度，取 max；不含精确/子串命中（命中请走 _norm_hits_candidate_vocab → 1.0）。"""
    if not norm or not terms:
        return 0.0
    norm_s = str(norm).strip()
    if not norm_s:
        return 0.0
    best = 0.0
    for t in terms:
        ts = str(t).strip()
        if not ts:
            continue
        r = SequenceMatcher(None, norm_s, ts).ratio()
        if r > best:
            best = r
    return min(1.0, best)


def _vocab_similarity_score(norm: str, terms: set) -> float:
    """精确/子串命中视为 1.0；否则为与词表最佳 SequenceMatcher 相似度。"""
    if not norm or not terms:
        return 0.0
    if _norm_hits_candidate_vocab(norm, terms):
        return 1.0
    return _best_vocab_similarity_to_terms(norm, terms)


def _strip_dmt_overlay_labels(text: Any) -> str:
    """去掉识别串中的 D/M/T 版面序号（如 D11、M7、T3），避免叠框标签混入正文。"""
    s = _normalize_text(text, preserve_newlines=True)
    if not s:
        return ''
    s = re.sub(r'(?i)[DMT]\s*\d{1,4}', '', s)
    return _normalize_text(s, preserve_newlines=True)


# 仅「轻量全自动」Qwen 初识附加说明（阅读顺序、去标签、印刷/手写标注）
_QWEN_LITE_PROMPT_SUFFIX = """## 轻量流水线附加规则（当前图为单个 D 版面裁切）
1) **阅读顺序**：版面可能有左右分栏、上下分区或表格。如果有请按人类正常阅读顺序抄录（例如先完整读完左侧一栏自上而下，再读右侧一栏自上而下），禁止把左右两栏文字按行交叉拼接。
2) **版面标签**：识别结果正文里**不要输出**图中可能有的版面序号标签，如 D31、M2、T1 等形式（含手写仿标签）；这些是叠框/标注，不是有实际意义的内容。
3) **印刷与手写**：若本版面可读字符总数明显超过约 15 个，且同时存在「表单预置印刷字」与「用户手写内容」，请在「识别结果：」同一行或多行内用括号标注区分，例如「（印刷）…（手写）…」；须忠实抄录字迹，括号仅作类型标注。
4) 最后一行仍以「识别结果：」开头，格式不变。"""

# 整图为粗粒度 DMT（ci_dmt_coarse_layout）时追加：黑/红笔与 TA 点评语境
_QWEN_LITE_PROMPT_COARSE_INK = """
5) 另外若版面中兼有黑色与红色手写笔迹，须在识别结果中区分并标注，例如分段标「（黑笔手写）…」「（红笔手写）…」。若附近有「TA点评」等印刷字样且红笔内容紧邻该区域，红笔一般为助教批语；若无此类版面提示，红笔也可能是教师批语或学生订正，可在括号内简短注明你的推断（如「红笔·疑助教」「红笔·疑教师」「红笔·疑学生订正」）。"""

_QWEN_LITE_SELF_CHECK_TAIL = (
    '复核时请一并校正：（1）多栏版面按栏内自上而下整理 final_text，勿左右行交替打乱语义；'
    '（2）final_text 中不得含 Dxx/Mxx/Txx 类版面标签；（3）保留（印刷）（手写）等区分及细节。'
)


def _qwen_lite_prompt_suffix_full(coarse_layout: bool) -> str:
    base = _QWEN_LITE_PROMPT_SUFFIX.rstrip()
    if coarse_layout:
        return f'{base}\n{_QWEN_LITE_PROMPT_COARSE_INK.strip()}'
    return base


def _qwen_lite_self_check_tail_full(coarse_layout: bool) -> str:
    tail = _QWEN_LITE_SELF_CHECK_TAIL
    if coarse_layout:
        tail += '（4）若版面中同时有黑笔/红笔手写则要作区分；邻近「TA点评」的红笔倾向助教批语，否则也可能是教师或学生订正，黑红双色手写笔迹时请在 final_text 中保留墨色标注与简要角色推断。'
    return tail


# 仅影响「原始草图 → 双模型识字」前一步：整图字迹清晰化后再按原 bbox 裁切。0/false/off 关闭。
_SNIPPET_SKETCH_PREPROCESS_ENV = 'NKCN_CI_SNIPPET_SKETCH_PREPROCESS'
_handwriting_isolate_mod: Any = None  # lazy: module | False（加载失败）


def _sketch_preprocess_for_snippet_enabled() -> bool:
    v = (os.environ.get(_SNIPPET_SKETCH_PREPROCESS_ENV) or '1').strip().lower()
    return v not in ('0', 'false', 'off', 'no')


def _effective_sketch_preprocess(requested: Optional[bool]) -> bool:
    """前端未传时使用 NKCN_CI_SNIPPET_SKETCH_PREPROCESS（默认开）；传入 True/False 则覆盖。"""
    if requested is None:
        return _sketch_preprocess_for_snippet_enabled()
    return bool(requested)


def _resolve_handwriting_isolate_script_path() -> str:
    """优先 app_chat/ci/handwriting_isolate.py；否则回退项目根 scripts/（旧布局）。"""
    ci_dir = os.path.dirname(os.path.abspath(__file__))
    ci_script = os.path.join(ci_dir, 'handwriting_isolate.py')
    if os.path.isfile(ci_script):
        return ci_script
    backend_dir = os.path.dirname(os.path.dirname(ci_dir))
    root_dir = os.path.dirname(backend_dir)
    legacy = os.path.join(root_dir, 'scripts', 'handwriting_isolate.py')
    return legacy if os.path.isfile(legacy) else ''


def _get_handwriting_isolate_module() -> Any:
    global _handwriting_isolate_mod
    if _handwriting_isolate_mod is False:
        return None
    if _handwriting_isolate_mod is not None:
        return _handwriting_isolate_mod
    script_path = _resolve_handwriting_isolate_script_path()
    if not script_path:
        print('[ci_auto_iter] handwriting_isolate.py 未找到（已查 app_chat/ci 与 scripts/），跳过识字前预处理')
        _handwriting_isolate_mod = False
        return None
    spec = importlib.util.spec_from_file_location('handwriting_isolate_ci', script_path)
    if spec is None or spec.loader is None:
        _handwriting_isolate_mod = False
        return None
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        print(f'[ci_auto_iter] 加载 handwriting_isolate 失败: {exc}')
        _handwriting_isolate_mod = False
        return None
    if not hasattr(mod, 'isolate'):
        print('[ci_auto_iter] handwriting_isolate 无 isolate 函数，跳过预处理')
        _handwriting_isolate_mod = False
        return None
    _handwriting_isolate_mod = mod
    return mod


def _cv2_imread_unicode(path: str):
    """Windows 下 cv2.imread 无法打开含中文路径，用 imdecode + 二进制读入规避。"""
    import cv2
    import numpy as np

    try:
        with open(path, 'rb') as handle:
            data = np.frombuffer(handle.read(), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def _cv2_imwrite_unicode_png(path: str, img_bgr) -> bool:
    """同上，写出 PNG 时避免 cv2.imwrite 对中文路径失败。"""
    import cv2
    import numpy as np

    ok, buf = cv2.imencode('.png', img_bgr)
    if not ok or buf is None:
        return False
    try:
        with open(path, 'wb') as handle:
            handle.write(buf.tobytes())
    except OSError:
        return False
    return True


def _write_preprocessed_sketch_fullpage(asset_abs_path: str, tmp_dir: str, *, enabled: bool) -> Optional[str]:
    """整图 isolate 后与输入同尺寸，写出临时 PNG；失败返回 None（调用方回退原图）。enabled=False 时跳过清晰化。"""
    if not enabled:
        return None
    mod = _get_handwriting_isolate_module()
    if mod is None:
        return None
    try:
        import cv2
    except Exception as exc:
        print(f'[ci_auto_iter] 识字预处理需要 cv2: {exc}')
        return None
    img = _cv2_imread_unicode(asset_abs_path)
    if img is None:
        print(f'[ci_auto_iter] 无法读取原图（含中文路径时请用 imdecode 路径）: {asset_abs_path!r}')
        return None
    h0, w0 = img.shape[:2]
    try:
        fg, _fb, _ink = mod.isolate(img, None)
    except Exception as exc:
        print(f'[ci_auto_iter] isolate() 失败，回退原图裁切: {exc}')
        return None
    if fg is None or getattr(fg, 'shape', None) is None or fg.shape[:2] != (h0, w0):
        print('[ci_auto_iter] isolate 输出尺寸与输入不一致，回退原图裁切')
        return None
    rgb = cv2.cvtColor(fg, cv2.COLOR_GRAY2BGR)
    os.makedirs(tmp_dir, exist_ok=True)
    out_path = os.path.join(tmp_dir, f'_sketch_pp_full_{uuid.uuid4().hex}.png')
    if not _cv2_imwrite_unicode_png(out_path, rgb):
        return None
    return out_path


_AUTO_VISION_OCR_SYSTEM_PROMPT = """你是局部图像文字识别器。你只做一件事：识别图片里实际看得见的文字，不要补全、不要改写、不要解释。

请严格输出 JSON：
{
    "recognized_text": "识别到的文字；多行可用\\n；没有可靠文字时必须为空字符串",
    "legibility": "clear | partial | none",
    "is_blank": false,
    "reason": "transcribed_visible_text | partial_visible_text | blank_or_illegible"
}

规则：
1. 只能抄录你真正看见的文字，不能根据上下文脑补缺字。
2. 如果只有很少一部分能确认，可以只输出那一部分，并把 legibility 设为 partial。
3. 如果没有可靠可读文字、只有空白、涂抹、线条或完全看不清，recognized_text 必须为空字符串，legibility=none，is_blank=true。
4. 除 JSON 外不要输出任何其它内容。"""

_AUTO_REGION_PLANNER_SYSTEM_PROMPT = """你是单图自动局部修订规划器。你的任务不是直接改图，而是为一个灰区 D 版面生成一条极简、可执行的 revision_instruction。

你会同时看到：
1. 当前复现图中锁定区域的局部裁切图。
2. 同一位置的原始草图局部裁切图（若提供）。
3. 当前复现图局部 OCR 识别出的文字。
4. 当前页图生文理解摘要与本子上下文。

请遵守：
1. 修改意图必须以原始草图视觉因素和本子上下文为主，以当前复现图局部 OCR 为辅。
2. 只能围绕当前锁定区域输出一条很短的 revision_instruction，不得扩展到其他区域。
3. 若当前 OCR 文字不稳定，只能做保守修订，不能臆造超出上下文边界的新知识。
4. instruction_text 必须明确“只改这个区域，其他不要变”。
5. 输出必须是合法 JSON，不能包含额外说明。

请输出：
{
  "instruction_text": "一句到两句的可执行修订指令，必须包含只改这个区域、其他不要变",
  "target_text_hint": "推断出的目标文字或目标表达，无法稳定推断则写空字符串",
  "reason": "为什么这样改的简短原因",
  "used_context": true
}"""


def _normalize_region_bbox(region: Dict[str, Any]) -> Optional[Dict[str, float]]:
    bbox = region.get('bbox') if isinstance(region, dict) else None
    if not isinstance(bbox, dict):
        return None
    return _normalize_edit_region(bbox)


def _normalize_text(text: Any, *, preserve_newlines: bool = False) -> str:
    value = str(text or '')
    value = re.sub(r'<\|/?ref\|>|<\|/?det\|>', ' ', value)
    value = re.sub(r'<\|[^>]+\|>', ' ', value)
    value = re.sub(r'\[[^\]]*\]\([^\)]*\)', ' ', value)
    value = re.sub(r'[`*_#>-]+', ' ', value)
    if preserve_newlines:
        value = value.replace('\r\n', '\n').replace('\r', '\n')
        lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in value.split('\n')]
        value = '\n'.join(lines)
        value = re.sub(r'\n{3,}', '\n\n', value)
    else:
        value = re.sub(r'\s+', ' ', value)
    return value.strip()


def _normalize_search_text(text: Any) -> str:
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', str(text or '').lower())


def _snippet_visible_char_len(text: Any) -> int:
    """用于长句灰区判定：汉字/字母/数字计字数（忽略空白与标点）。"""
    normalized = _normalize_text(text)
    if not normalized:
        return 0
    return len(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]', normalized))


def _snippet_result_looks_invalid(recognized_text: str) -> Tuple[bool, str]:
    normalized = _normalize_text(recognized_text)
    if not normalized:
        return True, 'snippet_empty_text'

    semantic_chars = len(re.findall(r'[\u4e00-\u9fffA-Za-z0-9]', normalized))
    if semantic_chars == 0:
        return True, 'snippet_no_semantic_chars'

    garbled_chars = len(re.findall(r'[□◆◇■△▽○●\ufffd]', normalized))
    if garbled_chars and (garbled_chars / max(len(normalized), 1)) >= 0.5:
        return True, 'snippet_garbled_text'

    repeated_phrase = re.search(r'([\u4e00-\u9fffA-Za-z0-9]{1,3})(?:\s*\1){3,}', normalized)
    if repeated_phrase:
        return True, 'snippet_repeated_phrase'

    return False, 'snippet_has_signal'


def _matching_char_ratio(left: str, right: str) -> float:
    """按字符顺序匹配（SequenceMatcher matching blocks）计算相同字符占较短串的比例。"""
    l = _normalize_text(left)
    r = _normalize_text(right)
    if not l or not r:
        return 0.0
    sm = SequenceMatcher(None, l, r)
    same_chars = sum(max(0, block.size) for block in sm.get_matching_blocks())
    base = max(1, min(len(l), len(r)))
    return float(same_chars) / float(base)


def _apply_arbitration_similarity_length_rule(
    arbitration_vote: str,
    option1_text: str,
    option2_text: str,
) -> Tuple[str, str]:
    """
    仲裁后附加规则（仅 vote=option1/option2 时生效）：
    - 两个候选必须是子串关系（其一包含另一）
    - 且更长候选比更短候选“仅多 1 或 2 个汉字”
    - 满足时优先更长候选（可覆盖仲裁原判）；否则维持仲裁原判
    """
    vote = str(arbitration_vote or '').strip().lower()
    t1 = str(option1_text or '').strip()
    t2 = str(option2_text or '').strip()
    if vote not in ('option1', 'option2'):
        return '', 'rule_skip_non_option_vote'
    selected = t1 if vote == 'option1' else t2
    if not t1 or not t2:
        return selected, 'rule_keep_missing_candidate'
    n1 = _normalize_text(t1)
    n2 = _normalize_text(t2)
    if not n1 or not n2:
        return selected, 'rule_keep_empty_after_normalize'
    if n1 == n2:
        return selected, 'rule_keep_same_text'

    if len(n1) >= len(n2):
        longer_raw, longer_norm = t1, n1
        shorter_raw, shorter_norm = t2, n2
    else:
        longer_raw, longer_norm = t2, n2
        shorter_raw, shorter_norm = t1, n1

    if shorter_norm not in longer_norm:
        return selected, 'rule_keep_not_substring_relation'

    longer_hz = len(re.findall(r'[\u4e00-\u9fff]', longer_raw))
    shorter_hz = len(re.findall(r'[\u4e00-\u9fff]', shorter_raw))
    diff_hz = longer_hz - shorter_hz
    if diff_hz not in (1, 2):
        return selected, f'rule_keep_hanzi_diff_{diff_hz}'

    if longer_raw == selected:
        return selected, f'rule_keep_selected_is_longer_hanzi_diff_{diff_hz}'
    return longer_raw, f'rule_override_to_longer_hanzi_diff_{diff_hz}'


def _resolve_judge_opinion_text(judge_item: Dict[str, Any], option1_text: str, option2_text: str) -> str:
    vote = str((judge_item or {}).get('vote') or '').strip().lower()
    if vote == 'option1':
        return str(option1_text or '').strip()
    if vote == 'option2':
        return str(option2_text or '').strip()
    if vote == 'neither':
        return str((judge_item or {}).get('corrected_text') or '').strip()
    return ''


def _text_consistent_with_judge_opinions(text: str, judge_results: List[Dict[str, Any]], option1_text: str, option2_text: str, ratio_threshold: float = 0.8) -> bool:
    """与任一裁判给出的最终主张文本相似度达到阈值即视为一致。"""
    target = str(text or '').strip()
    if not target:
        return False
    for item in (judge_results or []):
        judge_text = _resolve_judge_opinion_text(item, option1_text, option2_text)
        if not judge_text:
            continue
        if _matching_char_ratio(target, judge_text) >= float(ratio_threshold):
            return True
    return False


def _extract_text_tokens(text: str) -> List[str]:
    return [token for token in re.findall(r'[\u4e00-\u9fff]{2,}|[a-z0-9]{2,}', str(text or '').lower()) if token]


def _build_char_ngrams(text: str, n: int = 2) -> List[str]:
    normalized = _normalize_search_text(text)
    if len(normalized) < n:
        return [normalized] if normalized else []
    return [normalized[index:index + n] for index in range(len(normalized) - n + 1)]


def _chunk_text(text: str, size: int = _AUTO_CONTEXT_CHUNK_SIZE, overlap: int = _AUTO_CONTEXT_CHUNK_OVERLAP) -> List[str]:
    source = str(text or '').strip()
    if not source:
        return []
    if len(source) <= size:
        return [source]
    chunks: List[str] = []
    step = max(1, size - overlap)
    for start in range(0, len(source), step):
        chunk = source[start:start + size].strip()
        if chunk:
            chunks.append(chunk)
        if start + size >= len(source):
            break
    return chunks


def _build_context_chunks(notebook_ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    chunks: List[Dict[str, str]] = []

    scene_text = ' '.join([
        notebook_ctx.get('scene_name', '') or '',
        notebook_ctx.get('sub_scene_name', '') or '',
        notebook_ctx.get('notebook_description', '') or '',
        notebook_ctx.get('scene_summary', '') or '',
    ]).strip()
    if scene_text:
        chunks.append({
            'source': 'scene',
            'label': '场景上下文',
            'text': scene_text,
            'normalized': _normalize_search_text(scene_text),
        })

    for doc in notebook_ctx.get('doc_summaries', []) or []:
        file_name = str(doc.get('file_name') or '未命名文档').strip()
        summary = str(doc.get('summary') or doc.get('pre_summary') or doc.get('pre_image_summary') or '').strip()
        if not summary:
            continue
        for index, chunk in enumerate(_chunk_text(summary), start=1):
            payload = f'{file_name} {chunk}'.strip()
            chunks.append({
                'source': 'doc',
                'label': f'{file_name}#{index}',
                'text': payload,
                'normalized': _normalize_search_text(payload),
            })

    for card in notebook_ctx.get('card_summaries', []) or []:
        text = ' '.join([
            card.get('title', '') or '',
            card.get('keywords', '') or '',
            card.get('preview', '') or '',
        ]).strip()
        if not text:
            continue
        chunks.append({
            'source': 'card',
            'label': f"卡片{card.get('cid') or ''}".strip(),
            'text': text,
            'normalized': _normalize_search_text(text),
        })
    return chunks


def _extract_search_phrases(text: str) -> List[str]:
    normalized = _normalize_search_text(text)
    phrases: List[str] = []
    if 2 <= len(normalized) <= 48:
        phrases.append(normalized)

    for segment in re.split(r'[\s,，。；;、:：\n]+', str(text or '')):
        normalized_segment = _normalize_search_text(segment)
        if 2 <= len(normalized_segment) <= 24 and normalized_segment not in phrases:
            phrases.append(normalized_segment)

    tokens = _extract_text_tokens(text)
    for width in (2, 3, 4):
        if len(tokens) < width:
            continue
        for index in range(0, len(tokens) - width + 1):
            phrase = ''.join(tokens[index:index + width])
            normalized_phrase = _normalize_search_text(phrase)
            if 2 <= len(normalized_phrase) <= 32 and normalized_phrase not in phrases:
                phrases.append(normalized_phrase)
    return phrases[:16]


def _find_explicit_context_match(recognized_text: str, context_chunks: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    phrases = _extract_search_phrases(recognized_text)
    if not phrases:
        return None
    for phrase in phrases:
        for chunk in context_chunks:
            if phrase and phrase in chunk.get('normalized', ''):
                return {
                    'phrase': phrase,
                    'chunk': chunk,
                    'reason': 'explicit_phrase_match',
                }
    return None


def _compute_lexical_similarity(recognized_text: str, chunk_text: str) -> float:
    query_ngrams = set(_build_char_ngrams(recognized_text, n=2))
    if not query_ngrams:
        return 0.0
    chunk_ngrams = set(_build_char_ngrams(chunk_text, n=2))
    if not chunk_ngrams:
        return 0.0
    overlap = len(query_ngrams & chunk_ngrams)
    containment = overlap / max(len(query_ngrams), 1)
    ratio = SequenceMatcher(None, _normalize_search_text(recognized_text), _normalize_search_text(chunk_text)).ratio()
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


def _compute_embedding_scores(recognized_text: str, context_chunks: List[Dict[str, str]]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    if not context_chunks:
        return scores
    try:
        from llm_langchain.parse_input import embeddings

        if embeddings is None:
            return scores
        query_vec = embeddings.embed_query(recognized_text)
        chunk_vecs = embeddings.embed_documents([chunk.get('text', '') for chunk in context_chunks])
        for chunk, vector in zip(context_chunks, chunk_vecs):
            scores[chunk.get('label', '')] = _cosine_similarity(query_vec, vector)
    except Exception as error:
        print(f'[ci_auto_iter] embedding 相似度计算失败: {error}')
    return scores


def _classify_similarity_result(recognized_text: str, best_lexical: float, best_embedding: float) -> Tuple[str, str]:
    query_len = len(_normalize_search_text(recognized_text))
    if query_len <= 4:
        if best_lexical >= 0.92:
            return 'white', 'short_text_high_lexical_match'
        return 'gray', 'short_text_low_confidence'
    if query_len <= 8:
        if best_lexical >= 0.75 or (best_embedding >= 0.82 and best_lexical >= 0.22):
            return 'white', 'mid_short_text_context_match'
        return 'gray', 'mid_short_text_context_weak'
    if best_embedding >= 0.78 or (best_embedding >= 0.72 and best_lexical >= 0.35) or best_lexical >= 0.68:
        return 'white', 'semantic_context_match'
    return 'gray', 'semantic_context_weak'


def _crop_image_by_region(image_path: str, region_bbox: Dict[str, float]) -> Tuple[Image.Image, str]:
    with Image.open(image_path) as image:
        image = image.convert('RGBA')
        img_w, img_h = image.size
        left, top, right, bottom, _crop_w, _crop_h = _region_to_pixel_box(img_w, img_h, region_bbox)
        cropped = image.crop((left, top, right, bottom)).convert('RGBA')
    buffer = io.BytesIO()
    cropped.save(buffer, format='PNG')
    return cropped, base64.b64encode(buffer.getvalue()).decode('utf-8')


def _run_local_region_ocr(tmp_dir: str, source_image: Image.Image, region_id: str) -> Dict[str, Any]:
    os.makedirs(tmp_dir, exist_ok=True)
    safe_region_id = re.sub(r'[^\w\-]', '_', region_id or 'region')
    crop_path = os.path.join(tmp_dir, f'{safe_region_id}.png')
    source_image.convert('RGB').save(crop_path, format='PNG')
    try:
        result = run_remote_ocr_asset(file_path=crop_path, output_dir=tmp_dir, input_type='image', model_id=None)
    except Exception as error:
        print(f'[ci_auto_iter] 局部OCR失败({region_id}): {error}')
        result = {'success': False, 'raw_text': '', 'markdown': {}}
    finally:
        try:
            if os.path.isfile(crop_path):
                os.remove(crop_path)
        except Exception:
            pass
    return result or {}


def _extract_ocr_text(ocr_result: Dict[str, Any]) -> str:
    markdown_text = ''
    markdown_payload = ocr_result.get('markdown') if isinstance(ocr_result, dict) else None
    if isinstance(markdown_payload, dict):
        markdown_text = markdown_payload.get('markdown_content', '') or ''
    raw_text = ocr_result.get('raw_text', '') if isinstance(ocr_result, dict) else ''
    text = markdown_text or raw_text or ''
    return _normalize_text(text)


def _extract_ocr_error(ocr_result: Dict[str, Any]) -> str:
    if not isinstance(ocr_result, dict):
        return ''
    parts: List[str] = []
    errors = ocr_result.get('errors')
    if isinstance(errors, list):
        parts.extend(str(item).strip() for item in errors if str(item or '').strip())
    elif errors:
        parts.append(str(errors).strip())
    for key in ('error', 'msg', 'detail'):
        value = str(ocr_result.get(key) or '').strip()
        if value:
            parts.append(value)
    if ocr_result.get('success') is False and not parts:
        parts.append('ocr_backend_error')
    normalized = re.sub(r'\s+', ' ', ' ; '.join(parts)).strip(' ;')
    return _truncate_text(normalized, 240)


def _parse_llm_region_ocr_result(raw: Any) -> Optional[Dict[str, Any]]:
    parsed = _parse_llm_json(raw, {})
    if not parsed:
        repaired = _repair_json_locally(_normalize_llm_response_text(raw))
        if repaired:
            parsed = _parse_llm_json(repaired, {})
    if isinstance(parsed, dict) and parsed:
        recognized_text = _normalize_text(
            parsed.get('recognized_text') or parsed.get('text') or parsed.get('ocr_text') or '',
            preserve_newlines=True,
        )
        legibility = str(parsed.get('legibility') or '').strip().lower()
        if legibility not in ('clear', 'partial', 'none'):
            legibility = 'none' if not recognized_text else 'partial'
        is_blank = parsed.get('is_blank')
        if isinstance(is_blank, str):
            is_blank = is_blank.strip().lower() in ('1', 'true', 'yes', 'y', 'on')
        if not isinstance(is_blank, bool):
            is_blank = bool((not recognized_text) and legibility == 'none')
        reason = _truncate_text(parsed.get('reason') or '', 120)
        return {
            'recognized_text': recognized_text,
            'legibility': legibility,
            'is_blank': bool(is_blank),
            'reason': reason,
        }

    raw_text = _normalize_llm_response_text(raw).strip()
    plain_text = _normalize_text(raw_text, preserve_newlines=True)
    if plain_text in ('无', '无文字', '看不清', '看不清楚', '无法识别', '空白', '没有文字'):
        return {
            'recognized_text': '',
            'legibility': 'none',
            'is_blank': True,
            'reason': 'blank_or_illegible',
        }
    if plain_text and len(plain_text) <= 120 and not re.search(r'\{|\}|recognized_text|legibility|is_blank|reason', raw_text, re.IGNORECASE):
        return {
            'recognized_text': plain_text,
            'legibility': 'partial',
            'is_blank': False,
            'reason': 'plain_text_fallback',
        }
    return None


def _run_llm_region_ocr_fallback(crop_b64: str, region_id: str) -> Dict[str, Any]:
    user_text = (
        f'当前区域 region_id={region_id or "region"}。请识别这张局部裁切图中实际可见的文字。'
        '如果没有可靠可读文字，不要猜测，按约定返回空字符串和 none。'
    )
    user_content = [
        {'type': 'text', 'text': user_text},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{crop_b64}'}},
    ]
    candidates = [
        ('claude-4-sonnet', lambda: _call_claude4_sonnet_vision_llm(
            _AUTO_VISION_OCR_SYSTEM_PROMPT,
            user_content,
            _AUTO_REGION_OCR_FALLBACK_TIMEOUT,
            2,
        )),
        ('qwen3.5-flash', lambda: _call_qwen35_m_layer_llm(
            _AUTO_VISION_OCR_SYSTEM_PROMPT,
            user_content,
            _AUTO_REGION_OCR_FALLBACK_TIMEOUT,
            1,
        )),
        ('qwen3-vl-flash', lambda: _call_qwen_vl_flash_fast(
            _AUTO_VISION_OCR_SYSTEM_PROMPT,
            user_content,
            _AUTO_REGION_OCR_FALLBACK_TIMEOUT,
        )),
    ]
    errors: List[str] = []
    for model_name, caller in candidates:
        raw = caller()
        if not raw:
            errors.append(f'{model_name}:empty_response')
            continue
        parsed = _parse_llm_region_ocr_result(raw)
        if parsed:
            return {
                'success': True,
                'model_name': model_name,
                **parsed,
            }
        errors.append(
            f'{model_name}:unusable_output={_truncate_text(_normalize_llm_response_text(raw), 120)}'
        )
    return {
        'success': False,
        'error': _truncate_text(' ; '.join(errors) or 'vision_llm_fallback_failed', 240),
    }


def _build_auto_recognition_payload(
    recognized_text: str,
    recognition: str,
    reason: str,
    matched_chunk: Optional[Dict[str, str]] = None,
    lexical_score: float = 0.0,
    embedding_score: float = 0.0,
    recognition_error: str = '',
    ocr_failed: bool = False,
    recognition_source: str = _AUTO_RECOGNITION_SOURCE,
    llm_fallback_used: bool = False,
    llm_fallback_model: str = '',
    ocr_backend_error: str = '',
    extra_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        'recognition': recognition,
        'recognition_reason': reason,
        'recognized_text': _truncate_text(recognized_text, 240),
        'recognition_error': _truncate_text(recognition_error, 240),
        'recognition_source': recognition_source,
        'recognition_updated_at': _now_iso(),
        'ocr_failed': bool(ocr_failed),
        'llm_fallback_used': bool(llm_fallback_used),
        'llm_fallback_model': llm_fallback_model or '',
        'ocr_backend_error': _truncate_text(ocr_backend_error, 240),
        'context_excerpt': _truncate_text((matched_chunk or {}).get('text') or '', 240),
        'context_label': (matched_chunk or {}).get('label') or '',
        'context_source': (matched_chunk or {}).get('source') or '',
        'recognition_scores': {
            'lexical': round(float(lexical_score or 0.0), 4),
            'semantic': round(float(embedding_score or 0.0), 4),
        },
    }
    if isinstance(extra_payload, dict) and extra_payload:
        payload.update(copy.deepcopy(extra_payload))
    return payload


def _recognition_extra_with_voting(
    base_extra: Dict[str, Any],
    voting: Optional[Dict[str, Any]],
    attach_snippet_voting: bool,
) -> Dict[str, Any]:
    out = copy.deepcopy(base_extra)
    if attach_snippet_voting and voting is not None:
        out['snippet_raw_voting'] = copy.deepcopy(voting)
    return out


def _compact_payload_for_audit(payload: Dict[str, Any]) -> Dict[str, Any]:
    """压缩 snippet_raw_voting 内 reasoning 体积，便于 jsonl 单行可读。"""
    compact = copy.deepcopy(payload)
    srv = compact.get('snippet_raw_voting')
    if isinstance(srv, dict):
        preds = srv.get('predictions')
        if isinstance(preds, dict):
            for _alias, block in preds.items():
                if isinstance(block, dict) and block.get('reasoning'):
                    block['reasoning'] = _truncate_text(str(block.get('reasoning') or ''), 1500)
    return compact


def append_d_region_recognition_audit(
    paths: Dict[str, Any],
    *,
    username: str,
    analysis_id: str,
    unit_id: str,
    region_id: str,
    source: str,
    recognition_payload: Dict[str, Any],
) -> str:
    """将一次识字结果追加写入 `{analysis_root}/ci_audit/d_region_recognition_audit.jsonl`，返回绝对路径。"""
    root = paths.get('root') or ''
    if not root:
        return ''
    audit_dir = os.path.join(str(root), _D_REGION_AUDIT_SUBDIR)
    os.makedirs(audit_dir, exist_ok=True)
    audit_path = os.path.join(audit_dir, _D_REGION_AUDIT_FILENAME)
    record = {
        'ts': _now_iso(),
        'username': username,
        'analysis_id': analysis_id,
        'unit_id': unit_id,
        'region_id': region_id,
        'source': source,
        'payload': _compact_payload_for_audit(recognition_payload),
    }
    try:
        with open(audit_path, 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception as exc:
        print(f'[ci_auto_iter] 写入 D 版面识字审计失败: {exc}')
        return audit_path if os.path.isfile(audit_path) else ''
    return audit_path


def recognize_ci_d_region(
    username: str,
    analysis_id: str,
    unit_id: str,
    region_id: str,
    sketch_preprocess: Optional[bool] = None,
    use_recognition_context: bool = True,
    preview_only: bool = False,
) -> Dict[str, Any]:
    """对单个 D 版面调用 Gemini+Qwen 切片识字，写入审计日志，返回完整 payload（含 snippet_raw_voting）。
    sketch_preprocess：是否先做整图 handwriting_isolate；None 表示沿用环境变量默认。
    """
    paths, manifest, _r, _r_item, overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
    rid = str(region_id or '').strip()
    region = None
    for item in overlay_item.get('regions') or []:
        if isinstance(item, dict) and str(item.get('region_id') or '').strip() == rid:
            region = item
            break
    if not region:
        return {'success': False, 'msg': f'未找到 region_id={rid}'}
    if str(region.get('level') or '').lower() != 'd':
        return {'success': False, 'msg': '仅支持 level=D 的版面'}

    notebook_ctx = _build_auto_iteration_notebook_context(username, manifest)
    recognition_context = _build_auto_iteration_recognition_context(
        notebook_ctx,
        use_recognition_context=bool(use_recognition_context),
    )
    asset_abs_path = _resolve_unit_asset_abs_path(paths, manifest, unit_id)
    tmp_dir = os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME, 'd_region_probe')
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        if preview_only:
            crop_preview_b64 = _build_d_region_crop_preview_b64(
                region=region,
                asset_abs_path=asset_abs_path,
                tmp_dir=tmp_dir,
                sketch_preprocess=sketch_preprocess,
            )
            return {
                'success': True,
                'preview_only': True,
                'model_input_crop_b64': crop_preview_b64,
                'analysis_id': analysis_id,
                'unit_id': unit_id,
                'region_id': rid,
            }
        payload = _classify_region_recognition(
            region,
            asset_abs_path,
            tmp_dir,
            recognition_context,
            attach_snippet_voting=True,
            sketch_preprocess=sketch_preprocess,
        )
        payload = _attach_disagreement_adjudication_for_probe(
            payload=payload,
            region=region,
            asset_abs_path=asset_abs_path,
            tmp_dir=tmp_dir,
            recognition_context=recognition_context,
            sketch_preprocess=sketch_preprocess,
        )
        audit_path = append_d_region_recognition_audit(
            paths,
            username=username,
            analysis_id=analysis_id,
            unit_id=unit_id,
            region_id=rid,
            source='manual_probe',
            recognition_payload=payload,
        )
        return {
            'success': True,
            'recognition_payload': payload,
            'audit_log_path': audit_path,
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'region_id': rid,
        }
    finally:
        try:
            shutil.rmtree(os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME), ignore_errors=True)
        except Exception:
            pass


def _parse_confidence_percent(text: str) -> float:
    raw = str(text or '').strip()
    if not raw:
        raise ValueError('empty_confidence_output')
    nums = re.findall(r'(\d+(?:\.\d+)?)', raw)
    if not nums:
        raise ValueError('missing_confidence_number')
    value = float(nums[0])
    # 模型可能输出 0~1 或 0~100，这里统一为百分比。
    if value <= 1.0:
        value = value * 100.0
    # 特例：无字迹可判（空白、仅圈线箭头等）允许输出 0 / 0%。
    if value <= 0.0:
        return 0.0
    # 按需求微调：限制到 5~100，且按 5% 步长量化（0 仅用于“无字迹”特例）。
    value = max(5.0, min(100.0, value))
    value = round(value / 5.0) * 5.0
    value = max(5.0, min(100.0, value))
    return round(value, 2)


def _top_repeated_values(values: List[float], limit: int = 3) -> List[int]:
    if not values:
        return []
    counter: Dict[int, int] = {}
    for value in values:
        if float(value) <= 0.0:
            # 0 代表“无字迹”，不参与常规分值去重提示。
            continue
        key = int(round(float(value) / 5.0) * 5)
        key = max(5, min(100, key))
        counter[key] = int(counter.get(key) or 0) + 1
    ranked = sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    return [int(item[0]) for item in ranked[:max(1, int(limit or 1))]]


def _parse_yes_no_output(text: str) -> str:
    raw = str(text or '').strip()
    has_yes = '是' in raw
    has_no = '否' in raw
    if has_yes and not has_no:
        return '是'
    if has_no and not has_yes:
        return '否'
    return ''


def _qwen_check_candidate_garbled_needed_retry(input_b64: str, resized_b64: str) -> str:
    """
    返回“是/否”：
    - 是：两图几乎没区别 + 图中含“像汉字又不是汉字”的乱码字迹，应触发改用原草图局部重生
    - 否：其余情况
    若输出不规范，按要求再调用一次；仍不规范则回退“否”。
    """
    if not _JUDGE_GEMINI_KEY:
        return '否'
    prompt = (
        "你将看到两张图：\n"
        "1) input：本次局部迭代生图的输入图\n"
        "2) resized：模型输出并缩放后的局部图\n\n"
        "请只判断：\n"
        "A. 两图是否几乎没有区别；\n"
        "B. 图中是否存在“像汉字但实际接近乱码/伪汉字”的字迹（常见于生图模型胡写）。\n\n"
        "若 A 和 B 同时满足，输出“是”；否则输出“否”。\n"
        "只允许输出一个汉字：是 或 否。不要输出任何其他内容。"
    )
    client = OpenAI(
        api_key=_JUDGE_GEMINI_KEY,
        base_url=_JUDGE_GEMINI_BASE.rstrip('/') + '/',
        timeout=90,
    )
    for _ in range(2):
        try:
            rsp = client.chat.completions.create(
                model=_auto_ci_sm('ci_auto_gemini_pro', 'gemini-3.1-pro-preview'),
                messages=[{
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': prompt},
                        {'type': 'image_url', 'image_url': {'url': _to_data_url_from_b64_png(input_b64)}},
                        {'type': 'image_url', 'image_url': {'url': _to_data_url_from_b64_png(resized_b64)}},
                    ],
                }],
                temperature=0,
                max_tokens=5000,
            )
            out = str(rsp.choices[0].message.content or '').strip()
            parsed = _parse_yes_no_output(out)
            if parsed in ('是', '否'):
                return parsed
        except Exception:
            pass
    return '否'


def _call_qwen_confidence_once(
    *,
    crop_b64: str,
    full_b64: str,
    d1_crop_b64: str,
    region_id: str,
    is_d1: bool,
    reference_d1_confidence: Optional[float] = None,
    avoid_values: Optional[List[int]] = None,
) -> Dict[str, Any]:
    avoid_text = ''
    values = [int(v) for v in (avoid_values or []) if isinstance(v, (int, float))]
    if values:
        avoid_text = '；本轮已出现较多的置信度数值（请尽量避免重复，除非图像里字迹识别难易程度确实完全相同）：' + '、'.join(f'{int(v)}%' for v in values[:3])
    d1_ref_text = ''
    if reference_d1_confidence is not None:
        d1_ref_text = f'；D1 区域字迹的识别置信度参照值约为 {int(round(float(reference_d1_confidence)))}%'
    prompt_other = (
        "你将看到三张图：\n"
        "1) 当前D区域局部裁切图；\n"
        "2) 原草图整图；\n"
        "3) D1区域局部裁切图（作为置信度参照样本）。\n\n"
        "任务：仅输出“字迹识别置信度”（此处手写字能被**完全正确**认出的概率，单位百分比）。\n"
        "要求：\n"
        "- 不要输出识别文本内容；\n"
        "- 仅输出一个数字，不要任何解释；\n"
        "- 若该框内无可识别手写字迹（例如空白、仅一个圈/一根线/一个箭头且无疑似文字的笔迹），直接输出 0 或 0%；\n"
        "- 其余有字迹场景，数值范围限定在 5~100；\n"
        "- 仅可使用 5 的步长（5,10,15,...,100）；\n"
        "- 以D1区域字迹的可辨识程度作为参照，同时结合当前区域自身清晰完整度、字迹可辨识程度判断，若难易不同则置信度尽量与D1不同，在数值差上体现区别的程度；\n"
        f"- 在体现真实的字迹辨识难易顺序优先的前提下，输出值尽量与高频重复值不同{d1_ref_text}{avoid_text}；\n"
        "- 印刷体或非常标准清晰的手写字应视为 100。"
    )
    prompt_d1 = (
        "你将看到两张图：\n"
        "1) 当前D区域局部裁切图；\n"
        "2) 原草图整图。\n\n"
        "任务：仅输出“字迹识别置信度”（此处手写字能被**完全正确**认出的概率，单位百分比）。\n"
        "要求：\n"
        "- 不要输出识别文本内容；\n"
        "- 仅输出一个数字，不要任何解释；\n"
        "- 若该框内无可识别手写字迹（例如空白、仅一个圈/一根线/一个箭头且无疑似文字的笔迹），直接输出 0 或 0%；\n"
        "- 其余有字迹场景，数值范围限定在 5~100；\n"
        "- 仅可使用 5 的步长（5,10,15,...,100）；\n"
        "- 要体现出真实的此处字迹辨识难易程度；\n"
        "- 印刷体或非常标准清晰的手写字应视为 100。"
    )
    content = [
        {'type': 'text', 'text': prompt_d1 if is_d1 else prompt_other},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(crop_b64)}},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(full_b64)}},
    ]
    if not is_d1:
        content.append({'type': 'image_url', 'image_url': {'url': _to_data_url_from_b64_png(d1_crop_b64)}})
    client = OpenAI(
        api_key=_JUDGE_QWEN_KEY,
        base_url=_JUDGE_QWEN_BASE.rstrip('/') + '/',
        timeout=120,
    )
    rsp = client.chat.completions.create(
        model=_auto_ci_sm('ci_auto_qwen', 'qwen3.6-plus'),
        messages=[{'role': 'user', 'content': content}],
        temperature=0.0,
        max_tokens=120,
        extra_body={'enable_thinking': False},
    )
    out = str(rsp.choices[0].message.content or '').strip()
    confidence = _parse_confidence_percent(out)
    return {
        'region_id': region_id,
        'confidence_percent': confidence,
        'raw_output': _truncate_text(out, 500),
        'success': True,
    }


def _call_qwen_confidence_with_retry(
    *,
    crop_b64: str,
    full_b64: str,
    d1_crop_b64: str,
    region_id: str,
    is_d1: bool,
    reference_d1_confidence: Optional[float] = None,
    avoid_values: Optional[List[int]] = None,
) -> Dict[str, Any]:
    last_error = ''
    for attempt in range(1, 3):
        try:
            result = _call_qwen_confidence_once(
                crop_b64=crop_b64,
                full_b64=full_b64,
                d1_crop_b64=d1_crop_b64,
                region_id=region_id,
                is_d1=is_d1,
                reference_d1_confidence=reference_d1_confidence,
                avoid_values=avoid_values,
            )
            result['attempts'] = attempt
            return result
        except Exception as exc:
            last_error = str(exc)
            if attempt < 3:
                time.sleep(0.8 * attempt)
    return {
        'region_id': region_id,
        'confidence_percent': 0.01,
        'raw_output': '',
        'success': False,
        'attempts': 2,
        'error': _truncate_text(last_error, 500),
    }


def _parse_gemini_confidence_batch_output(text: str, region_ids: List[str]) -> Dict[str, float]:
    raw = str(text or '')
    result: Dict[str, float] = {}
    for rid in region_ids:
        rid = str(rid or '').strip()
        if not rid:
            continue
        pattern = rf'(?im)\b{re.escape(rid)}\b[^\d\n\r]{{0,24}}(\d{{1,3}})\s*%?'
        matched = re.search(pattern, raw)
        if not matched:
            continue
        try:
            result[rid] = _parse_confidence_percent(matched.group(1))
        except Exception:
            continue
    return result


def _call_gemini_confidence_batch_once(
    *,
    batch_items: List[Dict[str, Any]],
    full_b64: str,
    d1_crop_b64: str,
) -> Dict[str, Any]:
    region_ids = [str((item or {}).get('region_id') or '').strip() for item in batch_items]
    region_ids = [rid for rid in region_ids if rid]
    if not region_ids:
        raise ValueError('empty_batch_region_ids')
    prompt = (
        "你将看到多张图：\n"
        "1) 原草图整图；\n"
        "2) D1区域局部图（作为识别难度标尺）；\n"
        "3) 接下来是一组待评估D区局部图（每张图前有对应region_id标记）。\n\n"
        "任务：为每个region_id输出“字迹识别置信度”（该区域手写字被完全正确识别的概率）。\n"
        "要求：\n"
        "- 只输出结果列表，不要解释；\n"
        "- 每行一个结果，格式严格：<region_id>: <数字>% ；\n"
        "- 若某个框内无可识别手写字迹（例如空白、仅一个圈/一根线/一个箭头且无疑似文字的笔迹），该项直接输出 0 或 0%；\n"
        "- 其余有字迹场景，数值范围 5~100；\n"
        "- 仅允许 5 的步长（5,10,15,...,100）；\n"
        "- 请尽量体现不同区域真实辨识难度差异，避免大量相同分值；\n"
        "- 印刷体或非常标准清晰的手写字应接近 100。\n\n"
        f"本批必须覆盖以下全部 region_id（缺一不可）：{', '.join(region_ids)}"
    )
    content: List[Dict[str, Any]] = [
        {'type': 'text', 'text': prompt},
        {'type': 'text', 'text': '【原草图整图】'},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(full_b64)}},
        {'type': 'text', 'text': '【D1区域局部图（难度标尺）】'},
        {'type': 'image_url', 'image_url': {'url': _to_data_url_from_b64_png(d1_crop_b64)}},
    ]
    for item in batch_items:
        rid = str((item or {}).get('region_id') or '').strip()
        crop_b64 = str((item or {}).get('crop_b64') or '').strip()
        if not rid or not crop_b64:
            continue
        content.append({'type': 'text', 'text': f'【待评估区域】{rid}'})
        content.append({'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(crop_b64)}})

    client = OpenAI(
        api_key=_JUDGE_GEMINI_KEY,
        base_url=_JUDGE_GEMINI_BASE.rstrip('/') + '/',
        timeout=180,
    )
    rsp = client.chat.completions.create(
        model=_auto_ci_sm('ci_auto_gemini_pro', 'gemini-3.1-pro-preview'),
        messages=[{'role': 'user', 'content': content}],
        temperature=0.0,
        max_tokens=5000,
    )
    out = str(rsp.choices[0].message.content or '').strip()
    parsed = _parse_gemini_confidence_batch_output(out, region_ids)
    missing = [rid for rid in region_ids if rid not in parsed]
    return {
        'raw_output': _truncate_text(out, 1200),
        'parsed': parsed,
        'missing_regions': missing,
    }


def _call_gemini_confidence_batch_with_retry(
    *,
    batch_items: List[Dict[str, Any]],
    full_b64: str,
    d1_crop_b64: str,
) -> Dict[str, Any]:
    last_error = ''
    best_parsed: Dict[str, float] = {}
    raw_outputs: List[str] = []
    best_attempts = 0
    expected_ids = [str((item or {}).get('region_id') or '').strip() for item in batch_items]
    expected_ids = [rid for rid in expected_ids if rid]
    remaining_items: List[Dict[str, Any]] = list(batch_items or [])
    for attempt in range(1, 4):
        if not remaining_items:
            break
        try:
            out = _call_gemini_confidence_batch_once(
                batch_items=remaining_items,
                full_b64=full_b64,
                d1_crop_b64=d1_crop_b64,
            )
            parsed = out.get('parsed') if isinstance(out, dict) else {}
            raw_output = str(out.get('raw_output') or '').strip() if isinstance(out, dict) else ''
            if isinstance(parsed, dict):
                for rid, value in parsed.items():
                    rid = str(rid or '').strip()
                    if not rid:
                        continue
                    try:
                        best_parsed[rid] = float(value)
                    except Exception:
                        continue
                if parsed:
                    if raw_output:
                        raw_outputs.append(raw_output)
                    best_attempts = attempt
            missing = [rid for rid in expected_ids if rid and rid not in best_parsed]
            # 真正续跑：后续只重试缺失项，不再重复已完成项。
            if missing:
                remaining_items = [
                    item for item in remaining_items
                    if str((item or {}).get('region_id') or '').strip() in set(missing)
                ]
            if not missing:
                return {
                    'raw_output': '\n---\n'.join([chunk for chunk in raw_outputs if chunk]).strip(),
                    'parsed': best_parsed,
                    'missing_regions': [],
                    'attempts': attempt,
                    'success': True,
                }
            last_error = f'gemini_batch_missing_regions={",".join(missing)}; raw={_truncate_text(raw_output, 500)}'
        except Exception as exc:
            last_error = str(exc)
            if attempt < 2:
                time.sleep(0.8 * attempt)
    missing = [rid for rid in expected_ids if rid not in best_parsed]
    if best_parsed:
        return {
            'raw_output': '\n---\n'.join([chunk for chunk in raw_outputs if chunk]).strip(),
            'parsed': best_parsed,
            'missing_regions': missing,
            'attempts': best_attempts or 3,
            'success': True,
            'error': _truncate_text(last_error, 500) if last_error else '',
        }
    return {
        'raw_output': '\n---\n'.join([chunk for chunk in raw_outputs if chunk]).strip(),
        'parsed': best_parsed,
        'missing_regions': missing,
        'attempts': 3,
        'success': False,
        'error': _truncate_text(last_error, 500),
    }


def evaluate_ci_d_regions_confidence(
    username: str,
    analysis_id: str,
    unit_id: str,
    confidence_model: str = 'qwen',
) -> Dict[str, Any]:
    paths, manifest, _r, _r_item, overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
    d_regions = [item for item in (overlay_item.get('regions') or []) if str((item or {}).get('level') or '').lower() == 'd']
    d_regions.sort(
        key=lambda item: (
            int(item.get('rank') or 999),
            float((item.get('bbox') or {}).get('y') or 0.0),
            float((item.get('bbox') or {}).get('x') or 0.0),
            str(item.get('region_id') or ''),
        )
    )
    if not d_regions:
        return {'success': False, 'msg': '当前覆盖层没有可用 D 版面'}
    asset_abs_path = _resolve_unit_asset_abs_path(paths, manifest, unit_id)
    if not asset_abs_path or not os.path.isfile(asset_abs_path):
        return {'success': False, 'msg': '未找到原草图文件'}
    full_b64 = base64.b64encode(Path(asset_abs_path).read_bytes()).decode('utf-8')
    tmp_dir = os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME, 'd_confidence')
    os.makedirs(tmp_dir, exist_ok=True)
    model_name = str(confidence_model or 'qwen').strip().lower()
    use_gemini = model_name in ('gemini', 'gemini-3.1-pro-preview', 'gemini3.1pro', 'gemini_pro')
    resolved_model_name = _auto_ci_sm('ci_auto_gemini_pro', 'gemini-3.1-pro-preview') if use_gemini else _auto_ci_sm('ci_auto_qwen', 'qwen3.6-plus')
    try:
        first = d_regions[0]
        d1_crop_b64 = _build_d_region_crop_preview_b64(
            region=first,
            asset_abs_path=asset_abs_path,
            tmp_dir=tmp_dir,
            sketch_preprocess=False,
        )
        results_map: Dict[str, Dict[str, Any]] = {}
        if not use_gemini:
            d1_res = _call_qwen_confidence_with_retry(
                crop_b64=d1_crop_b64,
                full_b64=full_b64,
                d1_crop_b64=d1_crop_b64,
                region_id=str(first.get('region_id') or 'D1'),
                is_d1=True,
                reference_d1_confidence=None,
                avoid_values=[],
            )
            results_map[str(first.get('region_id') or 'D1')] = d1_res
            d1_conf = d1_res.get('confidence_percent')
            d1_conf_value = float(d1_conf) if d1_conf is not None else 5.0
            completed_values: List[float] = [d1_conf_value]
            values_lock = threading.Lock()
            rest = d_regions[1:]

            def _worker(region: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
                rid = str(region.get('region_id') or '').strip()
                crop_b64 = _build_d_region_crop_preview_b64(
                    region=region,
                    asset_abs_path=asset_abs_path,
                    tmp_dir=tmp_dir,
                    sketch_preprocess=False,
                )
                with values_lock:
                    avoid_values = _top_repeated_values(completed_values, limit=3)
                out = _call_qwen_confidence_with_retry(
                    crop_b64=crop_b64,
                    full_b64=full_b64,
                    d1_crop_b64=d1_crop_b64,
                    region_id=rid,
                    is_d1=False,
                    reference_d1_confidence=d1_conf_value,
                    avoid_values=avoid_values,
                )
                with values_lock:
                    out_conf = out.get('confidence_percent')
                    completed_values.append(float(out_conf) if out_conf is not None else 5.0)
                return rid, out

            if rest:
                with ThreadPoolExecutor(max_workers=2) as executor:
                    futures = [executor.submit(_worker, region) for region in rest]
                    for fut in futures:
                        rid, out = fut.result()
                        results_map[rid] = out
        else:
            region_items: List[Dict[str, Any]] = []
            for region in d_regions:
                rid = str(region.get('region_id') or '').strip()
                crop_b64 = _build_d_region_crop_preview_b64(
                    region=region,
                    asset_abs_path=asset_abs_path,
                    tmp_dir=tmp_dir,
                    sketch_preprocess=False,
                )
                region_items.append({'region_id': rid, 'crop_b64': crop_b64})
            batch_size = 10
            batches: List[List[Dict[str, Any]]] = [
                region_items[idx: idx + batch_size] for idx in range(0, len(region_items), batch_size)
            ]

            def _batch_worker(batch_items: List[Dict[str, Any]]) -> Tuple[List[str], Dict[str, Any]]:
                batch_ids = [str((item or {}).get('region_id') or '').strip() for item in batch_items]
                out = _call_gemini_confidence_batch_with_retry(
                    batch_items=batch_items,
                    full_b64=full_b64,
                    d1_crop_b64=d1_crop_b64,
                )
                return batch_ids, out

            with ThreadPoolExecutor(max_workers=min(3, max(1, len(batches)))) as executor:
                futures = [executor.submit(_batch_worker, batch_items) for batch_items in batches]
                for fut in futures:
                    batch_ids, out = fut.result()
                    parsed_map = out.get('parsed') if isinstance(out, dict) else {}
                    batch_raw = str(out.get('raw_output') or '').strip() if isinstance(out, dict) else ''
                    batch_attempts = int(out.get('attempts') or 0) if isinstance(out, dict) else 0
                    batch_success = bool(out.get('success')) if isinstance(out, dict) else False
                    batch_error = str(out.get('error') or '').strip() if isinstance(out, dict) else ''
                    missing_regions = out.get('missing_regions') if isinstance(out, dict) else []
                    missing_regions = [str(r or '').strip() for r in (missing_regions or []) if str(r or '').strip()]
                    for rid in batch_ids:
                        rid = str(rid or '').strip()
                        if not rid:
                            continue
                        if isinstance(parsed_map, dict) and rid in parsed_map:
                            results_map[rid] = {
                                'region_id': rid,
                                'confidence_percent': float(parsed_map.get(rid)) if parsed_map.get(rid) is not None else 5.0,
                                'raw_output': batch_raw,
                                'success': True,
                                'attempts': batch_attempts,
                            }
                        else:
                            miss_text = ''
                            if missing_regions:
                                miss_text = f'gemini_batch_missing_regions={",".join(missing_regions)}'
                            results_map[rid] = {
                                'region_id': rid,
                                'confidence_percent': 0.01,
                                'raw_output': batch_raw,
                                'success': False,
                                'attempts': batch_attempts,
                                'error': batch_error or miss_text or ('gemini_batch_partial' if batch_success else 'gemini_batch_failed'),
                            }

        ordered_results: List[Dict[str, Any]] = []
        for idx, region in enumerate(d_regions):
            rid = str(region.get('region_id') or '').strip()
            item = results_map.get(rid) or {
                'region_id': rid,
                'confidence_percent': 0.01,
                'success': False,
                'attempts': 0,
                'error': 'missing_result',
                'raw_output': '',
            }
            ordered_results.append({
                'order': idx + 1,
                'region_id': rid,
                'title': str(region.get('title') or rid).strip(),
                'confidence_percent': float(item.get('confidence_percent')) if item.get('confidence_percent') is not None else 0.01,
                'success': bool(item.get('success')),
                'attempts': int(item.get('attempts') or 0),
                'error': str(item.get('error') or '').strip(),
                'raw_output': str(item.get('raw_output') or '').strip(),
            })

        output = {
            'ts': _now_iso(),
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'model': resolved_model_name,
            'reference_region_id': str(first.get('region_id') or '').strip(),
            'results': ordered_results,
        }
        audit_dir = os.path.join(str(paths.get('root') or ''), _D_REGION_AUDIT_SUBDIR)
        os.makedirs(audit_dir, exist_ok=True)
        output_path = os.path.join(audit_dir, _D_REGION_CONFIDENCE_FILENAME)
        with open(output_path, 'w', encoding='utf-8') as handle:
            json.dump(output, handle, ensure_ascii=False, indent=2)
        return {
            'success': True,
            'msg': 'success',
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'result_file_path': output_path,
            'model': resolved_model_name,
            'reference_region_id': output.get('reference_region_id') or '',
            'results': ordered_results,
        }
    finally:
        try:
            shutil.rmtree(os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME), ignore_errors=True)
        except Exception:
            pass


def load_ci_d_regions_confidence_result(
    username: str,
    analysis_id: str,
    unit_id: str,
) -> Dict[str, Any]:
    paths, _manifest, _r, _r_item, _overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
    audit_path = os.path.join(str(paths.get('root') or ''), _D_REGION_AUDIT_SUBDIR, _D_REGION_CONFIDENCE_FILENAME)
    fallback_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), _D_REGION_CONFIDENCE_FILENAME)
    target_path = audit_path if os.path.isfile(audit_path) else (fallback_path if os.path.isfile(fallback_path) else '')
    if not target_path:
        return {'success': False, 'msg': 'not_found', 'result_file_path': ''}
    try:
        with open(target_path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
    except Exception as exc:
        return {'success': False, 'msg': f'read_failed: {exc}', 'result_file_path': target_path}
    results = payload.get('results') if isinstance(payload, dict) else []
    return {
        'success': True,
        'msg': 'success',
        'analysis_id': analysis_id,
        'unit_id': unit_id,
        'result_file_path': target_path,
        'model': str((payload or {}).get('model') or '').strip(),
        'reference_region_id': str((payload or {}).get('reference_region_id') or '').strip(),
        'results': results if isinstance(results, list) else [],
    }


def _load_auto_pick_log(paths: Dict[str, Any]) -> Dict[str, Any]:
    root = str(paths.get('root') or '')
    log_path = os.path.join(root, _D_REGION_AUDIT_SUBDIR, _D_REGION_AUTO_PICK_LOG_FILENAME)
    if not os.path.isfile(log_path):
        return {'path': log_path, 'records': []}
    try:
        with open(log_path, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
        records = payload.get('records') if isinstance(payload, dict) else []
        return {'path': log_path, 'records': records if isinstance(records, list) else []}
    except Exception:
        return {'path': log_path, 'records': []}


def _save_auto_pick_log(paths: Dict[str, Any], records: List[Dict[str, Any]]) -> str:
    root = str(paths.get('root') or '')
    audit_dir = os.path.join(root, _D_REGION_AUDIT_SUBDIR)
    os.makedirs(audit_dir, exist_ok=True)
    log_path = os.path.join(audit_dir, _D_REGION_AUTO_PICK_LOG_FILENAME)
    with open(log_path, 'w', encoding='utf-8') as handle:
        json.dump({'records': records}, handle, ensure_ascii=False, indent=2)
    return log_path


def get_ci_auto_iter_low_confidence_candidates(
    username: str,
    analysis_id: str,
    unit_id: str,
    limit: int = 9,
) -> Dict[str, Any]:
    paths, manifest, _r, _r_item, overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
    conf = load_ci_d_regions_confidence_result(username, analysis_id, unit_id)
    if not conf.get('success'):
        return {'success': False, 'msg': 'missing_confidence_result'}
    conf_items = conf.get('results') if isinstance(conf.get('results'), list) else []
    by_region: Dict[str, Dict[str, Any]] = {}
    for item in conf_items:
        rid = str((item or {}).get('region_id') or '').strip()
        if rid:
            by_region[rid] = item
    d_regions = [
        region for region in (overlay_item.get('regions') or [])
        if str((region or {}).get('level') or '').lower() == 'd'
    ]
    d_regions.sort(key=lambda item: (
        int(item.get('rank') or 999),
        float((item.get('bbox') or {}).get('y') or 0.0),
        float((item.get('bbox') or {}).get('x') or 0.0),
        str(item.get('region_id') or ''),
    ))
    log = _load_auto_pick_log(paths)
    used_success = set()
    for rec in (log.get('records') or []):
        if not isinstance(rec, dict):
            continue
        if str(rec.get('analysis_id') or '').strip() != str(analysis_id or '').strip():
            continue
        if str(rec.get('unit_id') or '').strip() != str(unit_id or '').strip():
            continue
        if rec.get('status') != 'success':
            continue
        rid = str(rec.get('region_id') or '').strip()
        if rid:
            used_success.add(rid)
    candidates: List[Dict[str, Any]] = []
    for region in d_regions:
        rid = str(region.get('region_id') or '').strip()
        if not rid or rid in used_success:
            continue
        item = by_region.get(rid)
        if not item:
            continue
        conf_value = float(item.get('confidence_percent')) if item.get('confidence_percent') is not None else 100.0
        # 0 代表框内无实际字迹，自动挑选时应排除。
        if conf_value <= 0.0:
            continue
        candidates.append({
            'region_id': rid,
            'title': str(region.get('title') or rid).strip(),
            'confidence_percent': conf_value,
        })
    candidates.sort(
        key=lambda item: (
            float(item.get('confidence_percent')) if item.get('confidence_percent') is not None else 100.0,
            str(item.get('region_id') or ''),
        )
    )
    pick_limit = max(1, min(int(limit or 9), 99))
    selected = candidates[:pick_limit]
    return {
        'success': True,
        'selected_region_ids': [str(item.get('region_id') or '').strip() for item in selected],
        'selected_items': selected,
        'excluded_used_success_region_ids': sorted(list(used_success)),
        'confidence_file_path': conf.get('result_file_path') or '',
        'log_file_path': log.get('path') or '',
    }


def mark_ci_auto_iter_regions_used(
    username: str,
    analysis_id: str,
    unit_id: str,
    region_ids: List[str],
    status: str = 'success',
    note: str = '',
) -> Dict[str, Any]:
    paths, _manifest, _r, _r_item, _overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
    cleaned_ids = [str(rid or '').strip() for rid in (region_ids or []) if str(rid or '').strip()]
    if not cleaned_ids:
        return {'success': False, 'msg': 'empty_region_ids'}
    log = _load_auto_pick_log(paths)
    records = list(log.get('records') or [])
    ts = _now_iso()
    for rid in cleaned_ids:
        records.append({
            'ts': ts,
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'region_id': rid,
            'status': 'success' if str(status or '').strip().lower() == 'success' else 'failed',
            'note': str(note or '').strip(),
        })
    log_path = _save_auto_pick_log(paths, records)
    return {'success': True, 'log_file_path': log_path, 'count': len(cleaned_ids)}


def _classify_region_recognition(
    region: Dict[str, Any],
    asset_abs_path: str,
    tmp_dir: str,
    recognition_context: Dict[str, Any],
    attach_snippet_voting: bool = False,
    sketch_preprocess: Optional[bool] = None,
) -> Dict[str, Any]:
    normalized_bbox = _normalize_region_bbox(region)
    if not normalized_bbox:
        return _build_auto_recognition_payload('', 'black', 'invalid_region_bbox')

    region_id = str(region.get('region_id') or 'region')
    if not asset_abs_path or not os.path.isfile(asset_abs_path):
        return _build_auto_recognition_payload(
            '',
            '',
            'missing_source_sketch',
            recognition_error='missing_source_sketch',
            ocr_failed=True,
        )

    use_pre = _effective_sketch_preprocess(sketch_preprocess)
    preprocess_full_path = _write_preprocessed_sketch_fullpage(asset_abs_path, tmp_dir, enabled=use_pre)
    crop_source_path = preprocess_full_path or asset_abs_path
    os.makedirs(tmp_dir, exist_ok=True)
    safe_region_id = re.sub(r'[^\w\-]', '_', region_id or 'region')
    crop_path = os.path.join(tmp_dir, f'{safe_region_id}_sketch.png')
    voting = {}
    try:
        cropped_image, _crop_b64 = _crop_image_by_region(crop_source_path, normalized_bbox)
        cropped_image.convert('RGB').save(crop_path, format='PNG')

        voting = recognize_snippet_with_voting(
            crop_path,
            recognition_context.get('card_context') or '',
            recognition_context.get('doc_context') or '',
            recognition_context.get('candidate_vocab_text') or '',
        )
    finally:
        for p in (crop_path, preprocess_full_path):
            if p and os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    predictions = voting.get('predictions') if isinstance(voting.get('predictions'), dict) else {}
    gemini_payload = predictions.get('gemini') if isinstance(predictions.get('gemini'), dict) else {}
    qwen_payload = predictions.get('qwen') if isinstance(predictions.get('qwen'), dict) else {}
    gemini_text = _strip_dmt_overlay_labels(gemini_payload.get('result') or '')
    qwen_text = _strip_dmt_overlay_labels(qwen_payload.get('result') or '')
    gemini_norm = str(_normalize_vocab_key(gemini_text) or '').strip()
    qwen_norm = str(_normalize_vocab_key(qwen_text) or '').strip()

    model_predictions = {
        'gemini': {
            'text': gemini_text,
            'normalized_text': gemini_norm,
            'success': bool(gemini_payload.get('success')),
            'error': _truncate_text(gemini_payload.get('error') or '', 240),
        },
        'qwen': {
            'text': qwen_text,
            'normalized_text': qwen_norm,
            'success': bool(qwen_payload.get('success')),
            'error': _truncate_text(qwen_payload.get('error') or '', 240),
        },
    }

    if not gemini_payload.get('success') or not qwen_payload.get('success'):
        errors = [
            f'gemini:{gemini_payload.get("error")}' if gemini_payload.get('error') else '',
            f'qwen:{qwen_payload.get("error")}' if qwen_payload.get('error') else '',
        ]
        return _build_auto_recognition_payload(
            '',
            '',
            'model_recognition_failed',
            recognition_error=' ; '.join(item for item in errors if item),
            ocr_failed=True,
            recognition_source='sketch_snippet_recognizer_v1',
            extra_payload=_recognition_extra_with_voting(
                {
                'model_predictions': model_predictions,
                'candidate_vocab_scenes': recognition_context.get('candidate_vocab_scenes') or [],
                'selection_required': False,
                'suggested_target_text': '',
                'selected_model': '',
            },
                voting,
                attach_snippet_voting,
            ),
        )

    candidate_terms = recognition_context.get('candidate_vocab_terms') or set()
    g_sim = _vocab_similarity_score(gemini_norm, candidate_terms)
    q_sim = _vocab_similarity_score(qwen_norm, candidate_terms)
    gemini_hit = bool(gemini_norm and _norm_hits_candidate_vocab(gemini_norm, candidate_terms))
    qwen_hit = bool(qwen_norm and _norm_hits_candidate_vocab(qwen_norm, candidate_terms))
    model_predictions['gemini']['hit_candidate_vocab'] = gemini_hit
    model_predictions['qwen']['hit_candidate_vocab'] = qwen_hit
    model_predictions['gemini']['vocab_similarity'] = round(g_sim, 4)
    model_predictions['qwen']['vocab_similarity'] = round(q_sim, 4)

    vv_thr = _AUTO_VOCAB_SIM_VERY_HIGH
    h_thr = _AUTO_VOCAB_SIM_HIGH

    selected_model = ''
    recognized_text = ''
    recognition = ''
    reason = ''
    weighted_scores = {}

    def _weighted_pick_gray() -> None:
        nonlocal selected_model, recognized_text, weighted_scores
        gemini_scores = score_text_against_contexts(
            gemini_text,
            recognition_context.get('card_context') or '',
            recognition_context.get('doc_context') or '',
            card_weight=_AUTO_CARD_CONTEXT_WEIGHT,
            doc_weight=_AUTO_DOC_CONTEXT_WEIGHT,
            use_embedding=False,
        )
        qwen_scores = score_text_against_contexts(
            qwen_text,
            recognition_context.get('card_context') or '',
            recognition_context.get('doc_context') or '',
            card_weight=_AUTO_CARD_CONTEXT_WEIGHT,
            doc_weight=_AUTO_DOC_CONTEXT_WEIGHT,
            use_embedding=False,
        )
        weighted_scores = {'gemini': gemini_scores, 'qwen': qwen_scores}
        # 灰区加权：手写场景优先生信 Qwen（与分歧时优先策略一致）
        if qwen_scores.get('weighted_score', 0.0) >= gemini_scores.get('weighted_score', 0.0):
            selected_model = 'qwen'
            recognized_text = qwen_text
        else:
            selected_model = 'gemini'
            recognized_text = gemini_text

    if gemini_norm and gemini_norm == qwen_norm:
        selected_model = 'agreement'
        recognized_text = gemini_text or qwen_text
        recognition = 'white'
        reason = 'models_agree_white_relaxed'
    elif (g_sim >= vv_thr and q_sim < vv_thr) or (q_sim >= vv_thr and g_sim < vv_thr):
        recognition = 'white'
        reason = 'one_very_high_vocab_sim_other_not_white'
        if g_sim >= vv_thr:
            selected_model = 'gemini'
            recognized_text = gemini_text
        else:
            selected_model = 'qwen'
            recognized_text = qwen_text
    elif g_sim >= h_thr and q_sim >= h_thr:
        _weighted_pick_gray()
        recognition = 'gray'
        reason = 'both_high_vocab_sim_disagree_weighted_gray'
    elif g_sim >= h_thr or q_sim >= h_thr:
        recognition = 'gray'
        reason = 'one_high_vocab_sim_other_not_gray'
        if g_sim >= h_thr and q_sim < h_thr:
            selected_model = 'gemini'
            recognized_text = gemini_text
        elif q_sim >= h_thr and g_sim < h_thr:
            selected_model = 'qwen'
            recognized_text = qwen_text
        else:
            selected_model = 'gemini' if g_sim >= q_sim else 'qwen'
            recognized_text = gemini_text if g_sim >= q_sim else qwen_text
    else:
        long_chars = max(_snippet_visible_char_len(gemini_text), _snippet_visible_char_len(qwen_text))
        if long_chars > _AUTO_LONG_SNIPPET_GRAY_MIN_CHARS:
            _weighted_pick_gray()
            recognition = 'gray'
            reason = 'long_snippet_default_gray_vocab_unreliable'
        else:
            recognition = 'black'
            reason = 'both_below_high_vocab_short_or_fallback_black'
            recognized_text = ''

    # 规范化串不一致时优先采纳 Qwen（手写更强）；Qwen 为空则回退 Gemini。黑区不覆盖（仍无可靠正文）。
    disagree = bool(gemini_norm != qwen_norm)
    if recognition != 'black':
        if disagree and str(qwen_text).strip():
            recognized_text = qwen_text
            selected_model = 'qwen'
        elif disagree and not str(qwen_text).strip() and str(gemini_text).strip():
            recognized_text = gemini_text
            selected_model = 'gemini'

    # 白区、长段灰区不应再被 invalid 启发式打成黑区
    skip_invalid_heuristic_black = (
        recognition == 'white'
        or reason == 'long_snippet_default_gray_vocab_unreliable'
        or (
            recognition == 'gray'
            and _snippet_visible_char_len(recognized_text) > _AUTO_LONG_SNIPPET_GRAY_MIN_CHARS
        )
    )

    # Snippet targets are often valid 2-4 char phrases, so only force black on clearly non-textual outputs.
    invalid_snippet, invalid_reason = _snippet_result_looks_invalid(recognized_text)
    if recognition != 'black' and recognized_text and invalid_snippet and not skip_invalid_heuristic_black:
        return _build_auto_recognition_payload(
            recognized_text,
            'black',
            invalid_reason,
            recognition_source='sketch_snippet_recognizer_v1',
            extra_payload=_recognition_extra_with_voting(
                {
                'model_predictions': model_predictions,
                'candidate_vocab_scenes': recognition_context.get('candidate_vocab_scenes') or [],
                'selection_required': False,
                'suggested_target_text': '',
                'selected_model': selected_model,
                'context_weighted_scores': weighted_scores,
            },
                voting,
                attach_snippet_voting,
            ),
        )
    return _build_auto_recognition_payload(
        recognized_text,
        recognition,
        reason,
        recognition_source='sketch_snippet_recognizer_v1',
        extra_payload=_recognition_extra_with_voting(
            {
            'model_predictions': model_predictions,
            'candidate_vocab_scenes': recognition_context.get('candidate_vocab_scenes') or [],
            'selection_required': recognition == 'gray',
            'suggested_target_text': recognized_text,
            'selected_model': selected_model,
            'context_weighted_scores': weighted_scores,
            'source_asset_kind': 'original_sketch',
        },
            voting,
            attach_snippet_voting,
        ),
    )


def _build_d_region_crop_preview_b64(
    region: Dict[str, Any],
    asset_abs_path: str,
    tmp_dir: str,
    sketch_preprocess: Optional[bool] = None,
) -> str:
    normalized_bbox = _normalize_region_bbox(region)
    if not normalized_bbox:
        raise ValueError('invalid_region_bbox')
    if not asset_abs_path or not os.path.isfile(asset_abs_path):
        raise ValueError('missing_source_sketch')

    use_pre = _effective_sketch_preprocess(sketch_preprocess)
    preprocess_full_path = _write_preprocessed_sketch_fullpage(asset_abs_path, tmp_dir, enabled=use_pre)
    crop_source_path = preprocess_full_path or asset_abs_path
    try:
        _cropped_image, crop_b64 = _crop_image_by_region(crop_source_path, normalized_bbox)
        return crop_b64
    finally:
        if preprocess_full_path and os.path.isfile(preprocess_full_path):
            try:
                os.remove(preprocess_full_path)
            except Exception:
                pass


def _build_d_region_marked_full_preview_b64(
    region: Dict[str, Any],
    asset_abs_path: str,
) -> str:
    """构造“原草图 + 当前D红框”全图输入（红框细线、轻微外扩）。"""
    normalized_bbox = _normalize_region_bbox(region)
    if not normalized_bbox:
        raise ValueError('invalid_region_bbox')
    if not asset_abs_path or not os.path.isfile(asset_abs_path):
        raise ValueError('missing_source_sketch')
    with Image.open(asset_abs_path).convert('RGB') as image:
        img_w, img_h = image.size
        left, top, right, bottom, box_w, box_h = _region_to_pixel_box(img_w, img_h, normalized_bbox)
        expand_px = max(1, int(round(min(box_w, box_h) * 0.03)))
        x1 = max(0, left - expand_px)
        y1 = max(0, top - expand_px)
        x2 = min(max(0, img_w - 1), right - 1 + expand_px)
        y2 = min(max(0, img_h - 1), bottom - 1 + expand_px)
        line_w = max(1, int(round(min(img_w, img_h) * 0.0012)))
        line_w = min(line_w, 2)
        draw = ImageDraw.Draw(image)
        draw.rectangle([(x1, y1), (x2, y2)], outline=(229, 57, 53), width=line_w)
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('utf-8')


def _to_data_url_from_b64_png(image_b64: str) -> str:
    return f'data:image/png;base64,{str(image_b64 or "").strip()}'


def _inline_data_url_from_png_b64_maybe_compress(b64_png: str) -> str:
    """PNG 纯 base64。超过 DashScope/Gemini 单条 data-uri 上限时落盘并走 encode_image 压到约 3MB 以内（与 _image_path_to_base64_url 一致）。"""
    s = str(b64_png or '').strip()
    if not s:
        return 'data:image/png;base64,'
    try:
        raw = base64.b64decode(s)
    except Exception:
        return _to_data_url_from_b64_png(b64_png)
    if len(raw) <= int(_CI_IMAGE_INLINE_MAX_MB * 1024 * 1024):
        return _to_data_url_from_b64_png(s)
    path = ''
    try:
        fd, path = tempfile.mkstemp(suffix='.png')
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
        out = _image_path_to_base64_url(path)
        return out if out else _to_data_url_from_b64_png(s)
    except Exception:
        return _to_data_url_from_b64_png(s)
    finally:
        if path:
            try:
                os.remove(path)
            except Exception:
                pass


def _parse_judge_vote(raw_text: str) -> Dict[str, str]:
    text = str(raw_text or '').strip()
    vote = ''
    corrected = ''
    reason = _truncate_text(text, 600)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            vote = str(parsed.get('vote') or '').strip().lower()
            corrected = str(parsed.get('corrected_text') or '').strip()
            reason = _truncate_text(str(parsed.get('reason') or reason), 600)
    except Exception:
        match_vote = re.search(r'"?vote"?\s*[:：]\s*"?(option1|option2|neither|1|2)"?', text, re.IGNORECASE)
        if match_vote:
            vote = match_vote.group(1).lower()
        match_corrected = re.search(r'"?corrected_text"?\s*[:：]\s*"([^"]*)"', text, re.IGNORECASE)
        if match_corrected:
            corrected = match_corrected.group(1).strip()
    if vote in ('1', 'option1'):
        vote = 'option1'
    elif vote in ('2', 'option2'):
        vote = 'option2'
    elif vote != 'neither':
        vote = ''
    return {
        'vote': vote,
        'corrected_text': corrected,
        'reason': reason,
        'raw': _truncate_text(text, 1200),
        'parsed_ok': 'true' if vote in ('option1', 'option2', 'neither') else 'false',
    }


def _judge_disagreement_once(
    judge_name: str,
    model_id: str,
    base_url: str,
    api_key: str,
    crop_b64: str,
    full_b64: str,
    option1: str,
    option2: str,
    card_context: str,
    doc_context: str,
) -> Dict[str, Any]:
    if not api_key:
        return {'judge': judge_name, 'success': False, 'error': 'missing_api_key', 'vote': '', 'corrected_text': '', 'reason': ''}
    prompt = (
        "你是手写识字裁判。请在不知道两个候选分别来自哪个识别模型的前提下盲选。\n"
        "你将看到：局部裁切图（主依据）、完整原图（辅助定位）、上下文补充（仅参考）、两个候选答案。\n"
        "任务：\n"
        "1) 若候选1更可信，vote=option1。\n"
        "2) 若候选2更可信，vote=option2。\n"
        "3) 若都不对，vote=neither，并给 corrected_text（你认为更合理的识别结果）。\n"
        "判定原则补充：若候选答案在词或句层面明显不通顺，或为非公众熟知人物人名，则此候选答案大概率有误；"
        "只输出一行 JSON，不要其它文字：\n"
        '{"vote":"option1|option2|neither","corrected_text":"可空","reason":"一句话理由"}\n\n'
        f'候选1：{option1}\n'
        f'候选2：{option2}\n\n'
        "上下文补充（仅参考，以图像为准）：\n"
        f'卡片上下文：{_truncate_text(card_context, 500)}\n'
        f'文档上下文：{_truncate_text(doc_context, 1000)}\n'
    )
    content = [
        {'type': 'text', 'text': '【D版面裁切图】（主依据）'},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(crop_b64)}},
        {'type': 'text', 'text': '【完整原图】（辅助定位）'},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(full_b64)}},
        {'type': 'text', 'text': prompt},
    ]
    last_error = ''
    for attempt in range(1, _JUDGE_RETRY_ATTEMPTS + 1):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url.rstrip('/') + '/', timeout=180)
            kwargs: Dict[str, Any] = {
                'model': model_id,
                'messages': [{'role': 'user', 'content': content}],
                'temperature': 0,
                'max_tokens': 5000 if str(model_id or '').strip() == 'gemini-3.1-pro-preview' else 800,
            }
            if 'qwen' in model_id.lower():
                kwargs['extra_body'] = {'enable_thinking': False}
            rsp = client.chat.completions.create(**kwargs)
            out = str(rsp.choices[0].message.content or '').strip()
            parsed = _parse_judge_vote(out)
            if str(parsed.get('parsed_ok') or '').strip().lower() != 'true':
                raise RuntimeError(f'judge_invalid_output_no_vote: {parsed.get("raw") or _truncate_text(out, 240)}')
            return {
                'judge': judge_name,
                'success': True,
                'error': '',
                'attempts': attempt,
                **parsed,
            }
        except Exception as e:
            last_error = _truncate_text(str(e), 240)
            if attempt < _JUDGE_RETRY_ATTEMPTS:
                time.sleep(0.8 * attempt)
    return {
        'judge': judge_name,
        'success': False,
        'error': last_error,
        'vote': '',
        'corrected_text': '',
        'reason': '',
        'raw': '',
        'attempts': _JUDGE_RETRY_ATTEMPTS,
    }


def _parse_self_check_result(raw_text: str, fallback_text: str) -> Dict[str, str]:
    text = str(raw_text or '').strip()
    confirmed = None
    final_text = ''
    reason = _truncate_text(text, 600)
    parsed_obj: Dict[str, Any] = {}
    parsed_confirmed_explicit = False
    parsed_final_text_explicit = False
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed_obj = parsed
    except Exception:
        # 兼容模型输出“前后有说明 + 中间一段 JSON”的情况
        match = re.search(r'\{[\s\S]*\}', text)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    parsed_obj = parsed
            except Exception:
                parsed_obj = {}
    if parsed_obj:
        c = parsed_obj.get('confirmed')
        if isinstance(c, bool):
            confirmed = c
            parsed_confirmed_explicit = True
        elif isinstance(c, str):
            ctext = c.strip().lower()
            if ctext in ('true', '1', 'yes', 'y', 'on'):
                confirmed = True
                parsed_confirmed_explicit = True
            elif ctext in ('false', '0', 'no', 'n', 'off'):
                confirmed = False
                parsed_confirmed_explicit = True
        final_text = str(parsed_obj.get('final_text') or '').strip()
        if final_text:
            parsed_final_text_explicit = True
        reason = _truncate_text(str(parsed_obj.get('reason') or reason), 600)
    if not parsed_obj:
        # 弱结构兜底：即使 JSON 不完整，也尽量抽取 confirmed/final_text
        m_confirmed = re.search(r'"?confirmed"?\s*[:：]\s*(true|false|1|0|"true"|"false")', text, re.IGNORECASE)
        if m_confirmed:
            ctext = m_confirmed.group(1).strip().strip('"').lower()
            if ctext in ('true', '1'):
                confirmed = True
                parsed_confirmed_explicit = True
            elif ctext in ('false', '0'):
                confirmed = False
                parsed_confirmed_explicit = True
        m_final = re.search(r'"?final_text"?\s*[:：]\s*"([^"\n\r}]*)"', text, re.IGNORECASE)
        if m_final:
            final_text = m_final.group(1).strip()
            if final_text:
                parsed_final_text_explicit = True
        else:
            # 兼容 markdown 风格：final_text: xxx（非引号）
            m_final_loose = re.search(r'final_text\s*[:：]\s*([^\n\r,}]+)', text, re.IGNORECASE)
            if m_final_loose:
                final_text = m_final_loose.group(1).strip().strip('"\'')
                if final_text:
                    parsed_final_text_explicit = True
    if not final_text:
        final_text = str(fallback_text or '').strip()
    if confirmed is None:
        confirmed = (final_text == str(fallback_text or '').strip())
    return {
        'confirmed': 'true' if confirmed else 'false',
        'final_text': final_text,
        'reason': reason,
        'raw': _truncate_text(text, 1200),
        # 仅当模型明确给出关键字段时视为有效；纯兜底推断应触发重试。
        'parsed_ok': 'true' if (parsed_confirmed_explicit or parsed_final_text_explicit) else 'false',
    }


def _self_check_once(
    judge_name: str,
    model_id: str,
    base_url: str,
    api_key: str,
    crop_b64: str,
    full_b64: str,
    self_result: str,
    card_context: str,
    doc_context: str,
    prompt_tail: str = '',
) -> Dict[str, Any]:
    if not api_key:
        return {'judge': judge_name, 'success': False, 'error': 'missing_api_key', 'final_text': self_result, 'confirmed': 'false', 'reason': ''}
    prompt = (
        "你是手写识字复核助手。下面给你的“候选结果”就是你上一轮自己的识别结果。\n"
        "请只复核这一个结果，可确认不改，也可修正为你认为更正确的结果。\n"
        "输出一行 JSON，不要其它文字：\n"
        '{"confirmed":true|false,"final_text":"复核后的最终结果","reason":"一句话理由"}\n\n'
        f'候选结果：{self_result}\n'
        "补充原则：若候选词句明显不通顺，或为非公众熟知人物人名，则此候选答案每个字都不可信，优先修正。\n"
        "上下文补充（仅参考，以图像为准）：\n"
        f'卡片上下文：{_truncate_text(card_context, 500)}\n'
        f'文档上下文：{_truncate_text(doc_context, 1000)}\n'
    )
    tail = str(prompt_tail or '').strip()
    if tail:
        prompt = f'{prompt}\n{tail}\n'
    content = [
        {'type': 'text', 'text': '【D版面裁切图】（主依据）'},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(crop_b64)}},
        {'type': 'text', 'text': '【完整原图】（辅助定位）'},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(full_b64)}},
        {'type': 'text', 'text': prompt},
    ]
    last_error = ''
    for attempt in range(1, _JUDGE_RETRY_ATTEMPTS + 1):
        try:
            client = OpenAI(api_key=api_key, base_url=base_url.rstrip('/') + '/', timeout=180)
            kwargs: Dict[str, Any] = {
                'model': model_id,
                'messages': [{'role': 'user', 'content': content}],
                'temperature': 0,
                'max_tokens': 5000 if str(model_id or '').strip() == 'gemini-3.1-pro-preview' else 800,
            }
            if 'qwen' in model_id.lower():
                kwargs['extra_body'] = {'enable_thinking': False}
            rsp = client.chat.completions.create(**kwargs)
            out = str(rsp.choices[0].message.content or '').strip()
            parsed = _parse_self_check_result(out, self_result)
            if str(parsed.get('parsed_ok') or '').strip().lower() != 'true':
                raise RuntimeError(f'self_check_invalid_output: {parsed.get("raw") or _truncate_text(out, 240)}')
            return {
                'judge': judge_name,
                'success': True,
                'error': '',
                'attempts': attempt,
                **parsed,
            }
        except Exception as e:
            last_error = _truncate_text(str(e), 240)
            if attempt < _JUDGE_RETRY_ATTEMPTS:
                time.sleep(0.8 * attempt)
    return {
        'judge': judge_name,
        'success': False,
        'error': last_error,
        'final_text': self_result,
        'confirmed': 'false',
        'reason': '',
        'raw': '',
        'attempts': _JUDGE_RETRY_ATTEMPTS,
    }


def _save_ci_lite_recognition_bundle(
    paths: Dict[str, str],
    analysis_id: str,
    unit_id: str,
    recognition_map: Dict[str, Dict[str, Any]],
    selected_regions: List[Dict[str, Any]],
    mode: str,
) -> str:
    """写入 ci_audit/d_region_lite_recognition_{unit_id}.json；与已有文件按 region_id 合并，仅覆盖本轮所选 D 区，便于单独重做部分版面。"""
    audit_dir = os.path.join(paths['root'], _D_REGION_AUDIT_SUBDIR)
    os.makedirs(audit_dir, exist_ok=True)
    rel_name = f'd_region_lite_recognition_{unit_id}.json'
    path = os.path.join(audit_dir, rel_name)
    by_id: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                old_data = json.load(handle)
            if isinstance(old_data, dict):
                for item in old_data.get('regions') or []:
                    if not isinstance(item, dict):
                        continue
                    rid = str(item.get('region_id') or '').strip()
                    if not rid:
                        continue
                    by_id[rid] = copy.deepcopy(item)
                    order.append(rid)
        except Exception:
            by_id = {}
            order = []

    finished_at = _now_iso()
    for r in selected_regions or []:
        if not isinstance(r, dict):
            continue
        rid = str(r.get('region_id') or '').strip()
        if not rid:
            continue
        prev = by_id.get(rid) if isinstance(by_id.get(rid), dict) else {}
        pay = copy.deepcopy(recognition_map.get(rid) or {})
        by_id[rid] = {
            'region_id': rid,
            'title': (r.get('title') if r.get('title') is not None else prev.get('title')) or '',
            'rank': int(r.get('rank') if r.get('rank') is not None else prev.get('rank') or 0),
            'payload': pay,
        }
        if rid not in order:
            order.append(rid)

    regions_out = [by_id[rid] for rid in order if rid in by_id]
    payload = {
        'version': _AUTO_ITERATION_VERSION,
        'mode': mode,
        'analysis_id': analysis_id,
        'unit_id': unit_id,
        'saved_at': finished_at,
        'merge_note': 'regions merged by region_id; only batch-selected ids were overwritten',
        'regions': regions_out,
    }
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return os.path.join(_D_REGION_AUDIT_SUBDIR, rel_name).replace('\\', '/')


def _classify_region_recognition_qwen_lite(
    region: Dict[str, Any],
    asset_abs_path: str,
    tmp_dir: str,
    recognition_context: Dict[str, Any],
    sketch_preprocess: Optional[bool] = None,
    coarse_layout: bool = False,
) -> Dict[str, Any]:
    """仅 Qwen 初识 + Qwen 自检，不进入裁判/仲裁。"""
    normalized_bbox = _normalize_region_bbox(region)
    if not normalized_bbox:
        return _build_auto_recognition_payload('', 'black', 'invalid_region_bbox')

    region_id = str(region.get('region_id') or 'region')
    if not asset_abs_path or not os.path.isfile(asset_abs_path):
        return _build_auto_recognition_payload(
            '',
            '',
            'missing_source_sketch',
            recognition_error='missing_source_sketch',
            ocr_failed=True,
        )

    card_ctx = recognition_context.get('card_context') or ''
    doc_ctx = recognition_context.get('doc_context') or ''

    use_pre = _effective_sketch_preprocess(sketch_preprocess)
    preprocess_full_path = _write_preprocessed_sketch_fullpage(asset_abs_path, tmp_dir, enabled=use_pre)
    crop_source_path = preprocess_full_path or asset_abs_path
    os.makedirs(tmp_dir, exist_ok=True)
    safe_region_id = re.sub(r'[^\w\-]', '_', region_id or 'region')
    crop_path = os.path.join(tmp_dir, f'{safe_region_id}_sketch.png')
    q_payload: Dict[str, Any] = {}
    try:
        cropped_image, _crop_b64 = _crop_image_by_region(crop_source_path, normalized_bbox)
        cropped_image.convert('RGB').save(crop_path, format='PNG')
        q_payload = _recognize_single_model(
            _qwen_model(),
            crop_path,
            card_ctx,
            doc_ctx,
            '',
            qwen_prompt_suffix=_qwen_lite_prompt_suffix_full(coarse_layout),
        )
    finally:
        for p in (crop_path, preprocess_full_path):
            if p and os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    if not q_payload.get('success'):
        return _build_auto_recognition_payload(
            '',
            '',
            'model_recognition_failed',
            recognition_error=_truncate_text(str(q_payload.get('error') or 'qwen_failed'), 240),
            ocr_failed=True,
            recognition_source='sketch_snippet_qwen_lite_v1',
        )

    qwen_text = _strip_dmt_overlay_labels(q_payload.get('result') or '')
    try:
        crop_b64 = _build_d_region_crop_preview_b64(region, asset_abs_path, tmp_dir, sketch_preprocess=sketch_preprocess)
        full_b64 = _build_d_region_marked_full_preview_b64(region, asset_abs_path)
    except Exception as exc:
        return _build_auto_recognition_payload(
            qwen_text,
            'black',
            'lite_marked_image_failed',
            recognition_error=_truncate_text(str(exc), 240),
            ocr_failed=True,
            recognition_source='sketch_snippet_qwen_lite_v1',
        )

    sc = _self_check_once(
        'qwen_self_check',
        _auto_ci_sm('ci_auto_qwen', 'qwen3.6-plus'),
        _JUDGE_QWEN_BASE,
        _JUDGE_QWEN_KEY,
        crop_b64,
        full_b64,
        qwen_text,
        card_ctx,
        doc_ctx,
        prompt_tail=_qwen_lite_self_check_tail_full(coarse_layout),
    )
    final_text = _strip_dmt_overlay_labels(str(sc.get('final_text') or '').strip() or qwen_text)
    norm_final = str(_normalize_vocab_key(final_text) or '').strip()
    recognition = 'white' if str(final_text).strip() else 'black'
    reason = 'qwen_lite_self_check_ok' if recognition == 'white' else 'qwen_lite_empty'

    extra = {
        'model_predictions': {
            'gemini': {'text': '', 'normalized_text': '', 'success': False, 'error': 'skipped_in_lite'},
            'qwen': {
                'text': final_text,
                'normalized_text': norm_final,
                'success': True,
                'error': '',
            },
        },
        'selection_required': False,
        'suggested_target_text': final_text,
        'selected_model': 'qwen',
        'pipeline': 'qwen_lite',
        'source_asset_kind': 'original_sketch',
        'disagreement_adjudication': {
            'enabled': True,
            'triggered': False,
            'pipeline': 'qwen_lite',
            'self_checks': [copy.deepcopy(sc)],
            'reason': 'qwen_lite_self_check_only',
        },
        'recognized_text': final_text,
    }
    return _build_auto_recognition_payload(
        final_text,
        recognition,
        reason,
        recognition_source='sketch_snippet_qwen_lite_v1',
        extra_payload=extra,
    )


def _arbitrate_disagreement_once(
    crop_b64: str,
    full_b64: str,
    option1: str,
    option2: str,
    judge_results: List[Dict[str, Any]],
    card_context: str,
    doc_context: str,
) -> Dict[str, Any]:
    if not _JUDGE_GEMINI_KEY:
        return {'success': False, 'error': 'missing_api_key', 'vote': '', 'corrected_text': '', 'reason': ''}
    judge_lines: List[str] = []
    for item in judge_results:
        judge_lines.append(
            f"- {item.get('judge')}: vote={item.get('vote') or 'unknown'} ; corrected={item.get('corrected_text') or '（空）'} ; reason={item.get('reason') or item.get('error') or '（空）'}"
        )
    prompt = (
        "你是手写识字终裁助手。两位裁判给出了分歧结论，请你基于图像证据再仲裁一次。\n"
        "可选输出：option1 / option2 / neither（并给 corrected_text）。\n"
        "只输出一行 JSON：\n"
        '{"vote":"option1|option2|neither","corrected_text":"可空","reason":"一句话理由"}\n\n'
        f'候选1：{option1}\n'
        f'候选2：{option2}\n\n'
        "两位裁判分歧信息：\n"
        + "\n".join(judge_lines) + "\n\n"
        "上下文补充（仅参考，以图像为准）：\n"
        f'卡片上下文：{_truncate_text(card_context, 500)}\n'
        f'文档上下文：{_truncate_text(doc_context, 1000)}\n'
    )
    content = [
        {'type': 'text', 'text': '【D版面裁切图】（主依据）'},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(crop_b64)}},
        {'type': 'text', 'text': '【完整原图】（辅助定位）'},
        {'type': 'image_url', 'image_url': {'url': _inline_data_url_from_png_b64_maybe_compress(full_b64)}},
        {'type': 'text', 'text': prompt},
    ]
    last_error = ''
    for attempt in range(1, _JUDGE_RETRY_ATTEMPTS + 1):
        try:
            client = OpenAI(api_key=_JUDGE_GEMINI_KEY, base_url=_JUDGE_GEMINI_BASE.rstrip('/') + '/', timeout=180)
            rsp = client.chat.completions.create(
                model=_auto_local_candidate_model(),
                messages=[{'role': 'user', 'content': content}],
                temperature=0,
                max_tokens=800,
            )
            out = str(rsp.choices[0].message.content or '').strip()
            parsed = _parse_judge_vote(out)
            if str(parsed.get('parsed_ok') or '').strip().lower() != 'true':
                raise RuntimeError(f'arbitration_invalid_output_no_vote: {parsed.get("raw") or _truncate_text(out, 240)}')
            return {'success': True, 'error': '', 'attempts': attempt, **parsed}
        except Exception as e:
            last_error = _truncate_text(str(e), 240)
            if attempt < _JUDGE_RETRY_ATTEMPTS:
                time.sleep(0.8 * attempt)
    return {'success': False, 'error': last_error, 'vote': '', 'corrected_text': '', 'reason': '', 'raw': '', 'attempts': _JUDGE_RETRY_ATTEMPTS}


def _attach_disagreement_adjudication_for_probe(
    payload: Dict[str, Any],
    region: Dict[str, Any],
    asset_abs_path: str,
    tmp_dir: str,
    recognition_context: Dict[str, Any],
    sketch_preprocess: Optional[bool] = None,
) -> Dict[str, Any]:
    out = copy.deepcopy(payload or {})
    recognition = str(out.get('recognition') or '').strip().lower()
    preds = out.get('model_predictions') if isinstance(out.get('model_predictions'), dict) else {}
    gemini_text = str((preds.get('gemini') or {}).get('text') or '').strip()
    qwen_text = str((preds.get('qwen') or {}).get('text') or '').strip()
    if not gemini_text and not qwen_text:
        return out
    try:
        crop_b64 = _build_d_region_crop_preview_b64(
            region=region,
            asset_abs_path=asset_abs_path,
            tmp_dir=tmp_dir,
            sketch_preprocess=sketch_preprocess,
        )
        full_b64 = _build_d_region_marked_full_preview_b64(
            region=region,
            asset_abs_path=asset_abs_path,
        )
    except Exception as e:
        out['disagreement_adjudication'] = {
            'enabled': True,
            'triggered': True,
            'error': _truncate_text(str(e), 240),
            'judges': [],
        }
        return out

    # 第一轮后先让两个选手各自复核自己的答案
    self_checks = [
        ('gemini_self_check', _auto_ci_sm('ci_auto_gemini_pro', 'gemini-3.1-pro-preview'), _JUDGE_GEMINI_BASE, _JUDGE_GEMINI_KEY, gemini_text),
        ('qwen_self_check', _auto_ci_sm('ci_auto_qwen', 'qwen3.6-plus'), _JUDGE_QWEN_BASE, _JUDGE_QWEN_KEY, qwen_text),
    ]
    self_check_results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _self_check_once,
                jname,
                mid,
                burl,
                key,
                crop_b64,
                full_b64,
                base_text,
                recognition_context.get('card_context') or '',
                recognition_context.get('doc_context') or '',
            )
            for (jname, mid, burl, key, base_text) in self_checks
        ]
        for fut in futures:
            self_check_results.append(fut.result())
    checked_gemini = next((str(item.get('final_text') or '').strip() for item in self_check_results if item.get('judge') == 'gemini_self_check'), gemini_text)
    checked_qwen = next((str(item.get('final_text') or '').strip() for item in self_check_results if item.get('judge') == 'qwen_self_check'), qwen_text)
    if isinstance(out.get('model_predictions'), dict):
        out['model_predictions']['gemini']['text'] = checked_gemini
        out['model_predictions']['gemini']['normalized_text'] = str(_normalize_vocab_key(checked_gemini) or '').strip()
        out['model_predictions']['qwen']['text'] = checked_qwen
        out['model_predictions']['qwen']['normalized_text'] = str(_normalize_vocab_key(checked_qwen) or '').strip()
    gemini_norm = str((out.get('model_predictions', {}).get('gemini') or {}).get('normalized_text') or '').strip()
    qwen_norm = str((out.get('model_predictions', {}).get('qwen') or {}).get('normalized_text') or '').strip()
    # 最终白/灰/黑判定以后验裁决为准：
    # 1) 自检后双模型一致 => 白区
    # 2) 其余先走裁判；裁判同票/分歧都先按灰区
    # 3) 仅当仲裁明确给出 neither => 黑区
    if gemini_norm and qwen_norm and gemini_norm == qwen_norm:
        agreed_text = checked_qwen or checked_gemini
        out['recognition'] = 'white'
        out['recognition_reason'] = 'self_check_models_agree_white'
        out['recognized_text'] = agreed_text
        out['selected_model'] = 'self_check_agreement'
        out['suggested_target_text'] = agreed_text
        out['selection_required'] = False
        out['disagreement_adjudication'] = {
            'enabled': True,
            'triggered': False,
            'self_checks': self_check_results,
            'reason': 'self_check_models_agree_white',
        }
        return out

    judges = [
        ('judge_qwen3.6_plus', _auto_ci_sm('ci_auto_qwen', 'qwen3.6-plus'), _JUDGE_QWEN_BASE, _JUDGE_QWEN_KEY),
        ('judge_gemini3.1_pro_dmxapi', _auto_ci_sm('ci_auto_gemini_pro', 'gemini-3.1-pro-preview'), _JUDGE_GEMINI_BASE, _JUDGE_GEMINI_KEY),
    ]
    judge_results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _judge_disagreement_once,
                jname,
                mid,
                burl,
                key,
                crop_b64,
                full_b64,
                checked_gemini,
                checked_qwen,
                recognition_context.get('card_context') or '',
                recognition_context.get('doc_context') or '',
            )
            for (jname, mid, burl, key) in judges
        ]
        for fut in futures:
            judge_results.append(fut.result())

    vote_counter = {'option1': 0, 'option2': 0, 'neither': 0}
    for jr in judge_results:
        vote = str(jr.get('vote') or '')
        if vote in vote_counter:
            vote_counter[vote] += 1
    final_vote = ''
    if vote_counter['option1'] > vote_counter['option2'] and vote_counter['option1'] > vote_counter['neither']:
        final_vote = 'option1'
    elif vote_counter['option2'] > vote_counter['option1'] and vote_counter['option2'] > vote_counter['neither']:
        final_vote = 'option2'
    elif vote_counter['neither'] > max(vote_counter['option1'], vote_counter['option2']):
        final_vote = 'neither'
    corrected_candidates = [str(jr.get('corrected_text') or '').strip() for jr in judge_results if str(jr.get('corrected_text') or '').strip()]
    arbitration_result: Dict[str, Any] = {}
    if not final_vote:
        arbitration_result = _arbitrate_disagreement_once(
            crop_b64=crop_b64,
            full_b64=full_b64,
            option1=checked_gemini,
            option2=checked_qwen,
            judge_results=judge_results,
            card_context=recognition_context.get('card_context') or '',
            doc_context=recognition_context.get('doc_context') or '',
        )
        if arbitration_result.get('success') and arbitration_result.get('vote'):
            final_vote = str(arbitration_result.get('vote') or '').strip()
            arb_corrected = str(arbitration_result.get('corrected_text') or '').strip()
            if arb_corrected:
                corrected_candidates.insert(0, arb_corrected)
    final_corrected = corrected_candidates[0] if corrected_candidates else ''
    is_judge_unanimous = sum(1 for v in vote_counter.values() if v > 0) == 1
    # 仲裁为 neither 时，只有在“仲裁给出的修正文本与两位裁判主张都不一致”才判黑区。
    arbitration_vote = str(arbitration_result.get('vote') or '').strip().lower()
    if arbitration_vote == 'neither':
        arbitration_corrected = str(arbitration_result.get('corrected_text') or '').strip()
        consistent_with_judges = _text_consistent_with_judge_opinions(
            arbitration_corrected,
            judge_results,
            checked_gemini,
            checked_qwen,
            ratio_threshold=0.8,
        ) if arbitration_corrected else False
        if arbitration_corrected and not consistent_with_judges:
            out['recognition'] = 'black'
            out['recognition_reason'] = 'arbitration_neither_and_conflict_with_judges_black'
            out['recognized_text'] = ''
            out['selected_model'] = 'arbitration_neither'
            out['suggested_target_text'] = ''
            out['selection_required'] = False
        else:
            resolved_text = arbitration_corrected or final_corrected or checked_qwen or checked_gemini
            out['recognition'] = 'gray'
            out['recognition_reason'] = 'arbitration_neither_but_close_to_judges_gray'
            out['recognized_text'] = resolved_text
            out['selected_model'] = 'arbitration_neither_gray'
            out['suggested_target_text'] = resolved_text
            out['selection_required'] = True
            out['gray_quality_hint'] = 'normal'
    else:
        arbitration_rule_note = ''
        arbitration_resolved_override = ''
        if arbitration_vote in ('option1', 'option2'):
            arbitration_resolved_override, arbitration_rule_note = _apply_arbitration_similarity_length_rule(
                arbitration_vote=arbitration_vote,
                option1_text=checked_gemini,
                option2_text=checked_qwen,
            )
            arbitration_result['post_similarity_length_rule'] = arbitration_rule_note
            if arbitration_resolved_override:
                arbitration_result['post_similarity_length_result'] = arbitration_resolved_override
        resolved_text = ''
        resolution_source = 'judge'
        if final_vote == 'option1':
            resolved_text = checked_gemini
            resolution_source = 'judge_option1'
        elif final_vote == 'option2':
            resolved_text = checked_qwen
            resolution_source = 'judge_option2'
        elif final_vote == 'neither':
            resolved_text = final_corrected
            resolution_source = 'judge_neither'
        if arbitration_vote == 'option1':
            resolved_text = checked_gemini
            resolution_source = 'arbitration_option1'
        elif arbitration_vote == 'option2':
            resolved_text = checked_qwen
            resolution_source = 'arbitration_option2'
        elif arbitration_vote == 'neither':
            resolved_text = ''
            resolution_source = 'arbitration_neither'
        if arbitration_resolved_override:
            if arbitration_resolved_override == checked_gemini:
                resolution_source = 'arbitration_postrule_option1'
            elif arbitration_resolved_override == checked_qwen:
                resolution_source = 'arbitration_postrule_option2'
            else:
                resolution_source = 'arbitration_postrule_custom'
            resolved_text = arbitration_resolved_override
        if not resolved_text:
            resolved_text = final_corrected or checked_qwen or checked_gemini
        out['recognition'] = 'gray'
        out['recognition_reason'] = (
            'judge_unanimous_gray_preferred'
            if is_judge_unanimous
            else 'judge_disagree_gray'
        )
        out['recognized_text'] = resolved_text
        out['selected_model'] = resolution_source
        out['suggested_target_text'] = resolved_text
        out['selection_required'] = True
        out['gray_quality_hint'] = 'preferred' if is_judge_unanimous else 'normal'

    out['disagreement_adjudication'] = {
        'enabled': True,
        'triggered': True,
        'option1_text': checked_gemini,
        'option2_text': checked_qwen,
        'votes': vote_counter,
        'final_vote': final_vote,
        'corrected_text': final_corrected,
        'judge_unanimous': is_judge_unanimous,
        'self_checks': self_check_results,
        'arbitration': arbitration_result,
        'judges': judge_results,
    }
    return out


def _build_auto_iteration_notebook_context(username: str, manifest: Dict[str, Any]) -> Dict[str, Any]:
    notebook_ctx = _gather_notebook_context(username)
    context_config = manifest.get('context_config') or {}
    return _filter_user_selected_context(
        notebook_ctx,
        username=username,
        selected_files=manifest.get('selected_files') or [],
        context_docs=context_config.get('user_selected_docs'),
        context_card_ids=context_config.get('user_selected_card_ids'),
    )


def _build_card_context_text(notebook_ctx: Dict[str, Any]) -> str:
    lines: List[str] = []
    for card in (notebook_ctx.get('card_summaries') or [])[:12]:
        title = _truncate_text(card.get('title') or '未命名卡片', 80)
        keywords = _truncate_text(card.get('keywords') or '', 160)
        # 勾选卡片场景下：卡片内容不足 500 字时尽量全量透传。
        preview = _truncate_text(card.get('preview') or '', 500)
        parts = [title]
        if keywords:
            parts.append(f'关键词：{keywords}')
        if preview:
            parts.append(f'内容：{preview}')
        lines.append(' | '.join(parts))
    return '\n'.join(lines)


def _build_doc_context_text(notebook_ctx: Dict[str, Any]) -> str:
    lines: List[str] = []
    for doc in (notebook_ctx.get('doc_summaries') or [])[:6]:
        file_name = _truncate_text(doc.get('file_name') or '未命名文档', 80)
        summary = _truncate_text(doc.get('summary') or doc.get('pre_summary') or doc.get('pre_image_summary') or '', 480)
        lines.append(f'{file_name}：{summary or "（空）"}')
    return '\n'.join(lines)


def _build_auto_iteration_recognition_context(
    notebook_ctx: Dict[str, Any],
    use_recognition_context: bool = True,
) -> Dict[str, Any]:
    if not use_recognition_context:
        return {
            'card_context': '',
            'doc_context': '',
            'candidate_vocab_text': '',
            'candidate_vocab_scenes': [],
            'candidate_vocab_terms': set(),
        }
    card_context = _build_card_context_text(notebook_ctx)
    doc_context = _build_doc_context_text(notebook_ctx)
    candidate_vocab = build_candidate_vocab_payload(card_context, doc_context)
    return {
        'card_context': card_context,
        'doc_context': doc_context,
        'candidate_vocab_text': candidate_vocab.get('text') or '',
        'candidate_vocab_terms': candidate_vocab.get('normalized_terms') or set(),
        'candidate_vocab_scenes': candidate_vocab.get('matched_scenes') or [],
    }


def _resolve_unit_asset_abs_path(paths: Dict[str, str], manifest: Dict[str, Any], unit_id: str) -> str:
    for unit in manifest.get('input_units') or []:
        if not isinstance(unit, dict) or str(unit.get('unit_id') or '').strip() != unit_id:
            continue
        asset_rel = str(unit.get('asset_path') or '').strip()
        if not asset_rel:
            return ''
        candidate = os.path.normpath(os.path.join(paths['root'], asset_rel))
        if os.path.isfile(candidate):
            return candidate
    return ''


def _build_page_context_text(iter_context: Dict[str, Any]) -> str:
    return '\n'.join([
        f"- T层补充：{iter_context.get('t_focus_text', '') or '（空）'}",
        f"- 主要内容：{iter_context.get('main_content', '') or '（空）'}",
        f"- 版面区域：{iter_context.get('layout_regions_text', '') or '（空）'}",
        f"- 阅读顺序：{iter_context.get('reading_order', '') or '（空）'}",
        f"- 手写/印刷关系：{iter_context.get('handwriting_printing_relation', '') or '（空）'}",
        f"- 批注关系：{iter_context.get('annotation_section', '') or '（空）'}",
        f"- 与前图关系：{iter_context.get('continuity_text', '') or '（空）'}",
        f"- M层复核：{iter_context.get('m_verification_text', '') or '（空）'}",
    ])


def _format_notebook_context_text(notebook_ctx: Dict[str, Any]) -> str:
    parts = [
        f"场景：{notebook_ctx.get('scene_name', '') or '未提供'} / {notebook_ctx.get('sub_scene_name', '') or '未提供'}",
        f"本子说明：{notebook_ctx.get('notebook_description', '') or '未提供'}",
        f"场景摘要：{notebook_ctx.get('scene_summary', '') or '未提供'}",
    ]
    doc_lines = []
    for doc in (notebook_ctx.get('doc_summaries') or [])[:3]:
        summary = _truncate_text(doc.get('summary') or doc.get('pre_summary') or doc.get('pre_image_summary') or '', 220)
        if summary:
            doc_lines.append(f"- {doc.get('file_name') or '未命名文档'}：{summary}")
    if doc_lines:
        parts.append('关联文档：')
        parts.extend(doc_lines)
    card_lines = []
    for card in (notebook_ctx.get('card_summaries') or [])[:5]:
        text = ' | '.join([
            _truncate_text(card.get('title') or '未命名卡片', 60),
            _truncate_text(card.get('keywords') or '', 80),
            _truncate_text(card.get('preview') or '', 120),
        ]).strip(' |')
        if text:
            card_lines.append(f'- {text}')
    if card_lines:
        parts.append('卡片知识：')
        parts.extend(card_lines)
    return '\n'.join(parts)


def _parse_auto_region_plan(raw: Any) -> Optional[Dict[str, Any]]:
    parsed = _parse_llm_json(raw, {})
    if not parsed:
        repaired = _repair_json_locally(_normalize_llm_response_text(raw))
        if repaired:
            try:
                parsed = _parse_llm_json(repaired, {})
            except Exception:
                parsed = {}
    if not isinstance(parsed, dict) or not parsed:
        return None
    instruction_text = _truncate_text(parsed.get('instruction_text') or '', 2000)
    if not instruction_text:
        return None
    if '其他不要变' not in instruction_text and '其他地方不要变' not in instruction_text:
        instruction_text = instruction_text.rstrip('。；; ') + '，只改这个区域，其他不要变。'
    return {
        'instruction_text': instruction_text,
        'target_text_hint': _truncate_text(parsed.get('target_text_hint') or '', 200),
        'reason': _truncate_text(parsed.get('reason') or '', 300),
        'used_context': bool(parsed.get('used_context', False)),
    }


def _build_auto_region_fallback_instruction(region: Dict[str, Any], recognition_payload: Dict[str, Any]) -> Dict[str, Any]:
    recognized_text = recognition_payload.get('recognized_text') or ''
    text_hint = _truncate_text(recognition_payload.get('context_excerpt') or recognized_text, 80)
    instruction = '参考原始草图与本子上下文，把这个区域整理为更清晰、规整、可辨认的内容，尽量恢复真实文字，不要越界扩写，只改这个区域，其他不要变。'
    if text_hint:
        instruction = f'参考原始草图与本子上下文，把这个区域整理为更清晰、规整、可辨认的内容，优先朝“{text_hint}”靠拢，只改这个区域，其他不要变。'
    return {
        'instruction_text': instruction,
        'target_text_hint': text_hint,
        'reason': 'local_fallback',
        'used_context': bool(recognition_payload.get('context_excerpt')),
    }


def _plan_auto_region_instruction(
    region: Dict[str, Any],
    recognition_payload: Dict[str, Any],
    current_context: Dict[str, Any],
    notebook_ctx: Dict[str, Any],
    original_crop_b64: str,
    reproduction_crop_b64: str,
) -> Dict[str, Any]:
    region_title = str(region.get('title') or region.get('region_id') or '当前区域').strip()
    position_text = '未知位置'
    bbox = _normalize_region_bbox(region)
    if bbox:
        center_x = bbox['x'] + bbox['w'] / 2.0
        center_y = bbox['y'] + bbox['h'] / 2.0
        horizontal = '左侧' if center_x < 0.34 else ('右侧' if center_x > 0.66 else '中部')
        vertical = '上部' if center_y < 0.34 else ('下部' if center_y > 0.66 else '中部')
        if horizontal == '中部' and vertical == '中部':
            position_text = '画面中部'
        elif horizontal == '中部':
            position_text = f'画面{vertical}'
        elif vertical == '中部':
            position_text = f'画面{horizontal}'
        else:
            position_text = f'画面{vertical}{horizontal}'

    user_text = f"""请为这个灰区 D 版面生成下一步局部裁切迭代所需的 revision_instruction。

## 当前锁定区域
- 区域：{region_title}
- 位置：{position_text}
- region_id：{region.get('region_id') or ''}

## 当前复现图局部 OCR 结果
- 识别文字：{recognition_payload.get('recognized_text') or '（空）'}
- 判定结果：gray
- 判定原因：{recognition_payload.get('recognition_reason') or '（空）'}

## 当前页理解
{_build_page_context_text(current_context)}

## 本子上下文
{_format_notebook_context_text(notebook_ctx)}

## 规划要求
1. 第一张图是当前复现图中的锁定区域；第二张图是同位置的原始草图局部。
2. 以原始草图视觉因素和本子上下文为主，结合当前复现图 OCR 文字，推断这个区域应该改成什么内容。
3. instruction_text 尽量精简，必须适合直接交给生图模型执行。
4. 必须明确“只改这个区域，其他不要变”。
5. 不能扩写到其他区域，也不能引入超出上下文边界的新知识。

请严格输出 JSON。"""
    user_content: List[Dict[str, Any]] = [
        {'type': 'text', 'text': '【当前复现图局部】'},
        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{reproduction_crop_b64}'}},
    ]
    if original_crop_b64:
        user_content.extend([
            {'type': 'text', 'text': '【原始草图局部】'},
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{original_crop_b64}'}},
        ])
    user_content.append({'type': 'text', 'text': user_text})

    raw = _call_qwen_vl_flash_fast(_AUTO_REGION_PLANNER_SYSTEM_PROMPT, user_content, _AUTO_REGION_PLAN_TIMEOUT)
    parsed = _parse_auto_region_plan(raw)
    if parsed:
        return parsed

    fallback_text = '\n'.join([
        user_text,
        '请仅根据上面的文字内容补一条简短可执行的 revision_instruction，必须包含“只改这个区域，其他不要变”。',
    ])
    fallback_payload = [{'type': 'text', 'text': fallback_text}]
    for caller, attempts in ((_call_qwen35_plus_m_layer_llm, 1), (_call_qwen35_m_layer_llm, 1)):
        raw = caller(_AUTO_REGION_PLANNER_SYSTEM_PROMPT, fallback_payload, _AUTO_REGION_PLAN_TIMEOUT, attempts)
        parsed = _parse_auto_region_plan(raw)
        if parsed:
            return parsed
    return _build_auto_region_fallback_instruction(region, recognition_payload)


def _bbox_overlap_ratio(box_a: Dict[str, float], box_b: Dict[str, float]) -> float:
    left = max(box_a['x'], box_b['x'])
    top = max(box_a['y'], box_b['y'])
    right = min(box_a['x'] + box_a['w'], box_b['x'] + box_b['w'])
    bottom = min(box_a['y'] + box_a['h'], box_b['y'] + box_b['h'])
    inter_w = max(0.0, right - left)
    inter_h = max(0.0, bottom - top)
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    area_a = max(box_a['w'] * box_a['h'], 1e-6)
    area_b = max(box_b['w'] * box_b['h'], 1e-6)
    return inter / min(area_a, area_b)


def _normalize_selected_region_ids(selected_region_ids: Any, max_count: int = _AUTO_MAX_BATCH_SIZE) -> List[str]:
    cap = max(1, int(max_count or _AUTO_MAX_BATCH_SIZE))
    if not isinstance(selected_region_ids, list):
        return []
    normalized: List[str] = []
    for item in selected_region_ids:
        region_id = str(item or '').strip()
        if not region_id or region_id in normalized:
            continue
        normalized.append(region_id)
        if len(normalized) >= cap:
            break
    return normalized


def _select_auto_iteration_regions(
    overlay_item: Dict[str, Any],
    start_region_id: str = '',
    continue_from_cursor: bool = True,
    selected_region_ids: Optional[List[str]] = None,
    max_manual_batch: int = _AUTO_MAX_BATCH_SIZE,
) -> Tuple[List[Dict[str, Any]], str, int, str]:
    d_regions = [
        region for region in (overlay_item.get('regions') or [])
        if isinstance(region, dict) and str(region.get('level') or '').lower() == 'd'
    ]
    d_regions.sort(key=lambda item: (int(item.get('rank') or 999), float((item.get('bbox') or {}).get('y') or 0.0), float((item.get('bbox') or {}).get('x') or 0.0), str(item.get('region_id') or '')))
    if not d_regions:
        return [], '', 0, _AUTO_SELECTION_SOURCE_CURSOR

    manual_cap = max(1, int(max_manual_batch or _AUTO_MAX_BATCH_SIZE))
    normalized_selected_ids = _normalize_selected_region_ids(selected_region_ids, max_count=manual_cap)
    if normalized_selected_ids:
        by_id = {
            str(region.get('region_id') or '').strip(): region
            for region in d_regions
            if str(region.get('region_id') or '').strip()
        }
        selected = [copy.deepcopy(by_id[region_id]) for region_id in normalized_selected_ids if region_id in by_id]
        next_region_id = str((overlay_item.get('auto_iteration') or {}).get('next_region_id') or '').strip()
        return selected[:manual_cap], next_region_id, 0, _AUTO_SELECTION_SOURCE_MANUAL

    start_id = str(start_region_id or '').strip()
    if not start_id and continue_from_cursor:
        auto_iteration = overlay_item.get('auto_iteration') if isinstance(overlay_item.get('auto_iteration'), dict) else {}
        start_id = str(auto_iteration.get('next_region_id') or '').strip()

    start_index = 0
    if start_id:
        for index, region in enumerate(d_regions):
            if str(region.get('region_id') or '').strip() == start_id:
                start_index = index
                break

    selected = d_regions[start_index:start_index + _AUTO_MAX_BATCH_SIZE]
    next_index = start_index + len(selected)
    next_region_id = ''
    if next_index < len(d_regions):
        next_region_id = str(d_regions[next_index].get('region_id') or '').strip()
    return copy.deepcopy(selected), next_region_id, start_index, _AUTO_SELECTION_SOURCE_CURSOR


def _build_unit_for_auto_iteration(username: str, analysis_id: str, manifest: Dict[str, Any], unit_id: str, asset_abs_path: str) -> Dict[str, Any]:
    units = _analysis_units_from_manifest(username, analysis_id, manifest)
    unit = next((item for item in units if item.get('unit_id') == unit_id), None)
    if not unit:
        raise ValueError(f'未找到 unit_id={unit_id} 对应的分析页')
    next_unit = copy.deepcopy(unit)
    next_unit['analysis_id'] = analysis_id
    next_unit['asset_abs_path'] = asset_abs_path
    return next_unit


def _generate_single_region_candidate(
    username: str,
    unit: Dict[str, Any],
    base_repro_abs: str,
    current_item: Dict[str, Any],
    region: Dict[str, Any],
    revision_instruction: str,
    image_quality: str,
    temp_dir: str,
    reference_image_b64: Optional[str] = None,
    reference_image_mime: str = 'image/png',
    reference_image_role: str = 'reference',
) -> Dict[str, Any]:
    region_id = str(region.get('region_id') or '').strip() or 'region'
    normalized_bbox = _normalize_region_bbox(region)
    if not normalized_bbox:
        raise ValueError(f'区域 {region_id} 缺少有效 bbox')

    with Image.open(base_repro_abs) as base_image:
        base_image = base_image.convert('RGBA')
        img_w, img_h = base_image.size
        left, top, right, bottom, target_w, target_h = _region_to_pixel_box(img_w, img_h, normalized_bbox)
        model_input_patch = base_image.crop((left, top, right, bottom)).convert('RGBA')
    # 备用输入：原草图同一D局部（仅在质检判“是”时启用）。
    original_input_patch = None
    unit_asset_abs = str(unit.get('asset_abs_path') or '').strip()
    if unit_asset_abs and os.path.isfile(unit_asset_abs):
        try:
            with Image.open(unit_asset_abs) as original_image:
                original_image = original_image.convert('RGBA')
                ow, oh = original_image.size
                o_left, o_top, o_right, o_bottom, _ow2, _oh2 = _region_to_pixel_box(ow, oh, normalized_bbox)
                original_input_patch = original_image.crop((o_left, o_top, o_right, o_bottom)).convert('RGBA')
        except Exception:
            original_input_patch = None

    input_buf = io.BytesIO()
    model_input_patch.save(input_buf, format='PNG')
    input_bytes = input_buf.getvalue()

    # 约束模型输出与输入局部图尺寸一致，避免后续贴回时文字被压扁/裁掉。
    patch_instruction = (
        f'{str(revision_instruction or "").strip()}\n\n'
        '【局部候选图硬性要求】\n'
        f'- 你必须输出与输入局部图完全相同的分辨率和宽高比：{target_w}×{target_h} 像素。\n'
        f'- 输出画布必须严格等于 {target_w}×{target_h}，禁止输出更大或更小尺寸。\n'
        '- 仅在该局部图内按要求修改，局部外无内容可参考，不要扩写到整图。\n'
    ).strip()

    client = OpenAI(
        api_key=_GEMINI_REPRO_API_KEY,
        base_url=_GEMINI_REPRO_BASE_URL,
        timeout=_GEMINI_REPRO_TIMEOUT,
    )

    model_output_bytes = b''
    model_output_image = None
    model_name = str(_auto_local_candidate_model() or '').strip()
    last_error = ''

    def _generate_once_from_input(local_input_bytes: bytes) -> bytes:
        local_input_b64 = base64.b64encode(local_input_bytes).decode('utf-8')
        if model_name.lower().startswith('gpt-image'):
            # gpt-image 分支保留（后续可能再切回）；当前默认模型已切回 Gemini。
            image_file = io.BytesIO(local_input_bytes)
            image_file.name = f'{region_id}_input.png'
            resp = client.images.edit(
                model=model_name,
                image=image_file,
                prompt=patch_instruction,
                size='auto',
            )
            data = getattr(resp, 'data', None) or []
            if not data:
                raise ValueError('局部候选图生成失败：images.edit 未返回 data')
            item = data[0]
            b64_json = getattr(item, 'b64_json', None)
            if b64_json:
                return base64.b64decode(b64_json)
            url = str(getattr(item, 'url', None) or '').strip()
            if not url:
                raise ValueError('局部候选图生成失败：返回中既无 b64_json 也无 url')
            with urlopen(url, timeout=60) as r:
                return r.read()
        # Gemini 路径：chat.completions + 提图解析链路
        content_parts = [
            {'type': 'text', 'text': '【待修改局部图】（只输出同分辨率同宽高比局部图）：'},
            {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{local_input_b64}'}},
            {'type': 'text', 'text': patch_instruction},
        ]
        response = client.chat.completions.create(
            model=model_name,
            messages=[{'role': 'user', 'content': content_parts}],
            temperature=0.2,
            max_tokens=8192,
        )
        b64_img = _extract_repro_base64_from_completion(response)
        if not b64_img:
            try:
                raw_text = response.choices[0].message.content
                if isinstance(raw_text, str):
                    b64_img = _extract_repro_base64(raw_text)
            except Exception:
                b64_img = None
        if not b64_img:
            raise ValueError('局部候选图生成失败：Gemini 响应未提取到图片')
        return _decode_inline_image_bytes(b64_img)

    qwen_check_decision = '未执行'
    retry_input_bytes: Optional[bytes] = None
    for attempt in range(1, _AUTO_CANDIDATE_RETRY_ATTEMPTS + 1):
        try:
            # 第一次：按现有逻辑用R层局部图输入
            current_input_bytes = input_bytes
            model_output_bytes = _generate_once_from_input(current_input_bytes)
            model_output_image = Image.open(io.BytesIO(model_output_bytes)).convert('RGBA')
            resized_tmp = model_output_image
            if model_output_image.size != (target_w, target_h):
                resized_tmp = model_output_image.resize((target_w, target_h), _resample_lanczos())

            # 新增质检：Qwen 判“是”时改用原草图局部重生（计入本次尝试）
            if original_input_patch is not None:
                resized_buf_for_check = io.BytesIO()
                resized_tmp.save(resized_buf_for_check, format='PNG')
                resized_b64_for_check = base64.b64encode(resized_buf_for_check.getvalue()).decode('utf-8')
                input_b64_for_check = base64.b64encode(current_input_bytes).decode('utf-8')
                judge = _qwen_check_candidate_garbled_needed_retry(input_b64_for_check, resized_b64_for_check)
                qwen_check_decision = judge
                if judge == '是':
                    original_buf = io.BytesIO()
                    original_input_patch.save(original_buf, format='PNG')
                    current_input_bytes = original_buf.getvalue()
                    retry_input_bytes = current_input_bytes
                    # 重新调用一次 Gemini 迭代（若失败，直接算本次 attempt 失败）
                    model_output_bytes = _generate_once_from_input(current_input_bytes)
                    model_output_image = Image.open(io.BytesIO(model_output_bytes)).convert('RGBA')
                    # 供后续 debug 看到最终实际输入
                    input_bytes = current_input_bytes
            break
        except Exception as error:
            last_error = str(error)
            if attempt < _AUTO_CANDIDATE_RETRY_ATTEMPTS:
                time.sleep(0.8 * attempt)
    if model_output_image is None:
        raise ValueError(f'局部候选图生成失败：{last_error or "unknown_error"}')

    resized_image = model_output_image
    resized_changed = False
    if model_output_image.size != (target_w, target_h):
        resized_image = model_output_image.resize((target_w, target_h), _resample_lanczos())
        resized_changed = True

    # 调试落盘：输入图、模型原始输出、必要时落盘拉伸后图。
    temp_dir_norm = os.path.normpath(str(temp_dir or ''))
    # 兼容两种传入：
    # 1) .../reproduction/auto_iter_tmp
    # 2) .../reproduction/auto_iter_tmp/ocr
    # 都统一落到 .../reproduction/auto_iter_candidate_debug
    parent_dir = os.path.dirname(temp_dir_norm)
    if os.path.basename(temp_dir_norm) == _AUTO_OCR_TMP_DIRNAME:
        reproduction_dir = parent_dir
    elif os.path.basename(parent_dir) == _AUTO_OCR_TMP_DIRNAME:
        reproduction_dir = os.path.dirname(parent_dir)
    else:
        reproduction_dir = parent_dir
    debug_root = os.path.normpath(os.path.join(reproduction_dir, _AUTO_CANDIDATE_DEBUG_DIRNAME))
    os.makedirs(debug_root, exist_ok=True)
    debug_prefix = f'{unit.get("unit_id")}_{region_id}_{int(time.time() * 1000)}'
    try:
        Path(os.path.join(debug_root, f'{debug_prefix}_input.png')).write_bytes(input_bytes)
        Path(os.path.join(debug_root, f'{debug_prefix}_model_output.png')).write_bytes(model_output_bytes)
        Path(os.path.join(debug_root, f'{debug_prefix}_check_decision.txt')).write_text(
            f'qwen_check_decision={qwen_check_decision}\n',
            encoding='utf-8',
        )
        if retry_input_bytes:
            Path(os.path.join(debug_root, f'{debug_prefix}_input_after_retry.png')).write_bytes(retry_input_bytes)
        if resized_changed:
            resized_buf = io.BytesIO()
            resized_image.save(resized_buf, format='PNG')
            Path(os.path.join(debug_root, f'{debug_prefix}_resized.png')).write_bytes(resized_buf.getvalue())
    except Exception:
        # 调试文件写失败不影响主流程
        pass

        return {
            'region_id': region_id,
            'left': left,
            'top': top,
            'width': target_w,
            'height': target_h,
        'image': resized_image,
    }


def _apply_candidate_patches(base_repro_abs: str, candidates: List[Dict[str, Any]]) -> None:
    with Image.open(base_repro_abs) as base_image:
        base_image = base_image.convert('RGBA')
        composite = base_image.copy()
        for candidate in candidates:
            patch = candidate.get('image')
            if patch is None:
                continue
            target_w = int(candidate.get('width') or 1)
            target_h = int(candidate.get('height') or 1)
            patch_image = patch.convert('RGBA')
            if patch_image.size != (target_w, target_h):
                patch_image = patch_image.resize((target_w, target_h), _resample_lanczos())
            composite.paste(patch_image, (int(candidate.get('left') or 0), int(candidate.get('top') or 0)))
        composite.convert('RGB').save(base_repro_abs, 'PNG')


def _merge_round_regions(
    regions: List[Dict[str, Any]],
    recognition_map: Dict[str, Dict[str, Any]],
    selected_order: List[str],
    decision_map: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    selected_set = set(selected_order)
    merged: List[Dict[str, Any]] = []
    for region in regions:
        if not isinstance(region, dict):
            continue
        region_id = str(region.get('region_id') or '').strip()
        next_region = copy.deepcopy(region)
        if str(next_region.get('level') or '').lower() == 'd':
            next_region.pop('auto_selected', None)
            next_region.pop('auto_state', None)
            next_region.pop('auto_state_reason', None)
            next_region.pop('auto_instruction_text', None)
        recognition_payload = recognition_map.get(region_id)
        if recognition_payload:
            next_region.update(recognition_payload)
        if region_id in selected_set:
            decision = decision_map.get(region_id, {})
            next_region['auto_selected'] = True
            next_region['auto_state'] = decision.get('decision') or 'selected'
            next_region['auto_state_reason'] = decision.get('reason') or ''
            next_region['auto_instruction_text'] = decision.get('instruction_text') or ''
        merged.append(next_region)
    return merged


def _build_auto_iteration_preview(
    selected_regions: List[Dict[str, Any]],
    recognition_map: Dict[str, Dict[str, Any]],
    next_region_id: str,
    mode: str,
    selection_source: str,
) -> Dict[str, Any]:
    selected_items: List[Dict[str, Any]] = []
    gray_items: List[Dict[str, Any]] = []
    failed_items: List[Dict[str, Any]] = []
    for region in selected_regions:
        region_id = str(region.get('region_id') or '').strip()
        payload = recognition_map.get(region_id, {})
        item = {
            **copy.deepcopy(region),
            **copy.deepcopy(payload),
        }
        selected_items.append(item)
        if payload.get('ocr_failed'):
            failed_items.append({
                'region_id': region_id,
                'title': region.get('title') or region_id,
                'error': payload.get('recognition_error') or payload.get('recognition_reason') or 'model_recognition_failed',
            })
            continue
        if payload.get('recognition') == 'gray':
            gray_items.append({
                'region_id': region_id,
                'title': region.get('title') or region_id,
                'recognized_text': payload.get('recognized_text') or '',
                'recognition_reason': payload.get('recognition_reason') or '',
                'model_predictions': copy.deepcopy(payload.get('model_predictions') or {}),
                'selected_model': payload.get('selected_model') or '',
                'default_target_text': payload.get('suggested_target_text') or payload.get('recognized_text') or '',
                'context_weighted_scores': copy.deepcopy(payload.get('context_weighted_scores') or {}),
            })

    return {
        'mode': mode,
        'selection_source': selection_source,
        'selected_regions': selected_items,
        'selected_region_ids': [str(region.get('region_id') or '').strip() for region in selected_regions],
        'selected_count': len(selected_regions),
        'gray_regions': gray_items,
        'gray_count': len(gray_items),
        'failed_regions': failed_items,
        'failed_count': len(failed_items),
        'next_region_id': next_region_id,
    }


def _normalize_gray_resolutions(gray_resolutions: Any) -> Dict[str, Dict[str, str]]:
    normalized: Dict[str, Dict[str, str]] = {}
    if not isinstance(gray_resolutions, list):
        return normalized
    for item in gray_resolutions:
        if not isinstance(item, dict):
            continue
        region_id = str(item.get('region_id') or '').strip()
        if not region_id:
            continue
        choice_type = str(item.get('choice_type') or item.get('source') or 'default').strip().lower()
        if choice_type not in ('default', 'gemini', 'qwen', 'manual'):
            choice_type = 'default'
        target_text = _normalize_text(item.get('target_text') or item.get('value') or '', preserve_newlines=True)
        normalized[region_id] = {
            'choice_type': choice_type,
            'target_text': target_text,
        }
    return normalized


def _resolve_gray_target_text(
    recognition_payload: Dict[str, Any],
    mode: str,
    gray_resolution: Optional[Dict[str, str]],
) -> Tuple[str, str]:
    model_predictions = recognition_payload.get('model_predictions') if isinstance(recognition_payload.get('model_predictions'), dict) else {}
    default_text = _normalize_text(recognition_payload.get('recognized_text') or '', preserve_newlines=True)
    if mode == _AUTO_MODE_FULL:
        if not default_text:
            raise ValueError('gray_region_missing_default_target')
        return default_text, 'default'

    if not isinstance(gray_resolution, dict):
        raise ValueError('gray_region_choice_required')

    choice_type = str(gray_resolution.get('choice_type') or 'default').strip().lower()
    manual_text = _normalize_text(gray_resolution.get('target_text') or '', preserve_newlines=True)
    if choice_type == 'manual':
        if not manual_text:
            raise ValueError('gray_region_manual_target_required')
        return manual_text, 'manual'
    if choice_type in ('gemini', 'qwen'):
        chosen_text = _normalize_text(((model_predictions.get(choice_type) or {}).get('text')) or '', preserve_newlines=True)
        if chosen_text:
            return chosen_text, choice_type
    if default_text:
        return default_text, 'default'
    raise ValueError('gray_region_missing_default_target')


def _build_white_region_instruction(target_text: str) -> str:
    return (
        f'只修改这个区域，其他不要变。把这里的目标文字明确改为“{target_text}”（说明：原区域里的字迹可能不清晰、潦草、甚至不成字；无论原笔迹是什么样，都必须将已有笔迹完全替换为此指定文字），'
        '使用清晰、规整、标准的印刷体呈现，字形和排布尽量稳定可辨。'
    )


def _build_gray_region_instruction(target_text: str, preferred: bool = False) -> str:
    style_hint = (
        '使用较为规范、工整、易辨认的手写体，仍保留自然手写笔触，不要改成印刷排版。'
        if preferred
        else '使用较为明显、自然的手写体，保留真实书写感和局部版面关系，不要改成印刷排版。'
    )
    return (
        f'只修改这个区域，其他不要变。把这里的目标文字改为“{target_text}”（说明：原区域里的字迹可能不清晰、潦草、甚至不成字；无论原笔迹是什么样，都必须将已有笔迹完全替换为此指定文字），'
        f'{style_hint}'
    )


def _build_black_region_instruction() -> str:
    return (
        '只修改这个区域，其他不要变。必须以提供的原始草图局部作为唯一的笔迹来源，'
        '原样保留其中手写笔迹、线条、符号、轮廓等痕迹；除这些痕迹外，背景、底纹、留白、'
        '边缘衔接、颜色和非手写结构都与当前复现图局部保持一致。'
    )


def _build_auto_iteration_plan(
    region: Dict[str, Any],
    recognition_payload: Dict[str, Any],
    mode: str,
    gray_resolution: Optional[Dict[str, str]],
    original_crop_b64: str,
) -> Dict[str, Any]:
    recognition = str(recognition_payload.get('recognition') or '').strip().lower()
    if recognition == 'white':
        target_text = _normalize_text(recognition_payload.get('recognized_text') or '', preserve_newlines=True)
        if not target_text:
            raise ValueError('white_region_missing_target')
        return {
            'instruction_text': _build_white_region_instruction(target_text),
            'target_text': target_text,
            'reason': 'white_region_standard_print',
            'reference_image_b64': '',
            'reference_image_mime': 'image/png',
            'reference_image_role': 'reference',
            'resolution_source': 'default',
        }
    if recognition == 'gray':
        target_text, resolution_source = _resolve_gray_target_text(recognition_payload, mode, gray_resolution)
        preferred_gray = str(recognition_payload.get('gray_quality_hint') or '').strip().lower() == 'preferred'
        return {
            'instruction_text': _build_gray_region_instruction(target_text, preferred=preferred_gray),
            'target_text': target_text,
            'reason': f'gray_region_{"preferred_" if preferred_gray else ""}{resolution_source}',
            'reference_image_b64': '',
            'reference_image_mime': 'image/png',
            'reference_image_role': 'reference',
            'resolution_source': resolution_source,
        }
    if recognition == 'black':
        if not original_crop_b64:
            raise ValueError('black_region_missing_original_crop')
        return {
            'instruction_text': _build_black_region_instruction(),
            'target_text': '',
            'reason': 'black_region_preserve_sketch_trace',
            'reference_image_b64': original_crop_b64,
            'reference_image_mime': 'image/png',
            'reference_image_role': 'original_sketch_crop',
            'resolution_source': 'sketch_crop',
        }
    raise ValueError(f'unsupported_recognition={recognition or "unknown"}')


def _build_round_summary(
    start_region_id: str,
    next_region_id: str,
    selected_regions: List[Dict[str, Any]],
    recognition_map: Dict[str, Dict[str, Any]],
    decision_map: Dict[str, Dict[str, Any]],
    started_at: str,
    finished_at: str,
    mode: str,
    selection_source: str,
) -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for region in selected_regions:
        region_id = str(region.get('region_id') or '').strip()
        recognition = recognition_map.get(region_id, {})
        decision = decision_map.get(region_id, {})
        recognized_text = recognition.get('recognized_text') or ''
        recognition_type = recognition.get('recognition') or ''
        items.append({
            'region_id': region_id,
            'title': region.get('title') or region_id,
            'rank': int(region.get('rank') or 0),
            'recognition': recognition_type,
            'recognized_text': recognized_text,
            'recognition_reason': recognition.get('recognition_reason') or '',
            'recognition_error': recognition.get('recognition_error') or '',
            'model_predictions': copy.deepcopy(recognition.get('model_predictions') or {}),
            'disagreement_adjudication': copy.deepcopy(recognition.get('disagreement_adjudication') or {}),
            'gray_quality_hint': recognition.get('gray_quality_hint') or '',
            'selected_model': recognition.get('selected_model') or '',
            'target_text': decision.get('target_text') or (recognized_text if recognition_type != 'black' else ''),
            'resolution_source': decision.get('resolution_source') or '',
            'decision': decision.get('decision') or 'selected',
            'decision_reason': decision.get('reason') or '',
            'instruction_text': decision.get('instruction_text') or '',
        })
    iterated_ids = [item['region_id'] for item in items if item.get('decision') == 'iterated']
    skipped_ids = [item['region_id'] for item in items if item.get('decision') == 'skipped']
    failed_ids = [item['region_id'] for item in items if item.get('decision') == 'failed']
    for item in items:
        rid = item['region_id']
        rec = recognition_map.get(rid, {})
        if rec.get('ocr_failed') and rid not in failed_ids:
            failed_ids.append(rid)
    return {
        'version': _AUTO_ITERATION_VERSION,
        'mode': mode,
        'selection_source': selection_source,
        'started_at': started_at,
        'finished_at': finished_at,
        'start_region_id': start_region_id,
        'next_region_id': next_region_id,
        'selected_region_ids': [item['region_id'] for item in items],
        'iterated_region_ids': iterated_ids,
        'skipped_region_ids': skipped_ids,
        'failed_region_ids': failed_ids,
        'selected_regions': items,
        'selected_count': len(items),
        'iterated_count': len(iterated_ids),
        'skipped_count': len(skipped_ids),
        'failed_count': len(failed_ids),
    }


def _update_overlay_auto_iteration_state(
    paths: Dict[str, str],
    manifest: Dict[str, Any],
    r_layer: Dict[str, Any],
    unit_id: str,
    recognition_map: Dict[str, Dict[str, Any]],
    selected_regions: List[Dict[str, Any]],
    decision_map: Dict[str, Dict[str, Any]],
    start_region_id: str,
    next_region_id: str,
    round_started_at: str,
    mode: str,
    selection_source: str,
    lite_auto_iteration_last: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    selected_order = [str(region.get('region_id') or '').strip() for region in selected_regions if str(region.get('region_id') or '').strip()]
    finished_at = _now_iso()
    lite_patch = lite_auto_iteration_last if isinstance(lite_auto_iteration_last, dict) and lite_auto_iteration_last else None

    def _patch_overlay(current: Dict[str, Any]) -> Dict[str, Any]:
        row = {
            **current,
            'regions': _merge_round_regions(current.get('regions') or [], recognition_map, selected_order, decision_map),
            'auto_iteration': {
                **(current.get('auto_iteration') or {}),
                'version': _AUTO_ITERATION_VERSION,
                'mode': mode,
                'selection_source': selection_source,
                'next_region_id': next_region_id,
                'last_completed_at': finished_at,
                'last_round': _build_round_summary(start_region_id, next_region_id, selected_regions, recognition_map, decision_map, round_started_at, finished_at, mode, selection_source),
            },
            'updated_at': finished_at,
        }
        if lite_patch:
            row['lite_auto_iteration_last'] = lite_patch
        return row

    return _update_overlay_item(paths, manifest, r_layer, unit_id, _patch_overlay)


def run_ci_apply_lite_bundle_to_reproduction(
    task_id: str,
    username: str,
    analysis_id: str,
    unit_id: str,
    image_quality: str = 'normal',
    iter_context_updates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """根据已保存的轻量识字 JSON，对当前 R 层复现图执行局部贴补（与全自动迭代贴补逻辑一致）。"""
    from app_chat.continuous_image_service import _set_reproduction_iterating  # noqa: PLC0415
    from app_chat.ci.orchestrator import _load_existing_layer

    decision_map: Dict[str, Dict[str, Any]] = {}
    recognition_map: Dict[str, Dict[str, Any]] = {}
    selected_regions: List[Dict[str, Any]] = []
    round_started_at = _now_iso()
    mode_apply = _AUTO_MODE_FULL

    try:
        _update_task(task_id, current_item=0, total_items=1, current_section=SECTION_PREPARING, completed=False, error='')
        paths, manifest, r_layer, r_item, overlay_item, repro_abs = _load_ci_context(username, analysis_id, unit_id)
        current_item = copy.deepcopy(r_item)

        if isinstance(iter_context_updates, dict) and iter_context_updates:
            current_item = _update_single_r_layer_item(
                paths,
                unit_id,
                lambda item: {
                    **item,
                    'iter_context': _normalize_reproduction_iter_context(item.get('iter_context'), iter_context_updates),
                    'updated_at': _now_iso(),
                },
            )
            r_layer = _load_existing_layer(paths['r_layer']) or r_layer

        bundle_path = os.path.join(paths['root'], _D_REGION_AUDIT_SUBDIR, f'd_region_lite_recognition_{unit_id}.json')
        if not os.path.isfile(bundle_path):
            raise ValueError('未找到轻量识字结果文件，请先运行「全自动-直接执行&平衡效率和质量」')
        with open(bundle_path, 'r', encoding='utf-8') as handle:
            bundle = json.load(handle)
        regions_saved = bundle.get('regions') if isinstance(bundle.get('regions'), list) else []
        recognition_map = {
            str((item or {}).get('region_id') or '').strip(): copy.deepcopy((item or {}).get('payload') or {})
            for item in regions_saved
            if str((item or {}).get('region_id') or '').strip()
        }
        overlay_regions = overlay_item.get('regions') if isinstance(overlay_item.get('regions'), list) else []
        region_by_id = {
            str((r or {}).get('region_id') or '').strip(): r
            for r in overlay_regions
            if isinstance(r, dict) and str((r or {}).get('region_id') or '').strip()
        }
        selected_regions = []
        for item in regions_saved:
            rid = str((item or {}).get('region_id') or '').strip()
            if rid and rid in region_by_id:
                selected_regions.append(region_by_id[rid])
        if not selected_regions:
            raise ValueError('轻量结果中的 region_id 与当前覆盖层不匹配')

        notebook_ctx = _build_auto_iteration_notebook_context(username, manifest)
        recognition_context = _build_auto_iteration_recognition_context(notebook_ctx, use_recognition_context=True)
        asset_abs_path = _resolve_unit_asset_abs_path(paths, manifest, unit_id)
        unit = _build_unit_for_auto_iteration(username, analysis_id, manifest, unit_id, asset_abs_path)
        current_context = _normalize_reproduction_iter_context(current_item.get('iter_context'))
        tmp_dir = os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME, 'ocr_apply_lite')
        os.makedirs(tmp_dir, exist_ok=True)
        gray_resolution_map: Dict[str, Any] = {}

        plan_results: List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], str]] = []
        _update_task(task_id, current_item=0, total_items=len(selected_regions), current_section=SECTION_PLANNING, completed=False, error='')
        for index, region in enumerate(selected_regions, start=1):
            region_id = str(region.get('region_id') or '').strip()
            recognition_payload = recognition_map.get(region_id, {})
            if recognition_payload.get('ocr_failed'):
                decision_map[region_id] = {
                    'decision': 'failed',
                    'reason': recognition_payload.get('recognition_error') or recognition_payload.get('recognition_reason') or 'model_recognition_failed',
                    'instruction_text': '',
                    'target_text': '',
                    'resolution_source': '',
                }
                _update_task(task_id, current_item=index, total_items=len(selected_regions), current_section=SECTION_PLANNING)
                continue

            normalized_bbox = _normalize_region_bbox(region)
            if not normalized_bbox:
                decision_map[region_id] = {
                    'decision': 'failed',
                    'reason': 'invalid_region_bbox',
                    'instruction_text': '',
                    'target_text': '',
                    'resolution_source': '',
                }
                _update_task(task_id, current_item=index, total_items=len(selected_regions), current_section=SECTION_PLANNING)
                continue

            original_crop_b64 = ''
            if asset_abs_path and os.path.isfile(asset_abs_path):
                try:
                    _original_crop_image, original_crop_b64 = _crop_image_by_region(asset_abs_path, normalized_bbox)
                except Exception:
                    original_crop_b64 = ''

            try:
                plan = _build_auto_iteration_plan(
                    region,
                    recognition_payload,
                    mode_apply,
                    gray_resolution_map.get(region_id),
                    original_crop_b64,
                )
                plan_results.append((region, recognition_payload, plan, original_crop_b64))
            except Exception as error:
                decision_map[region_id] = {
                    'decision': 'failed',
                    'reason': _truncate_text(str(error), 160),
                    'instruction_text': '',
                    'target_text': '',
                    'resolution_source': '',
                }
            _update_task(task_id, current_item=index, total_items=len(selected_regions), current_section=SECTION_PLANNING)

        successful_candidates: List[Dict[str, Any]] = []
        if plan_results:
            rollback_stack = current_item.get('rollback_stack')
            try:
                if current_item.get('status') == 'ready':
                    rollback_stack = _append_reproduction_rollback_snapshot(paths, current_item, reason='apply_lite_bundle')
                else:
                    rollback_stack = current_item.get('rollback_stack')
            except Exception as snapshot_error:
                print(f'[ci_auto_iter] apply_lite 回滚快照失败({unit_id}): {snapshot_error}')
                rollback_stack = current_item.get('rollback_stack')

            candidate_jobs = []
            accepted_bboxes: List[Dict[str, float]] = []
            with ThreadPoolExecutor(max_workers=min(_AUTO_MAX_BATCH_SIZE, len(plan_results))) as executor:
                _update_task(task_id, current_item=0, total_items=len(plan_results), current_section=SECTION_ITERATING, completed=False, error='')
                for region, _recognition_payload, plan, _original_crop_b64 in plan_results:
                    region_id = str(region.get('region_id') or '').strip()
                    region_bbox = _normalize_region_bbox(region)
                    overlap_conflict = bool(region_bbox) and any(_bbox_overlap_ratio(region_bbox, existing_bbox) > 0.05 for existing_bbox in accepted_bboxes)
                    if not region_bbox or overlap_conflict:
                        decision_map[region_id] = {
                            'decision': 'failed',
                            'reason': 'bbox_overlap_conflict' if overlap_conflict else 'invalid_region_bbox',
                            'instruction_text': plan.get('instruction_text') or '',
                            'target_text': plan.get('target_text') or '',
                            'resolution_source': plan.get('resolution_source') or '',
                        }
                        continue
                    accepted_bboxes.append(region_bbox)
                    candidate_jobs.append((region, plan, executor.submit(
                        _generate_single_region_candidate,
                        username,
                        unit,
                        repro_abs,
                        current_item,
                        region,
                        plan.get('instruction_text') or '',
                        image_quality,
                        os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME),
                        plan.get('reference_image_b64') or None,
                        plan.get('reference_image_mime') or 'image/png',
                        plan.get('reference_image_role') or 'reference',
                    )))

                completed_jobs = 0
                for region, plan, future in candidate_jobs:
                    region_id = str(region.get('region_id') or '').strip()
                    try:
                        candidate = future.result()
                        successful_candidates.append(candidate)
                        decision_map[region_id] = {
                            'decision': 'iterated',
                            'reason': plan.get('reason') or 'lite_bundle_applied',
                            'instruction_text': plan.get('instruction_text') or '',
                            'target_text': plan.get('target_text') or '',
                            'resolution_source': plan.get('resolution_source') or '',
                        }
                    except Exception as error:
                        traceback.print_exc()
                        decision_map[region_id] = {
                            'decision': 'failed',
                            'reason': _truncate_text(str(error), 160),
                            'instruction_text': plan.get('instruction_text') or '',
                            'target_text': plan.get('target_text') or '',
                            'resolution_source': plan.get('resolution_source') or '',
                        }
                    completed_jobs += 1
                    _update_task(task_id, current_item=completed_jobs, total_items=len(plan_results), current_section=SECTION_ITERATING)

            if successful_candidates:
                _apply_candidate_patches(repro_abs, successful_candidates)
                updated_item = _update_single_r_layer_item(
                    paths,
                    unit_id,
                    lambda item: {
                        **item,
                        'rollback_stack': rollback_stack,
                        'status': 'ready',
                        'error': '',
                        'iter_context': copy.deepcopy(current_context),
                        'last_generated_context': copy.deepcopy(current_context),
                        'updated_at': _now_iso(),
                    },
                )
                current_item = updated_item
                r_layer = _load_existing_layer(paths['r_layer']) or r_layer

        next_region_id = ''
        updated_overlay_item = _update_overlay_auto_iteration_state(
            paths,
            manifest,
            r_layer,
            unit_id,
            recognition_map,
            selected_regions,
            decision_map,
            str(selected_regions[0].get('region_id') or '').strip() if selected_regions else '',
            next_region_id,
            round_started_at,
            'apply_lite_bundle',
            'lite_bundle_file',
        )

        _update_task(task_id, current_section=SECTION_COMPLETED, current_item=1, total_items=1, completed=True, error='')
        return {
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'mode': 'apply_lite_bundle',
            'selected_region_ids': [str(r.get('region_id') or '').strip() for r in selected_regions],
            'iterated_region_ids': [rid for rid, pl in decision_map.items() if pl.get('decision') == 'iterated'],
            'failed_region_ids': [rid for rid, pl in decision_map.items() if pl.get('decision') == 'failed'],
            'r_item': _sanitize_reproduction_item_for_response(current_item),
            'overlay_item': updated_overlay_item,
        }
    except Exception:
        _update_task(task_id, current_section=SECTION_FAILED, current_item=1, total_items=1, completed=True, error='apply_lite_failed')
        raise
    finally:
        _set_reproduction_iterating(username, analysis_id, unit_id, False)
        try:
            if 'paths' in locals():
                shutil.rmtree(os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME), ignore_errors=True)
        except Exception:
            pass


def preview_ci_auto_iteration_round(
    username: str,
    analysis_id: str,
    unit_id: str,
    selected_region_ids: Optional[List[str]] = None,
    start_region_id: str = '',
    continue_from_cursor: bool = True,
    mode: str = _AUTO_MODE_SEMI,
    sketch_preprocess: Optional[bool] = None,
    use_recognition_context: bool = True,
) -> Dict[str, Any]:
    notebook_ctx: Dict[str, Any] = {}
    recognition_map: Dict[str, Dict[str, Any]] = {}
    selected_regions: List[Dict[str, Any]] = []
    next_region_id = ''
    selection_source = _AUTO_SELECTION_SOURCE_CURSOR
    try:
        mode = str(mode or _AUTO_MODE_SEMI).strip().lower()
        if mode not in (_AUTO_MODE_SEMI, _AUTO_MODE_FULL, _AUTO_MODE_FULL_LITE):
            mode = _AUTO_MODE_SEMI
        manual_cap = _AUTO_MAX_BATCH_SIZE_LITE if mode == _AUTO_MODE_FULL_LITE else _AUTO_MAX_BATCH_SIZE
        paths, manifest, _r_layer, _r_item, overlay_item, _repro_abs = _load_ci_context(username, analysis_id, unit_id)
        coarse_layout = bool((overlay_item or {}).get('ci_dmt_coarse_layout'))
        selected_regions, next_region_id, _start_index, selection_source = _select_auto_iteration_regions(
            overlay_item,
            start_region_id=start_region_id,
            continue_from_cursor=continue_from_cursor,
            selected_region_ids=selected_region_ids,
            max_manual_batch=manual_cap,
        )
        if mode == _AUTO_MODE_SEMI and selection_source != _AUTO_SELECTION_SOURCE_MANUAL:
            raise ValueError(f'半自动模式请先手动选择 1-{_AUTO_MAX_BATCH_SIZE} 个 D 版面')
        if mode == _AUTO_MODE_FULL_LITE and selection_source != _AUTO_SELECTION_SOURCE_MANUAL:
            raise ValueError(f'轻量全自动请先手动选择 1-{_AUTO_MAX_BATCH_SIZE_LITE} 个 D 版面')
        if not selected_regions:
            raise ValueError('当前没有可用的 D 版面可用于自动迭代')

        notebook_ctx = _build_auto_iteration_notebook_context(username, manifest)
        recognition_context = _build_auto_iteration_recognition_context(
            notebook_ctx,
            use_recognition_context=bool(use_recognition_context),
        )
        asset_abs_path = _resolve_unit_asset_abs_path(paths, manifest, unit_id)
        tmp_dir = os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME, 'preview')
        os.makedirs(tmp_dir, exist_ok=True)
        for region in selected_regions:
            region_id = str(region.get('region_id') or '').strip()
            if mode == _AUTO_MODE_FULL_LITE:
                rec_payload = _classify_region_recognition_qwen_lite(
                    region,
                    asset_abs_path,
                    tmp_dir,
                    recognition_context,
                    sketch_preprocess=sketch_preprocess,
                    coarse_layout=coarse_layout,
                )
            else:
                rec_payload = _classify_region_recognition(
                    region, asset_abs_path, tmp_dir, recognition_context, sketch_preprocess=sketch_preprocess,
                )
                rec_payload = _attach_disagreement_adjudication_for_probe(
                    payload=rec_payload,
                    region=region,
                    asset_abs_path=asset_abs_path,
                    tmp_dir=tmp_dir,
                    recognition_context=recognition_context,
                    sketch_preprocess=sketch_preprocess,
                )
            recognition_map[region_id] = rec_payload
            append_d_region_recognition_audit(
                paths,
                username=username,
                analysis_id=analysis_id,
                unit_id=unit_id,
                region_id=region_id,
                source='auto_iterate_preview',
                recognition_payload=rec_payload,
            )

        preview = _build_auto_iteration_preview(selected_regions, recognition_map, next_region_id, mode, selection_source)
        preview.update({
            'analysis_id': analysis_id,
            'unit_id': unit_id,
        })
        return preview
    finally:
        try:
            if 'paths' in locals():
                shutil.rmtree(os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME), ignore_errors=True)
        except Exception:
            pass


def run_ci_auto_iteration_round(
    task_id: str,
    username: str,
    analysis_id: str,
    unit_id: str,
    start_region_id: str = '',
    continue_from_cursor: bool = True,
    image_quality: str = 'normal',
    iter_context_updates: Optional[Dict[str, Any]] = None,
    mode: str = _AUTO_MODE_FULL,
    selected_region_ids: Optional[List[str]] = None,
    gray_resolutions: Optional[List[Dict[str, Any]]] = None,
    sketch_preprocess: Optional[bool] = None,
    use_recognition_context: bool = True,
) -> Dict[str, Any]:
    from app_chat.ci.orchestrator import _load_existing_layer

    decision_map: Dict[str, Dict[str, Any]] = {}
    recognition_map: Dict[str, Dict[str, Any]] = {}
    selected_regions: List[Dict[str, Any]] = []
    next_region_id = ''
    resume_region_id = ''
    selection_source = _AUTO_SELECTION_SOURCE_CURSOR
    round_started_at = _now_iso()
    mode = str(mode or _AUTO_MODE_FULL).strip().lower()
    if mode not in (_AUTO_MODE_SEMI, _AUTO_MODE_FULL, _AUTO_MODE_FULL_LITE):
        mode = _AUTO_MODE_FULL
    manual_cap = _AUTO_MAX_BATCH_SIZE_LITE if mode == _AUTO_MODE_FULL_LITE else _AUTO_MAX_BATCH_SIZE
    gray_resolution_map = _normalize_gray_resolutions(gray_resolutions)

    try:
        _update_task(task_id, current_item=0, total_items=1, current_section=SECTION_PREPARING, completed=False, error='')
        paths, manifest, r_layer, r_item, overlay_item, repro_abs = _load_ci_context(username, analysis_id, unit_id)
        coarse_layout = bool((overlay_item or {}).get('ci_dmt_coarse_layout'))
        current_item = copy.deepcopy(r_item)

        if isinstance(iter_context_updates, dict) and iter_context_updates:
            current_item = _update_single_r_layer_item(
                paths,
                unit_id,
                lambda item: {
                    **item,
                    'iter_context': _normalize_reproduction_iter_context(item.get('iter_context'), iter_context_updates),
                    'updated_at': _now_iso(),
                },
            )
            r_layer = _load_existing_layer(paths['r_layer']) or r_layer

        selected_regions, next_region_id, _start_index, selection_source = _select_auto_iteration_regions(
            overlay_item,
            start_region_id=start_region_id,
            continue_from_cursor=continue_from_cursor,
            selected_region_ids=selected_region_ids,
            max_manual_batch=manual_cap,
        )
        if mode == _AUTO_MODE_SEMI and selection_source != _AUTO_SELECTION_SOURCE_MANUAL:
            raise ValueError(f'半自动模式请先手动选择 1-{_AUTO_MAX_BATCH_SIZE} 个 D 版面')
        if mode == _AUTO_MODE_FULL_LITE and selection_source != _AUTO_SELECTION_SOURCE_MANUAL:
            raise ValueError(f'轻量全自动请先手动选择 1-{_AUTO_MAX_BATCH_SIZE_LITE} 个 D 版面')
        if not selected_regions:
            raise ValueError('当前没有可继续的 D 版面可用于自动迭代')

        notebook_ctx = _build_auto_iteration_notebook_context(username, manifest)
        recognition_context = _build_auto_iteration_recognition_context(
            notebook_ctx,
            use_recognition_context=bool(use_recognition_context),
        )
        asset_abs_path = _resolve_unit_asset_abs_path(paths, manifest, unit_id)
        unit = _build_unit_for_auto_iteration(username, analysis_id, manifest, unit_id, asset_abs_path)
        current_context = _normalize_reproduction_iter_context(current_item.get('iter_context'))
        tmp_dir = os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME, 'ocr')
        os.makedirs(tmp_dir, exist_ok=True)

        if mode == _AUTO_MODE_FULL_LITE:

            def _lite_one(reg: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
                rid = str(reg.get('region_id') or '').strip()
                try:
                    pay = _classify_region_recognition_qwen_lite(
                        reg,
                        asset_abs_path,
                        tmp_dir,
                        recognition_context,
                        sketch_preprocess=sketch_preprocess,
                        coarse_layout=coarse_layout,
                    )
                    return rid, pay
                except Exception as exc:
                    traceback.print_exc()
                    return rid, _build_auto_recognition_payload(
                        '',
                        '',
                        'lite_pipeline_failed',
                        recognition_error=_truncate_text(str(exc), 240),
                        ocr_failed=True,
                        recognition_source='sketch_snippet_qwen_lite_v1',
                    )

            recognition_map = {}
            workers = min(2, max(1, len(selected_regions)))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [executor.submit(_lite_one, region) for region in selected_regions]
                for idx, fut in enumerate(futures, start=1):
                    region_id, rec_payload = fut.result()
                    recognition_map[region_id] = rec_payload
                    append_d_region_recognition_audit(
                        paths,
                        username=username,
                        analysis_id=analysis_id,
                        unit_id=unit_id,
                        region_id=region_id,
                        source='auto_iterate_lite_round',
                        recognition_payload=rec_payload,
                    )
                    _update_task(task_id, current_item=idx, total_items=len(selected_regions), current_section=SECTION_RECOGNIZING)

            bundle_rel = _save_ci_lite_recognition_bundle(
                paths, analysis_id, unit_id, recognition_map, selected_regions, mode,
            )
            finished_at = _now_iso()
            lite_meta = {
                'version': _AUTO_ITERATION_VERSION,
                'mode': _AUTO_MODE_FULL_LITE,
                'finished_at': finished_at,
                'bundle_rel_path': bundle_rel,
                'selected_region_ids': [str(r.get('region_id') or '').strip() for r in selected_regions],
                'selection_source': selection_source,
            }
            updated_overlay_item = _update_overlay_auto_iteration_state(
                paths,
                manifest,
                r_layer,
                unit_id,
                recognition_map,
                selected_regions,
                {},
                '',
                next_region_id,
                round_started_at,
                _AUTO_MODE_FULL_LITE,
                selection_source,
                lite_auto_iteration_last=lite_meta,
            )
            _update_task(task_id, current_section=SECTION_COMPLETED, current_item=1, total_items=1, completed=True, error='')
            return {
                'analysis_id': analysis_id,
                'unit_id': unit_id,
                'mode': mode,
                'selection_source': selection_source,
                'selected_region_ids': [str(r.get('region_id') or '').strip() for r in selected_regions],
                'lite_bundle_rel_path': bundle_rel,
                'recognition_region_count': len(recognition_map),
                'overlay_item': updated_overlay_item,
                'r_item': _sanitize_reproduction_item_for_response(current_item),
            }

        _update_task(task_id, current_item=0, total_items=len(selected_regions), current_section=SECTION_RECOGNIZING, completed=False, error='')
        for index, region in enumerate(selected_regions, start=1):
            region_id = str(region.get('region_id') or '').strip()
            rec_payload = _classify_region_recognition(
                region, asset_abs_path, tmp_dir, recognition_context, sketch_preprocess=sketch_preprocess,
            )
            rec_payload = _attach_disagreement_adjudication_for_probe(
                payload=rec_payload,
                region=region,
                asset_abs_path=asset_abs_path,
                tmp_dir=tmp_dir,
                recognition_context=recognition_context,
                sketch_preprocess=sketch_preprocess,
            )
            recognition_map[region_id] = rec_payload
            append_d_region_recognition_audit(
                paths,
                username=username,
                analysis_id=analysis_id,
                unit_id=unit_id,
                region_id=region_id,
                source='auto_iterate_round',
                recognition_payload=rec_payload,
            )
            _update_task(task_id, current_item=index, total_items=len(selected_regions), current_section=SECTION_RECOGNIZING)

        plan_results: List[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], str]] = []
        _update_task(task_id, current_item=0, total_items=len(selected_regions), current_section=SECTION_PLANNING, completed=False, error='')
        for index, region in enumerate(selected_regions, start=1):
            region_id = str(region.get('region_id') or '').strip()
            recognition_payload = recognition_map.get(region_id, {})
            if recognition_payload.get('ocr_failed'):
                decision_map[region_id] = {
                    'decision': 'failed',
                    'reason': recognition_payload.get('recognition_error') or recognition_payload.get('recognition_reason') or 'model_recognition_failed',
                    'instruction_text': '',
                    'target_text': '',
                    'resolution_source': '',
                }
                _update_task(task_id, current_item=index, total_items=len(selected_regions), current_section=SECTION_PLANNING)
                continue

            normalized_bbox = _normalize_region_bbox(region)
            if not normalized_bbox:
                decision_map[region_id] = {
                    'decision': 'failed',
                    'reason': 'invalid_region_bbox',
                    'instruction_text': '',
                    'target_text': '',
                    'resolution_source': '',
                }
                _update_task(task_id, current_item=index, total_items=len(selected_regions), current_section=SECTION_PLANNING)
                continue

            original_crop_b64 = ''
            if asset_abs_path and os.path.isfile(asset_abs_path):
                try:
                    _original_crop_image, original_crop_b64 = _crop_image_by_region(asset_abs_path, normalized_bbox)
                except Exception:
                    original_crop_b64 = ''

            try:
                plan = _build_auto_iteration_plan(
                    region,
                    recognition_payload,
                    mode,
                    gray_resolution_map.get(region_id),
                    original_crop_b64,
                )
                plan_results.append((region, recognition_payload, plan, original_crop_b64))
            except Exception as error:
                decision_map[region_id] = {
                    'decision': 'failed',
                    'reason': _truncate_text(str(error), 160),
                    'instruction_text': '',
                    'target_text': '',
                    'resolution_source': '',
                }
            _update_task(task_id, current_item=index, total_items=len(selected_regions), current_section=SECTION_PLANNING)

        successful_candidates: List[Dict[str, Any]] = []
        if plan_results:
            rollback_stack = current_item.get('rollback_stack')
            try:
                if current_item.get('status') == 'ready':
                    rollback_stack = _append_reproduction_rollback_snapshot(paths, current_item, reason='auto_iterate_round')
                else:
                    rollback_stack = current_item.get('rollback_stack')
            except Exception as snapshot_error:
                print(f'[ci_auto_iter] 记录自动迭代回滚快照失败({unit_id}): {snapshot_error}')
                rollback_stack = current_item.get('rollback_stack')

            candidate_jobs = []
            accepted_bboxes: List[Dict[str, float]] = []
            with ThreadPoolExecutor(max_workers=min(_AUTO_MAX_BATCH_SIZE, len(plan_results))) as executor:
                _update_task(task_id, current_item=0, total_items=len(plan_results), current_section=SECTION_ITERATING, completed=False, error='')
                for region, _recognition_payload, plan, _original_crop_b64 in plan_results:
                    region_id = str(region.get('region_id') or '').strip()
                    region_bbox = _normalize_region_bbox(region)
                    overlap_conflict = bool(region_bbox) and any(_bbox_overlap_ratio(region_bbox, existing_bbox) > 0.05 for existing_bbox in accepted_bboxes)
                    if not region_bbox or overlap_conflict:
                        decision_map[region_id] = {
                            'decision': 'failed',
                            'reason': 'bbox_overlap_conflict' if overlap_conflict else 'invalid_region_bbox',
                            'instruction_text': plan.get('instruction_text') or '',
                            'target_text': plan.get('target_text') or '',
                            'resolution_source': plan.get('resolution_source') or '',
                        }
                        continue
                    accepted_bboxes.append(region_bbox)
                    candidate_jobs.append((region, plan, executor.submit(
                        _generate_single_region_candidate,
                        username,
                        unit,
                        repro_abs,
                        current_item,
                        region,
                        plan.get('instruction_text') or '',
                        image_quality,
                        os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME),
                        plan.get('reference_image_b64') or None,
                        plan.get('reference_image_mime') or 'image/png',
                        plan.get('reference_image_role') or 'reference',
                    )))

                completed_jobs = 0
                for region, plan, future in candidate_jobs:
                    region_id = str(region.get('region_id') or '').strip()
                    try:
                        candidate = future.result()
                        successful_candidates.append(candidate)
                        decision_map[region_id] = {
                            'decision': 'iterated',
                            'reason': plan.get('reason') or 'auto_iteration_applied',
                            'instruction_text': plan.get('instruction_text') or '',
                            'target_text': plan.get('target_text') or '',
                            'resolution_source': plan.get('resolution_source') or '',
                        }
                    except Exception as error:
                        traceback.print_exc()
                        decision_map[region_id] = {
                            'decision': 'failed',
                            'reason': _truncate_text(str(error), 160),
                            'instruction_text': plan.get('instruction_text') or '',
                            'target_text': plan.get('target_text') or '',
                            'resolution_source': plan.get('resolution_source') or '',
                        }
                    completed_jobs += 1
                    _update_task(task_id, current_item=completed_jobs, total_items=len(plan_results), current_section=SECTION_ITERATING)

            if successful_candidates:
                _apply_candidate_patches(repro_abs, successful_candidates)
                updated_item = _update_single_r_layer_item(
                    paths,
                    unit_id,
                    lambda item: {
                        **item,
                        'rollback_stack': rollback_stack,
                        'status': 'ready',
                        'error': '',
                        'iter_context': copy.deepcopy(current_context),
                        'last_generated_context': copy.deepcopy(current_context),
                        'updated_at': _now_iso(),
                    },
                )
                current_item = updated_item
                r_layer = _load_existing_layer(paths['r_layer']) or r_layer

        failed_region_ids = [
            str(region.get('region_id') or '').strip()
            for region in selected_regions
            if decision_map.get(str(region.get('region_id') or '').strip(), {}).get('decision') == 'failed'
        ]
        current_auto_iteration = overlay_item.get('auto_iteration') if isinstance(overlay_item.get('auto_iteration'), dict) else {}
        default_resume_region_id = next_region_id if selection_source == _AUTO_SELECTION_SOURCE_CURSOR else str(current_auto_iteration.get('next_region_id') or '').strip()
        resume_region_id = failed_region_ids[0] if failed_region_ids else default_resume_region_id

        updated_overlay_item = _update_overlay_auto_iteration_state(
            paths,
            manifest,
            r_layer,
            unit_id,
            recognition_map,
            selected_regions,
            decision_map,
            str(selected_regions[0].get('region_id') or '').strip() if selected_regions else '',
            resume_region_id,
            round_started_at,
            mode,
            selection_source,
        )

        result = {
            'analysis_id': analysis_id,
            'unit_id': unit_id,
            'mode': mode,
            'selection_source': selection_source,
            'selected_region_ids': [str(region.get('region_id') or '').strip() for region in selected_regions],
            'iterated_region_ids': [region_id for region_id, payload in decision_map.items() if payload.get('decision') == 'iterated'],
            'skipped_region_ids': [region_id for region_id, payload in decision_map.items() if payload.get('decision') == 'skipped'],
            'failed_region_ids': [region_id for region_id, payload in decision_map.items() if payload.get('decision') == 'failed'],
            'next_region_id': resume_region_id,
            'r_item': _sanitize_reproduction_item_for_response(current_item),
            'overlay_item': updated_overlay_item,
        }

        _update_task(task_id, current_section=SECTION_FINALIZING, current_item=1, total_items=1, completed=False, error='')
        _update_task(task_id, current_section=SECTION_COMPLETED, current_item=1, total_items=1, completed=True, error='')
        return result
    except Exception as error:
        traceback.print_exc()
        try:
            if 'paths' in locals() and 'manifest' in locals() and 'r_layer' in locals():
                _update_overlay_auto_iteration_state(
                    paths,
                    manifest,
                    r_layer,
                    unit_id,
                    recognition_map,
                    selected_regions,
                    decision_map,
                    str(selected_regions[0].get('region_id') or '').strip() if selected_regions else '',
                    next_region_id,
                    round_started_at,
                    mode,
                    selection_source,
                )
        except Exception:
            pass
        _update_task(task_id, current_section=SECTION_FAILED, current_item=1, total_items=1, completed=True, error=str(error))
        raise
    finally:
        _set_reproduction_iterating(username, analysis_id, unit_id, False)
        try:
            if 'paths' in locals():
                shutil.rmtree(os.path.join(paths['reproduction_dir'], _AUTO_OCR_TMP_DIRNAME), ignore_errors=True)
        except Exception:
            pass