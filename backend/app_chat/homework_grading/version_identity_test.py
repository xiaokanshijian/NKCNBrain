"""隔离目录验证历史读取和内容身份，不修改真实材料。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_chat import ci_test_support  # noqa: F401
from django.test import override_settings, RequestFactory
from app_chat.feedback_material_settings import (material_settings, load_saved_material_settings,
                                                legacy_settings_path)
from app_chat.feedback_material_identity import source_digest
from app_chat.ci.index_manager import CIIndexManager
from . import homework_versions as versions
from .feedback_workspaces import publish_pointer, run_directory
from .feedback_snapshot_reader_test import write_snapshot_fixture
from .utils import safe_json_dump, safe_json_load


class VersionIdentityTest(unittest.TestCase):
    def test_rerun_resolves_missing_original_name_but_rejects_same_name_replacement(self):
        from app_chat.feedback_material_identity import resolve_source_filename
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            root = Path(tmp) / 'received_dir/user_raw_file/synthetic_book'
            root.mkdir(parents=True)
            (root / 'renamed.pdf').write_bytes(b'synthetic original')
            digest = source_digest('synthetic_book', 'renamed.pdf')
            self.assertEqual(resolve_source_filename('synthetic_book', 'old.pdf', digest), 'renamed.pdf')
            (root / 'old.pdf').write_bytes(b'synthetic replacement')
            with self.assertRaisesRegex(ValueError, '同名新内容'):
                resolve_source_filename('synthetic_book', 'old.pdf', digest)

    def test_broken_current_does_not_block_runs_archives_images_or_key_flag(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(versions, '_container_root', return_value=tmp):
            root = Path(tmp)
            run = 'p03_' + 'a' * 32
            directory = run_directory(root, run)
            write_snapshot_fixture(directory)
            archive = root / '_archives/20260926_120000'
            write_snapshot_fixture(archive)
            safe_json_dump(root / '_archives/index.json', {'versions': [{'run_id': archive.name}]})
            (root / 'current_run.json').write_text('{broken', encoding='utf-8')
            before = (directory / 'manifest.json').read_bytes()
            self.assertEqual(Path(versions.resolve_homework_run_root('synthetic', 'id', run)), directory)
            self.assertEqual(Path(versions.resolve_homework_run_root('synthetic', 'id', archive.name)), archive)
            listed = versions.list_homework_versions('synthetic', 'id')
            self.assertEqual({v['run_id'] for v in listed}, {run, archive.name, 'current'})
            self.assertTrue(all(v.get('history_warning') for v in listed))
            from .service import get_homework_grading_result
            result = get_homework_grading_result('synthetic', 'id')
            self.assertTrue(result['current_unavailable'])
            self.assertFalse(result['available_actions']['resume']['enabled'])
            self.assertEqual(get_homework_grading_result('synthetic', 'id', run)['run_id'], run)
            versions.set_homework_version_key('synthetic', 'id', run, True)
            self.assertTrue(next(v for v in versions.list_homework_versions('synthetic', 'id') if v['run_id'] == run)['is_key_version'])
            self.assertEqual((directory / 'manifest.json').read_bytes(), before)

    def test_new_run_archiving_is_idempotent_reference_only(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(versions, '_container_root', return_value=tmp):
            run = 'p03_' + 'b' * 32
            directory = run_directory(tmp, run)
            manifest = write_snapshot_fixture(directory)
            manifest['run_id'] = run
            safe_json_dump(directory / 'manifest.json', manifest)
            (directory / 'homework_grading').mkdir()
            publish_pointer(tmp, run)
            with patch.object(versions.shutil, 'copy2', side_effect=AssertionError('must not copy')):
                self.assertEqual(versions.archive_homework_run_if_exists('user', 'id'), run)
                self.assertEqual(versions.archive_homework_run_if_exists('user', 'id'), run)
            index = safe_json_load(Path(tmp) / '_archives/index.json')
            self.assertEqual(len(index['versions']), 1)
            self.assertEqual(index['versions'][0]['storage'], 'run')
            self.assertFalse((Path(tmp) / '_archives' / run).exists())

    def test_display_does_not_restore_execution_rules(self):
        from .feedback_result_basis import result_basis
        with tempfile.TemporaryDirectory() as tmp:
            manifest = write_snapshot_fixture(tmp)
            with patch('app_chat.homework_grading.feedback_runtime_service.restore_feedback_runtime',
                       side_effect=AssertionError('display must not restore execution')):
                state, view, _, _ = result_basis(tmp, manifest)
            self.assertEqual(state['snapshot_status'], 'complete')
            self.assertEqual(view.fingerprint, manifest['config_fingerprint'])

    def test_rename_shares_settings_replacement_does_not_and_query_uses_content(self):
        from app_chat.ci.orchestrator import query_ci_analyses
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            root = Path(tmp) / 'received_dir/user_raw_file/synthetic_book'
            root.mkdir(parents=True)
            (root / 'a.pdf').write_bytes(b'synthetic first')
            (root / 'b.pdf').write_bytes(b'synthetic first')
            request = RequestFactory().post('/', {'files': ['a.pdf'], 'save': True,
                'material': {'reference_text': 'synthetic reference'}}, content_type='application/json')
            request.ci_workspace = 'synthetic_book'
            self.assertEqual(json.loads(material_settings.__wrapped__.__wrapped__(request).content)['error_num'], 0)
            self.assertEqual(load_saved_material_settings('synthetic_book', 'b.pdf')[0]['reference_text'], 'synthetic reference')
            digest = source_digest('synthetic_book', 'a.pdf')
            record = {'analysis_type': 'homework_grading', 'analysis_id': 'homework_' + digest[:24],
                      'source_document_sha256': digest, 'mode': 'single', 'files': ['a.pdf']}
            with patch.object(CIIndexManager, 'load', return_value=[record]):
                self.assertIn('b.pdf', query_ci_analyses('synthetic_book', ['b.pdf'])['singles'][0]['files'])
                (root / 'a.pdf').write_bytes(b'synthetic replaced')
                self.assertEqual(query_ci_analyses('synthetic_book', ['a.pdf'])['singles'], [])
                self.assertFalse(load_saved_material_settings('synthetic_book', 'a.pdf')[1])

    def test_unverified_legacy_settings_require_explicit_save(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            root = Path(tmp) / 'received_dir/user_raw_file/synthetic_book'
            root.mkdir(parents=True)
            (root / 'a.pdf').write_bytes(b'synthetic')
            safe_json_dump(legacy_settings_path('synthetic_book', 'a.pdf'), {'reference_text': 'old'})
            with self.assertRaisesRegex(ValueError, '重新保存'):
                load_saved_material_settings('synthetic_book', 'a.pdf')
            request = RequestFactory().post('/', {'files': ['a.pdf'], 'save': True,
                'material': {'reference_text': 'confirmed'}}, content_type='application/json')
            request.ci_workspace = 'synthetic_book'
            self.assertEqual(json.loads(material_settings.__wrapped__.__wrapped__(request).content)['error_num'], 0)
            self.assertEqual(load_saved_material_settings('synthetic_book', 'a.pdf')[0]['reference_text'], 'confirmed')
