"""合成源字节与临时目录，验证快照事务；不解析或批改学生PDF。"""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat.homework_grading import feedback_snapshot as snapshots
from app_chat.homework_grading.feedback_context_test import context_fixture
from app_chat.homework_grading.feedback_fingerprint_test import dependency_fixture
from app_chat.homework_grading.feedback_snapshot_reader import read_feedback_snapshot


def snapshot_arguments(root):
    source = Path(root) / 'synthetic-source.pdf'
    source.write_bytes(b'synthetic protocol bytes, not a real student PDF')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return {'source_path': str(source), 'analysis_id': 'homework_' + digest[:24],
            'expected_source_sha256': digest, 'context': context_fixture(), **dependency_fixture()}


class SnapshotWriteTest(unittest.TestCase):
    def test_publish_and_external_mutation_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            args = snapshot_arguments(root)
            target = Path(root) / 'prepared'
            manifest = snapshots.prepare_feedback_snapshot(target, **args)
            before = {p.name: p.read_bytes() for p in target.iterdir()}
            args['references']['reference_text'] = 'later change'
            manifest['feedback_execution']['model_config']['model'] = 'later change'
            self.assertEqual(read_feedback_snapshot(target)['snapshot_status'], 'complete')
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})
            self.assertEqual(len(before), 5)
            with self.assertRaises(FileExistsError):
                snapshots.prepare_feedback_snapshot(target, **args)
            self.assertEqual(before, {p.name: p.read_bytes() for p in target.iterdir()})

    def test_each_write_failure_preserves_old_version(self):
        for failed_index in range(5):
            with self.subTest(index=failed_index), tempfile.TemporaryDirectory() as root:
                args = snapshot_arguments(root)
                old = Path(root) / 'current'
                snapshots.prepare_feedback_snapshot(old, **args)
                before = {p.name: p.read_bytes() for p in old.iterdir()}
                real_write = snapshots._write_snapshot_json
                count = [0]
                def failing_write(path, value):
                    index = count[0]
                    count[0] += 1
                    if index == failed_index:
                        raise OSError('synthetic write failure')
                    return real_write(path, value)
                with mock.patch.object(snapshots, '_write_snapshot_json', side_effect=failing_write):
                    with self.assertRaises(OSError):
                        snapshots.prepare_feedback_snapshot(Path(root) / 'new', **args)
                self.assertFalse((Path(root) / 'new').exists())
                self.assertFalse(list(Path(root).glob('.new-p01-*')))
                self.assertEqual(before, {p.name: p.read_bytes() for p in old.iterdir()})

    def test_validation_and_publication_failures(self):
        for point in ('read_feedback_snapshot', 'rename'):
            with self.subTest(point=point), tempfile.TemporaryDirectory() as root:
                args = snapshot_arguments(root)
                target = Path(root) / 'new'
                patch = (mock.patch.object(snapshots, point, return_value={'snapshot_status': 'invalid'})
                         if point == 'read_feedback_snapshot' else mock.patch.object(snapshots.os, point, side_effect=OSError('publish failed')))
                with patch, self.assertRaises((ValueError, OSError)):
                    snapshots.prepare_feedback_snapshot(target, **args)
                self.assertFalse(target.exists())
                self.assertFalse(list(Path(root).glob('.new-p01-*')))

    def test_full_hash_conflict_and_wrong_prefix(self):
        with tempfile.TemporaryDirectory() as root:
            args = snapshot_arguments(root)
            # 同24位前缀、不同完整哈希，也必须拒绝。
            digest = args['expected_source_sha256']
            args['expected_source_sha256'] = digest[:24] + ('0' if digest[24] != '0' else '1') + digest[25:]
            with self.assertRaisesRegex(ValueError, '完整哈希冲突'):
                snapshots.prepare_feedback_snapshot(Path(root) / 'new', **args)
            args['analysis_id'] = 'homework_' + '0' * 24
            with self.assertRaises(ValueError):
                snapshots.prepare_feedback_snapshot(Path(root) / 'new', **args)

    def test_source_changes_before_publish(self):
        with tempfile.TemporaryDirectory() as root:
            args = snapshot_arguments(root)
            with mock.patch.object(snapshots, 'sha256_file', return_value='0' * 64), self.assertRaises(ValueError):
                snapshots.prepare_feedback_snapshot(Path(root) / 'new', **args)
            self.assertFalse((Path(root) / 'new').exists())


if __name__ == '__main__':
    unittest.main()
