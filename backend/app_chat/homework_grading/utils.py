import base64
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

SUBJECTS = {'math', 'chinese', 'english', 'unknown'}
SUBJECT_LABELS = {
    'math': '数学',
    'chinese': '语文',
    'english': '英语',
    'unknown': '未知学科',
}


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def source_document_sha256_from_artifact_path(path: str) -> str:
    """Read the source PDF identity stored beside a Pass1 artifact."""
    artifact_dir = os.path.dirname(os.path.abspath(str(path or '')))
    base_dir = os.path.dirname(artifact_dir)
    meta_path = os.path.join(base_dir, 'sample_meta.json')
    if not os.path.isfile(meta_path):
        return ''
    try:
        value = str(safe_json_load(meta_path).get('source_document_sha256') or '')
    except Exception:
        return ''
    normalized = value.replace(' ', '').strip().lower()
    return normalized if re.fullmatch(r'[0-9a-f]{64}', normalized) else ''


def windows_io_path(path: str) -> str:
    """仅文件系统访问使用扩展路径，业务路径及快照内容保持原样。"""
    path = os.fspath(path)
    if os.name != 'nt' or path.startswith('\\\\?\\'):
        return path
    absolute = os.path.abspath(path)
    if absolute.startswith('\\\\'):
        return '\\\\?\\UNC\\' + absolute[2:]
    return '\\\\?\\' + absolute


def safe_json_dump(path: str, data: Dict[str, Any]) -> None:
    path = windows_io_path(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def safe_json_load(path: str) -> Dict[str, Any]:
    path = windows_io_path(path)
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)


def image_to_data_uri(path: str) -> str:
    path = windows_io_path(path)
    with open(path, 'rb') as file:
        encoded = base64.b64encode(file.read()).decode('ascii')
    return f'data:image/png;base64,{encoded}'


_GEMINI_REVIEW_INLINE_MAX_MB = 3.0
_GEMINI_REVIEW_INLINE_TARGET_MB = 2.5


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.environ.get(name) or default)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def image_to_data_uri_for_gemini_review(path: str) -> str:
    """Gemini 批改自检用图。

    字形复核需要保留细小笔画。默认 3MB 以下发送原图，超过阈值才压缩；
    可用 HOMEWORK_PASS1_REVIEW_INLINE_MAX_MB / TARGET_MB 调整。
    """
    if path:
        path = windows_io_path(path)
    if not path or not os.path.isfile(path):
        raise ValueError(f'missing_image_file: {path}')

    from llm_langchain import util  # noqa: PLC0415

    file_size_mb = os.path.getsize(path) / (1024 * 1024)
    max_size_mb = _float_env('HOMEWORK_PASS1_REVIEW_INLINE_MAX_MB', _GEMINI_REVIEW_INLINE_MAX_MB, 0.5, 8.0)
    target_size_mb = _float_env(
        'HOMEWORK_PASS1_REVIEW_INLINE_TARGET_MB',
        min(_GEMINI_REVIEW_INLINE_TARGET_MB, max_size_mb),
        0.5,
        max_size_mb,
    )
    ext = os.path.splitext(path)[1].lower().lstrip('.')
    mime = {
        'jpg': 'jpeg',
        'jpeg': 'jpeg',
        'png': 'png',
        'webp': 'webp',
        'gif': 'gif',
        'bmp': 'bmp',
    }.get(ext, 'jpeg')
    b64 = util.encode_image(
        path,
        max_size_mb=max_size_mb,
        target_size_mb=target_size_mb,
    )
    if file_size_mb > max_size_mb:
        mime = 'jpeg'
    return f'data:image/{mime};base64,{b64}'


def page_filename(subject: str, sample_id: str, page_num: int) -> str:
    normalized = subject if subject in SUBJECTS else 'unknown'
    return f'{normalized}_{sample_id}_page{page_num}.png'


def parse_page_num(filename: str) -> int:
    match = re.search(r'_page(\d+)\.(?:png|json)$', filename)
    if not match:
        return 0
    return int(match.group(1))


def is_final_pass1_page_json(name: str) -> bool:
    if not name.endswith('.json'):
        return False
    if name.endswith('.detect.json') or name.endswith('.grade.json') or name.endswith('.review.json'):
        return False
    if '.error' in name or '.thinking' in name:
        return False
    return True


def sorted_json_pages(pass1_dir: str) -> List[str]:
    if not os.path.isdir(pass1_dir):
        return []
    return sorted(
        [os.path.join(pass1_dir, name) for name in os.listdir(pass1_dir) if is_final_pass1_page_json(name)],
        key=lambda path: (parse_page_num(os.path.basename(path)), os.path.basename(path)),
    )


def normalize_position(position: Any) -> List[float]:
    if isinstance(position, dict):
        keys = ('x_min', 'y_min', 'x_max', 'y_max')
        if not all(key in position for key in keys):
            return []
        position = [position[key] for key in keys]
    if not isinstance(position, list) or len(position) != 4:
        return []
    values = []
    for item in position:
        try:
            value = float(item)
        except (TypeError, ValueError):
            return []
        values.append(max(0.0, min(1000.0, value)))
    x1, y1, x2, y2 = values
    if x2 <= x1 or y2 <= y1:
        return []
    return [x1, y1, x2, y2]


def position_to_bbox(position: Any) -> Dict[str, float]:
    normalized = normalize_position(position)
    if not normalized:
        return {}
    x1, y1, x2, y2 = normalized
    return {
        'x': round(x1 / 1000.0, 6),
        'y': round(y1 / 1000.0, 6),
        'w': round((x2 - x1) / 1000.0, 6),
        'h': round((y2 - y1) / 1000.0, 6),
    }


def relpath_under(path: str, root: str) -> str:
    return Path(os.path.relpath(path, root)).as_posix()


def make_qid_global(page: Any, qid: Any) -> str:
    """Stage 3.5 全局唯一题号: p{page}:{id}（如 p3:3-1），贯穿 memory/Pass2/L5/hallucination。"""
    page_str = str(page or '').strip()
    qid_str = str(qid or '').strip()
    if not page_str or not qid_str:
        return ''
    page_str = page_str.lstrip('p')
    # 原始题号可能恰好以页码开头（如第10页的10-1和1是不同题）。
    # 此处只组合主键，不猜测或剥离所谓的页码前缀。
    return f'p{page_str}:{qid_str}'


def evidence_values(value: Any) -> list:
    """Treat a legacy scalar as one reference, never an iterable of characters."""
    if isinstance(value, list):
        return value
    return [value] if isinstance(value, str) and value else []


def normalize_question_evidence(value: Any, valid_ids=None) -> list:
    """Preserve complete global references; never guess a page from a bare ID."""
    result = []
    for qid in evidence_values(value):
        if not isinstance(qid, str) or not re.fullmatch(r'p[1-9][0-9]*:[^\s:]+', qid):
            continue
        if valid_ids is not None and qid not in valid_ids:
            continue
        if qid not in result:
            result.append(qid)
    return result


def stage_of_grade(grade: Any) -> int:
    """小学 1-2 年级 = S1，3-4 年级 = S2，5-6 年级 = S3。无法识别时回退 S2（与既有数学/语文/英语样本一致）。"""
    try:
        g = int(grade)
    except (TypeError, ValueError):
        return 2
    if g <= 2:
        return 1
    if g <= 4:
        return 2
    return 3


def write_sample_meta(
    base_dir: str,
    subject: str,
    sample_id: str,
    grade: Any,
    *,
    source_document_sha256: str = '',
    source_filename: str = '',
    feedback_runtime=None,
) -> Dict[str, Any]:
    meta_path = os.path.join(base_dir, 'sample_meta.json')
    existing = {}
    if os.path.isfile(meta_path):
        try:
            existing = safe_json_load(meta_path)
        except Exception:
            existing = {}
    meta = {
        **existing,
        'subject': subject,
        'sample_id': sample_id,
        'grade': int(grade) if str(grade).isdigit() else (grade if isinstance(grade, int) else 4),
        'stage': stage_of_grade(grade),
    }
    if feedback_runtime is not None:
        from .feedback_runtime import runtime_attributes
        actual_subject, actual_grade, actual_stage = runtime_attributes(feedback_runtime)
        meta.update(subject=actual_subject, grade=actual_grade, stage=actual_stage,
                    feedback_context=feedback_runtime.context,
                    config_fingerprint=feedback_runtime.fingerprint)
    normalized_hash = str(source_document_sha256 or '').replace(' ', '').strip().lower()
    if re.fullmatch(r'[0-9a-f]{64}', normalized_hash):
        meta['source_document_sha256'] = normalized_hash
        meta['document_identity_version'] = 'source-sha256-v1'
    if source_filename:
        meta['source_filename'] = str(source_filename)
    safe_json_dump(meta_path, meta)
    return meta


def load_sample_meta(base_dir: str) -> Dict[str, Any]:
    path = os.path.join(base_dir, 'sample_meta.json')
    if not os.path.exists(path):
        return {}
    try:
        return safe_json_load(path)
    except Exception:
        return {}


def resolve_source_document_sha256(
    base_dir: str,
    source_path: str,
    *,
    expected_sha256_prefix: str = '',
) -> str:
    """Resolve and validate the immutable source-PDF identity for a workspace."""
    sample_meta = load_sample_meta(base_dir)
    stored = str(sample_meta.get('source_document_sha256') or '')
    stored = stored.replace(' ', '').strip().lower()
    if not re.fullmatch(r'[0-9a-f]{64}', stored):
        stored = ''

    current = (
        sha256_file(source_path)
        if source_path and os.path.isfile(source_path)
        else ''
    )
    expected_prefix = str(expected_sha256_prefix or '').strip().lower()
    if expected_prefix and not re.fullmatch(r'[0-9a-f]{24}', expected_prefix):
        raise ValueError('作业批改任务的源文档身份格式无效')
    if current and expected_prefix and not current.startswith(expected_prefix):
        raise ValueError('源PDF内容与批改任务身份不一致')
    if stored and current and stored != current:
        raise ValueError('源PDF内容已变化，拒绝在原批改工作区继续运行')
    return stored or current
