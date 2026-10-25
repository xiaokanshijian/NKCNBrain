"""P01合成快照，哈希仅为协议验证；不是实际模型运行。"""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from app_chat.homework_grading.feedback_context_test import context_fixture
from app_chat.homework_grading.feedback_fingerprint import compute_config_fingerprint
from app_chat.homework_grading.feedback_fingerprint_test import dependency_fixture
from app_chat.homework_grading.feedback_snapshot_reader import SNAPSHOT_FILES, SNAPSHOT_SCHEMA, read_feedback_snapshot


def write_snapshot_fixture(root, name='初中·初二·物理·作业.pdf'):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    data = {'context': context_fixture(name).to_dict(), 'skills': [], 'curriculum': None,
            'references': {'status': 'none', 'documents': [], 'reference_text': ''}}
    hashes = {}
    for kind, filename in SNAPSHOT_FILES.items():
        value = data[kind] if kind == 'context' else {'schema_version': SNAPSHOT_SCHEMA, 'kind': kind, 'data': data[kind]}
        payload = json.dumps(value, ensure_ascii=False).encode('utf-8')
        (root / filename).write_bytes(payload)
        hashes[filename] = hashlib.sha256(payload).hexdigest()
    execution = {key: value for key, value in dependency_fixture().items() if key in ('model_config', 'preprocessing', 'retrieval')}
    fingerprint = compute_config_fingerprint(data['context'], skills=data['skills'], curriculum=data['curriculum'],
                                             references=data['references'], **execution)
    manifest = {'source_document_sha256': 'a' * 64, 'config_fingerprint': fingerprint, 'feedback_execution': execution,
                'feedback_snapshot': {'schema_version': SNAPSHOT_SCHEMA, 'status': 'complete', 'files': hashes}}
    (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    return manifest


class SnapshotReaderTest(unittest.TestCase):
    def test_legacy_never_invents_context(self):
        with tempfile.TemporaryDirectory() as root:
            result = read_feedback_snapshot(root, {'grade': 4, 'config_fingerprint': 'b' * 64})
            self.assertEqual(result['snapshot_status'], 'legacy_missing')
            self.assertIsNone(result['feedback_context'])
            self.assertIsNone(result['config_fingerprint'])

    def test_current_and_archive_isolated(self):
        with tempfile.TemporaryDirectory() as root:
            old = Path(root) / '_archives' / 'synthetic'
            write_snapshot_fixture(root)
            write_snapshot_fixture(old, '大学·大一·高等数学·笔记.pdf')
            self.assertEqual(read_feedback_snapshot(root)['feedback_context']['education_level'], 'junior')
            self.assertEqual(read_feedback_snapshot(old)['feedback_context']['education_level'], 'university')

    def test_missing_corrupt_and_future(self):
        for mutation, expected in [('missing', 'missing'), ('hash', 'invalid'), ('json', 'invalid'), ('future', 'unsupported')]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as root:
                manifest = write_snapshot_fixture(root)
                path = Path(root) / 'skill_snapshot.json'
                if mutation == 'missing':
                    path.unlink()
                elif mutation in ('hash', 'json'):
                    path.write_bytes(b'broken')
                    if mutation == 'json':
                        manifest['feedback_snapshot']['files'][path.name] = hashlib.sha256(b'broken').hexdigest()
                else:
                    manifest['feedback_snapshot']['schema_version'] = 'future'
                result = read_feedback_snapshot(root, manifest)
                self.assertEqual(result['snapshot_status'], expected)
                self.assertIsNone(result['config_fingerprint'])

    def test_orphan_and_incomplete_snapshots_not_legacy(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = write_snapshot_fixture(root)
            self.assertEqual(read_feedback_snapshot(root, {})['snapshot_status'], 'invalid')
            manifest['feedback_snapshot']['status'] = 'writing'
            self.assertEqual(read_feedback_snapshot(root, manifest)['snapshot_status'], 'invalid')

    def test_mismatched_fingerprint_not_complete(self):
        with tempfile.TemporaryDirectory() as root:
            manifest = write_snapshot_fixture(root)
            manifest['feedback_execution']['model_config']['model'] = 'changed'
            self.assertEqual(read_feedback_snapshot(root, manifest)['snapshot_status'], 'invalid')

    def test_result_service_reads_selected_root(self):
        from app_chat.homework_grading import service
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / '_archives' / 'synthetic'
            from .feedback_skills_test import runtime_fixture
            from .feedback_snapshot_test import snapshot_arguments
            from .feedback_snapshot import prepare_feedback_snapshot
            runtime = runtime_fixture('大学·大一·高等数学·笔记.pdf')
            args = snapshot_arguments(root)
            args.update(context=runtime.context, **runtime.dependencies)
            prepare_feedback_snapshot(archive, **args)
            with mock.patch.object(service, 'resolve_homework_run_root', return_value=str(archive)):
                result = service.get_homework_grading_result('synthetic-user', 'homework_synthetic', 'synthetic')
            self.assertEqual(result['error_num'], 0)
            self.assertEqual(result['run_id'], 'synthetic')
            self.assertEqual(result['feedback_context']['education_level'], 'university')
            self.assertEqual(result['snapshot_status'], 'complete')


if __name__ == '__main__':
    unittest.main()
