"""持久化批改任务；内存表只是缓存，归属和运行标识不可被进度更新改写。"""
import datetime
import json
from pathlib import Path
import re

from .file_io import FileLock, atomic_json

PROGRESS_FIELDS = {'current_item', 'total_items', 'current_section', 'completed', 'error',
                   'status', 'failure_stage', 'warnings', 'content_validation', 'updated_at'}
TERMINAL = {'completed', 'failed', 'interrupted'}


def runtime_root():
    from django.conf import settings
    return Path(settings.BASE_DIR) / 'received_dir' / '.ci_runtime'


def task_path(task_id, root=None):
    if not isinstance(task_id, str) or not re.fullmatch(r'ci_task_[a-zA-Z0-9_-]{1,80}', task_id):
        raise ValueError('任务标识无效')
    return Path(root if root is not None else runtime_root()) / 'tasks' / (task_id + '.json')


def read_task(task_id, *, root=None):
    path = task_path(task_id, root)
    if not path.is_file():
        return None
    with FileLock(str(path) + '.lock', timeout=15):
        record = json.loads(path.read_text(encoding='utf-8'))
    if (not isinstance(record, dict) or record.get('task_id') != task_id
            or not record.get('_ci_principal') or not record.get('_ci_workspace')
            or record.get('schema_version') != 'ci-task-v1'):
        raise ValueError('任务记录损坏，不能核实运行归属')
    return record


def create_task(record, *, root=None):
    required = {'task_id', '_ci_principal', '_ci_workspace', 'analysis_id', 'run_id',
                'source_document_sha256', 'config_fingerprint'}
    if not isinstance(record, dict) or any(not record.get(key) for key in required):
        raise ValueError('任务缺少归属或冻结运行标识')
    for key in ('source_document_sha256', 'config_fingerprint'):
        if not re.fullmatch('[0-9a-f]{64}', record[key]):
            raise ValueError('任务运行指纹无效')
    path = task_path(record['task_id'], root)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    value = dict(record, schema_version='ci-task-v1', _ci_persistent=True,
                 created_at=now, updated_at=now)
    value.setdefault('status', 'registered')
    value.setdefault('completed', False)
    with FileLock(str(path) + '.lock', timeout=15):
        if path.exists():
            raise FileExistsError('任务标识已登记，拒绝覆盖')
        atomic_json(path, value)
    return value


def update_task(task_id, changes, *, root=None):
    if not isinstance(changes, dict) or set(changes) - PROGRESS_FIELDS:
        raise ValueError('进度更新不能改写任务归属或运行依据')
    path = task_path(task_id, root)
    with FileLock(str(path) + '.lock', timeout=15):
        record = json.loads(path.read_text(encoding='utf-8'))
        if record.get('task_id') != task_id or record.get('schema_version') != 'ci-task-v1':
            raise ValueError('任务记录损坏')
        if record.get('status') in TERMINAL:
            return record
        record.update(changes)
        if record.get('completed'):
            record['status'] = ('failed' if record.get('error') else 'completed')
        if changes.get('status') in TERMINAL:
            record['status'] = changes['status']
            record['completed'] = True
        record['updated_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        atomic_json(path, record)
    return record
