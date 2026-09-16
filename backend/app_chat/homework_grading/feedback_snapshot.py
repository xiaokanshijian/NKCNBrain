"""准备独立运行快照；尚未接入生产启动事务。"""
import copy
import hashlib
import os
import re
import shutil
import tempfile
from pathlib import Path

from app_chat.homework_grading.feedback_context import FrozenFeedbackContext, canonical_json
from app_chat.homework_grading.feedback_fingerprint import fingerprint_payload, content_sha256
from app_chat.homework_grading.feedback_snapshot_reader import SNAPSHOT_FILES, SNAPSHOT_SCHEMA, is_sha256, read_feedback_snapshot
from app_chat.homework_grading.utils import resolve_source_document_sha256, sha256_file


def _write_snapshot_json(path, data):
    with open(path, 'x', encoding='utf-8', newline='\n') as handle:
        handle.write(canonical_json(data))
        handle.flush()
        os.fsync(handle.fileno())


def prepare_feedback_snapshot(destination, *, source_path, analysis_id, context,
                              skills, curriculum, references, model_config, preprocessing, retrieval,
                              expected_source_sha256=None):
    """destination必须是服务端选择的、尚不存在的独立暂存目标。

    成功后四快照和manifest一起可读，失败不发布；不归档/替换current。
    P03负责用户隔离、同文档互斥以及最终工作区切换。这里不提供跨worker锁。
    """
    destination = Path(destination).absolute()
    if os.path.lexists(destination):
        raise FileExistsError('冻结快照目标已存在，拒绝覆盖')
    match = re.fullmatch(r'homework_([0-9a-f]{24})', analysis_id or '')
    if not match or not Path(source_path).is_file():
        raise ValueError('源文件或作业身份无效')
    source_hash = resolve_source_document_sha256(str(destination / 'homework_grading'), str(source_path),
                                               expected_sha256_prefix=match.group(1))
    if not is_sha256(source_hash):
        raise ValueError('无法核验源文件完整哈希')
    if expected_source_sha256 is not None and (not is_sha256(expected_source_sha256) or expected_source_sha256 != source_hash):
        raise ValueError('源文件完整哈希冲突，拒绝准备快照')
    data = context.to_dict() if isinstance(context, FrozenFeedbackContext) else copy.deepcopy(context)
    dependencies = copy.deepcopy({'skills': skills, 'curriculum': curriculum, 'references': references,
                                  'model_config': model_config, 'preprocessing': preprocessing, 'retrieval': retrieval})
    payload = fingerprint_payload(data, **dependencies)
    # 执行配置只保存参与指纹的配置；凭据不应被调用者传入此接口。
    execution = {key: payload[key] for key in ('model_config', 'preprocessing', 'retrieval')}
    manifest = {'analysis_type': 'homework_grading', 'group_id': analysis_id,
                'source_document_sha256': source_hash, 'config_fingerprint': content_sha256(payload),
                'feedback_execution': execution,
                'feedback_snapshot': {'schema_version': SNAPSHOT_SCHEMA, 'status': 'complete', 'files': {}}}
    contents = {'context': data, **{key: dependencies[key] for key in ('skills', 'curriculum', 'references')}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f'.{destination.name}-p01-', dir=destination.parent))
    try:
        for kind, filename in SNAPSHOT_FILES.items():
            value = contents[kind] if kind == 'context' else {'schema_version': SNAPSHOT_SCHEMA, 'kind': kind, 'data': contents[kind]}
            path = staging / filename
            _write_snapshot_json(path, value)
            manifest['feedback_snapshot']['files'][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
        # 完整性记录最后写入；写到此处之前，目录不可能被认作完整快照。
        _write_snapshot_json(staging / 'manifest.json', manifest)
        if read_feedback_snapshot(staging)['snapshot_status'] != 'complete':
            raise ValueError('新快照完整性校验失败，未发布')
        if sha256_file(str(source_path)) != source_hash:
            raise ValueError('准备快照期间源文件内容发生变化')
        if os.path.lexists(destination):
            raise FileExistsError('冻结快照目标已存在，拒绝覆盖')
        # 同盘目录重命名发布。Windows上已存在目标会明确失败，不覆盖旧目录。
        os.rename(staging, destination)
        return copy.deepcopy(manifest)
    finally:
        # 仅清理本次mkdtemp创建的目录，绝不清理destination或其他版本。
        if staging.exists():
            if staging.resolve().parent != destination.parent.resolve() or not staging.name.startswith(f'.{destination.name}-p01-'):
                raise ValueError('临时快照目录超出本次工作区')
            shutil.rmtree(staging)
