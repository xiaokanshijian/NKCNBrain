"""独立运行目录与原子当前版本指针；旧目录保留为无指针历史布局。"""
import json
from pathlib import Path
import re

from app_chat.ci.file_io import atomic_json
from app_chat.ci_access import is_relative_to

POINTER_NAME = 'current_run.json'


def run_directory(container, run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r'p03_[0-9a-f]{32}', run_id):
        raise ValueError('批改运行标识无效')
    container = Path(container).resolve()
    directory = container / '_runs' / run_id
    resolved = directory.resolve()
    if (not is_relative_to(resolved, container)
            or resolved.parent != (container / '_runs').resolve() or directory.is_symlink()):
        raise ValueError('批改运行目录超出工作区')
    return directory


def read_pointer(container):
    pointer = Path(container) / POINTER_NAME
    if not pointer.exists():
        return None
    value = json.loads(pointer.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema_version') != 'ci-current-v1':
        raise ValueError('当前版本指针损坏，请保留原运行目录')
    directory = run_directory(container, value.get('run_id'))
    if not (directory / 'manifest.json').is_file():
        raise ValueError('当前版本目录不完整，请恢复启动事务')
    return value


def current_directory(container):
    pointer = read_pointer(container)
    return run_directory(container, pointer['run_id']) if pointer else Path(container)


def publish_pointer(container, run_id):
    directory = run_directory(container, run_id)
    if not (directory / 'manifest.json').is_file():
        raise ValueError('尚未准备运行记录，拒绝发布当前版本')
    value = {'schema_version': 'ci-current-v1', 'run_id': run_id}
    atomic_json(Path(container) / POINTER_NAME, value)
    return value


def restore_pointer(container, previous):
    if previous is None:
        # 仅撤销本次创建的指针，不清理任何运行、快照或原材料。
        (Path(container) / POINTER_NAME).unlink(missing_ok=True)
    else:
        publish_pointer(container, previous['run_id'])
