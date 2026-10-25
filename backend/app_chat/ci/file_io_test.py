import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .file_io import FileLock, FileLockBusy, atomic_json


class FileIOTest(unittest.TestCase):
    def test_cross_process_contention_and_crash_release(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / 'document.lock'
            script = ('import sys,os; from app_chat.ci.file_io import FileLock; '
                      'lock=FileLock(sys.argv[1]).acquire(); print("locked",flush=True); '
                      'sys.stdin.readline(); os._exit(23)')
            child = subprocess.Popen([sys.executable, '-c', script, str(lock)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                for line in child.stdout:
                    if line.strip() == 'locked':
                        break
                else:
                    self.fail('锁进程未就绪')
                with self.assertRaises(FileLockBusy):
                    FileLock(lock).acquire()
                child.stdin.write('crash\n')
                child.stdin.flush()
                child.wait(timeout=10)
                self.assertEqual(child.returncode, 23)
                with FileLock(lock):
                    pass
            finally:
                if child.poll() is None:
                    child.stdin.write('crash\n')
                    child.stdin.flush()
                    child.wait(timeout=10)
                child.stdin.close()
                child.stdout.close()

    def test_concurrent_atomic_read_modify_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'index.json'
            atomic_json(path, {'items': []})
            script = '''import json,sys
from pathlib import Path
from app_chat.ci.file_io import FileLock,atomic_json
p=Path(sys.argv[1])
for n in range(15):
 with FileLock(str(p)+'.lock',timeout=10):
  value=json.loads(p.read_text()); value['items'].append(sys.argv[2]+str(n)); atomic_json(p,value)
'''
            children = [subprocess.Popen([sys.executable, '-c', script, str(path), str(n)]) for n in range(3)]
            for child in children:
                self.assertEqual(child.wait(timeout=20), 0)
            self.assertEqual(len(set(json.loads(path.read_text())['items'])), 45)

    def test_failed_publish_preserves_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'index.json'
            atomic_json(path, {'version': 1})
            original = path.read_bytes()
            with patch('app_chat.ci.file_io.os.replace', side_effect=OSError('synthetic failure')):
                with self.assertRaises(OSError):
                    atomic_json(path, {'version': 2})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(tmp).glob('*.tmp')), [])

    def test_actual_index_updates_and_corrupt_file_preservation(self):
        from concurrent.futures import ThreadPoolExecutor
        from .index_manager import CIIndexManager
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'index.json'
            with patch('app_chat.ci.index_manager._ci_index_path', return_value=str(path)):
                with ThreadPoolExecutor(max_workers=3) as executor:
                    list(executor.map(lambda n: CIIndexManager.add_or_update('synthetic',
                        {'analysis_id': str(n), 'status': 'running'}), range(12)))
                self.assertEqual(len(CIIndexManager.load('synthetic')), 12)
                CIIndexManager.restore_record('synthetic', '1', {'analysis_id': '1', 'status': 'completed'})
                self.assertEqual(len(CIIndexManager.load('synthetic')), 12)
                self.assertEqual(CIIndexManager.find_by_id('synthetic', '1')['status'], 'completed')
                CIIndexManager.restore_record('synthetic', '1', None)
                self.assertEqual(len(CIIndexManager.load('synthetic')), 11)
                path.write_text('{broken')
                with self.assertRaises(ValueError):
                    CIIndexManager.add_or_update('synthetic', {'analysis_id': 'new'})
                self.assertEqual(path.read_text(), '{broken')
