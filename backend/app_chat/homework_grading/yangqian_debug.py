"""杨谦批改调整：关键信息同时 print 并原样写入 txt。"""
import datetime
import os
import threading
from typing import Optional

_LOCK = threading.Lock()
DEFAULT_TXT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'yangqian_adjust.debug.txt')


def debug_txt_path(extra_dir: Optional[str] = None) -> str:
    if extra_dir:
        return os.path.join(extra_dir, 'yangqian_adjust.debug.txt')
    return DEFAULT_TXT


def debug_log(message, extra_dir: Optional[str] = None) -> str:
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{stamp}] {message}'
    print(line, flush=True)
    _append(DEFAULT_TXT, line)
    if extra_dir:
        _append(debug_txt_path(extra_dir), line)
    return line


def _append(path: str, line: str) -> None:
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with _LOCK:
            with open(path, 'a', encoding='utf-8') as handle:
                handle.write(line + '\n')
    except Exception as exc:
        print(f'[yangqian_debug] 写 txt 失败 {path}: {exc}', flush=True)
