"""本子内材料内容身份；文件名只是定位输入和历史别名，不跨本子复用。"""
import re
from pathlib import Path

from django.conf import settings
from .ci_access import assert_workspace_path
from .homework_grading.utils import sha256_file, safe_json_load


def source_digest(workspace, filename):
    path = Path(assert_workspace_path(workspace, Path(settings.BASE_DIR) /
        'received_dir/user_raw_file' / workspace / filename))
    if not path.is_file():
        return None
    return sha256_file(str(path))


def record_digest(workspace, record):
    digest = record.get('source_document_sha256')
    if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest):
        return digest
    analysis_id = record.get('analysis_id', '')
    if not re.fullmatch(r'homework_[0-9a-f]{24}', analysis_id):
        return None
    from .homework_grading.homework_versions import resolve_homework_run_root
    try:
        root = resolve_homework_run_root(workspace, analysis_id, record.get('run_id') or 'current')
        digest = safe_json_load(Path(root) / 'manifest.json').get('source_document_sha256')
        return digest if isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest) else None
    except (ValueError, OSError, TypeError):
        return None


def resolve_source_filename(workspace, filename, expected_digest):
    """原名消失后只查本子原件别名；同名换内容仍拒绝旧运行续做。"""
    actual = source_digest(workspace, filename)
    if actual:
        if expected_digest and actual != expected_digest:
            raise ValueError('原文件已被同名新内容替换，请从材料入口完整新跑')
        return filename
    if not isinstance(expected_digest, str) or not re.fullmatch(r'[0-9a-f]{64}', expected_digest):
        raise ValueError('原文件不存在，且旧运行无法核对内容身份')
    root = Path(settings.BASE_DIR) / 'received_dir/user_raw_file' / workspace
    for path in sorted(root.glob('*')):
        if path.is_file() and path.suffix.lower() == '.pdf' and source_digest(workspace, path.name) == expected_digest:
            return path.name
    raise ValueError('本子内找不到对应内容的原PDF，请恢复原件后再继续')
