"""本地进程间互斥与同目录原子JSON发布，无新增依赖。"""
import json
import os
from pathlib import Path
import tempfile
import time


class FileLockBusy(RuntimeError):
    pass


class FileLock:
    def __init__(self, path, *, timeout=0):
        self.path = Path(path)
        self.timeout = timeout
        self.handle = None

    def acquire(self):
        if self.handle is not None:
            raise RuntimeError('文件锁不能重复获取')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, 'a+b')
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.handle = handle
                return self
            except OSError as exc:
                if time.monotonic() >= deadline:
                    handle.close()
                    raise FileLockBusy('该文件对应的操作正在进行，请稍后重试') from exc
                time.sleep(min(0.05, max(0, deadline - time.monotonic())))

    def release(self):
        handle, self.handle = self.handle, None
        if handle is None:
            return
        try:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='\n',
                prefix='.' + path.name + '-', suffix='.tmp', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, allow_nan=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
