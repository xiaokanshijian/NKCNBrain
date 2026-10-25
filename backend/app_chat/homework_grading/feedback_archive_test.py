"""P01根目录快照归档测试；仅合成源字节及临时目录。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat.homework_grading import homework_versions as versions
from app_chat.homework_grading.feedback_snapshot import prepare_feedback_snapshot
from app_chat.homework_grading.feedback_snapshot_test import snapshot_arguments
from app_chat.homework_grading.feedback_snapshot_reader import SNAPSHOT_FILES, read_feedback_snapshot


def archive_fixture(root):
    args = snapshot_arguments(root)
    current = Path(root) / 'current'
    prepare_feedback_snapshot(current, **args)
    (current / 'homework_grading').mkdir()
    # 持久锁文件属于协调设施；失败不能改变业务文件或历史索引。
    (current / '.archive.lock').write_bytes(b'0')
    (current / 'homework_grading' / 'sample_meta.json').write_text('{"synthetic":true}', encoding='utf-8')
    old = current / '_archives' / 'keep'
    old.mkdir(parents=True)
    (old / 'keep.txt').write_bytes(b'keep original history')
    (current / '_archives' / 'index.json').write_text('{"versions":[{"run_id":"keep"}]}', encoding='utf-8')
    return current


class ArchiveSnapshotTest(unittest.TestCase):
    def test_archive_contains_complete_independent_snapshots(self):
        with tempfile.TemporaryDirectory() as root:
            current = archive_fixture(root)
            before = {name: (current / name).read_bytes() for name in ['manifest.json', *SNAPSHOT_FILES.values()]}
            with mock.patch.object(versions, '_container_root', return_value=str(current)):
                run_id = versions.archive_homework_run_if_exists('fixture', 'fixture')
            archive = current / '_archives' / run_id
            for name, payload in before.items():
                self.assertEqual((archive / name).read_bytes(), payload)
                self.assertEqual((current / name).read_bytes(), payload)
            self.assertEqual(read_feedback_snapshot(archive), read_feedback_snapshot(current))
            self.assertEqual((current / '_archives' / 'keep' / 'keep.txt').read_bytes(), b'keep original history')
            (current / 'feedback_context.json').write_bytes(b'current later changed')
            self.assertEqual(read_feedback_snapshot(archive)['snapshot_status'], 'complete')

    def test_rejects_incomplete_current_before_archiving(self):
        with tempfile.TemporaryDirectory() as root:
            current = archive_fixture(root)
            (current / 'skill_snapshot.json').unlink()
            before = {str(p.relative_to(current)): p.read_bytes() for p in current.rglob('*') if p.is_file()}
            with mock.patch.object(versions, '_container_root', return_value=str(current)), self.assertRaises(ValueError):
                versions.archive_homework_run_if_exists('fixture', 'fixture')
            self.assertEqual(before, {str(p.relative_to(current)): p.read_bytes() for p in current.rglob('*') if p.is_file()})

    def test_copy_validation_and_index_failure_protect_existing_files(self):
        for failure in ['context', 'skills', 'curriculum', 'references', 'validation', 'index']:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as root:
                current = archive_fixture(root)
                before = {str(p.relative_to(current)): p.read_bytes() for p in current.rglob('*') if p.is_file()}
                real_copy = versions.shutil.copy2
                def failed_copy(source, target, *args, **kwargs):
                    if Path(source).name == SNAPSHOT_FILES.get(failure):
                        raise OSError('synthetic snapshot copy failure')
                    result = real_copy(source, target, *args, **kwargs)
                    if failure == 'validation' and Path(source).name == 'reference_snapshot.json':
                        Path(target).write_bytes(b'broken copy')
                    return result
                patch = (mock.patch.object(versions, '_save_archives_index', side_effect=OSError('synthetic index failure'))
                         if failure == 'index' else mock.patch.object(versions.shutil, 'copy2', side_effect=failed_copy))
                with mock.patch.object(versions, '_container_root', return_value=str(current)), patch, self.assertRaises((OSError, ValueError)):
                    versions.archive_homework_run_if_exists('fixture', 'fixture')
                self.assertEqual(before, {str(p.relative_to(current)): p.read_bytes() for p in current.rglob('*') if p.is_file()})
                self.assertEqual(sorted(p.name for p in (current / '_archives').iterdir()), ['index.json', 'keep'])

    def test_existing_unregistered_temporary_directory_retained(self):
        with tempfile.TemporaryDirectory() as root:
            current = archive_fixture(root)
            retained = current / '_archives' / '.earlier.tmp'
            retained.mkdir()
            (retained / 'audit.txt').write_text('preserve previous evidence', encoding='utf-8')
            with mock.patch.object(versions, '_container_root', return_value=str(current)):
                versions.archive_homework_run_if_exists('fixture', 'fixture')
            self.assertEqual((retained / 'audit.txt').read_text(), 'preserve previous evidence')


if __name__ == '__main__':
    unittest.main()
