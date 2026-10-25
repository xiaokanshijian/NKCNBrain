"""后处理在候选副本运行；整组验证后发布，异常或进程中断可恢复旧字节。"""
import json
import os
from pathlib import Path
import tempfile
import uuid

from .utils import safe_json_dump, safe_json_load, windows_io_path

JOURNAL = 'artifact_transaction.json'


def _io(path):
    return Path(windows_io_path(path))


def _resolved(path):
    # 解析、stat、目录遍历也必须使用扩展路径；逻辑路径用于相对日志和边界比较。
    value = str(_io(path).resolve())
    if os.name == 'nt':
        if value.startswith('\\\\?\\UNC\\'):
            value = '\\\\' + value[8:]
        elif value.startswith('\\\\?\\'):
            value = value[4:]
    return Path(value)


def _inside(root, relative):
    path = root / relative
    target = _resolved(path)
    if _resolved(root) not in target.parents or _io(path).is_symlink():
        raise ValueError('产物事务路径超出运行目录')
    return target


def _read(path):
    with open(windows_io_path(path), 'rb') as handle:
        return handle.read()


def _publish(path, value):
    destination = Path(windows_io_path(path))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.publish-', delete=False) as handle:
            temporary = handle.name
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def transaction_pending(base):
    path = Path(base) / JOURNAL
    if not _io(path).is_file():
        return False
    return safe_json_load(path).get('status') == 'publishing'


def recover_transaction(base):
    base = _resolved(base)
    path = base / JOURNAL
    if not _io(path).is_file():
        return
    journal = safe_json_load(path)
    if journal.get('status') != 'publishing':
        return
    for item in journal['files']:
        target = _inside(base, item['target'])
        if item['before'] is not None:
            _publish(target, _read(_inside(base, item['before'])))
        elif _io(target).exists():
            # 仅移除本事务新建、此前不存在的派生产物，不删除已有业务文件。
            os.unlink(windows_io_path(target))
    journal['status'] = 'rolled_back'
    safe_json_dump(path, journal)


def candidate_transaction(paths, operation, *, include_images=False):
    base = _resolved(paths['base'])
    recover_transaction(base)
    tx = base / 'artifact_transactions' / uuid.uuid4().hex
    candidate = tx / 'candidate'
    _io(candidate).mkdir(parents=True)
    # 候选目录仅供内部后处理使用，传扩展路径也保护调用方的普通open/stat/glob。
    translated = dict(paths, base=str(_io(candidate)))
    for name in ('pass1_json', 'pass2_report'):
        translated[name] = str(_io(candidate / name))
        _io(candidate / name).mkdir()
    if include_images:
        for name in ('annotated', 'annotated_understanding', 'annotated_layout'):
            if name in paths:
                translated[name] = str(_io(candidate / name))
                _io(candidate / name).mkdir()
    # 仅复制本阶段需要的JSON和已有修正备份；原图/批改图保持只读共享。
    sources = [base / p.name for p in _io(base).glob('*.json') if p.is_file()]
    for name in ('pass1_json', 'pass2_report'):
        sources += [base / name / p.name for p in _io(base / name).iterdir() if p.is_file() and
                    (p.suffix == '.json' or p.name.endswith('.corrected.bak'))]
    for source in sources:
        if source.name == JOURNAL:
            continue
        target = candidate / source.relative_to(base)
        _publish(target, _read(_inside(base, source.relative_to(base))))
    try:
        result = operation(translated)
    except Exception as exc:
        safe_json_dump(tx / 'rejected.json', {'status': 'rejected', 'error': str(exc)})
        raise
    changes = []
    for after_io in _io(candidate).rglob('*'):
        if not after_io.is_file():
            continue
        relative = after_io.relative_to(_io(candidate))
        after = _inside(candidate, relative)
        target = _inside(base, relative)
        value = _read(after)
        if _io(target).is_file() and _read(target) == value:
            continue
        before = None
        if _io(target).is_file():
            before = tx / 'before' / relative
            _publish(before, _read(target))
        changes.append({'target': relative.as_posix(),
                        'before': before.relative_to(base).as_posix() if before else None,
                        'after': after.relative_to(base).as_posix()})
    journal = {'status': 'publishing', 'files': changes}
    safe_json_dump(base / JOURNAL, journal)
    try:
        for item in changes:
            _publish(_inside(base, item['target']), _read(_inside(base, item['after'])))
        journal['status'] = 'committed'
        safe_json_dump(base / JOURNAL, journal)
    except Exception:
        recover_transaction(base)
        raise
    return result
