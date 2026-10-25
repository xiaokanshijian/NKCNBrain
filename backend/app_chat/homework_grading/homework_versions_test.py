import json
import os
import tempfile
import unittest
from unittest import mock

from app_chat.homework_grading import homework_versions as versions


class HomeworkVersionsTest(unittest.TestCase):
    analysis_id = 'homework_versions_fixture'

    def test_archive_and_resume_copy_preserve_long_path_artifacts(self):
        from .utils import safe_json_dump, safe_json_load, windows_io_path
        import shutil
        root = tempfile.mkdtemp(prefix='p03-archive-long-')
        try:
            source = os.path.join(root, 'a'*80, 'b'*80, 'homework_grading')
            relative = os.path.join('pass2_report', 'math_fixture_answer_statement_verification.json')
            report = os.path.join(source, relative)
            self.assertGreater(len(os.path.abspath(report)), 260)
            safe_json_dump(report, {'audit': 'synthetic'})
            archived = os.path.join(root, 'archive', 'c'*80, 'd'*80, 'homework_grading')
            restored = os.path.join(root, 'resume', 'e'*80, 'f'*80, 'homework_grading')
            versions._copy_homework_version_workspace(source, archived)
            versions._copy_homework_version_workspace(archived, restored)
            for workspace in (source, archived, restored):
                self.assertEqual(safe_json_load(os.path.join(workspace, relative)), {'audit': 'synthetic'})
        finally:
            shutil.rmtree(windows_io_path(root))

    def _write_json(self, path, body):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(body, file, ensure_ascii=False)

    def test_current_version_uses_latest_manifest_update_time(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            versions, '_container_root', return_value=root,
        ):
            self._write_json(os.path.join(root, 'manifest.json'), {
                'created_at': '2026-07-09T17:34:03.336492',
                'updated_at': '2026-07-18T18:16:34.957650',
                'status': 'completed',
            })
            self._write_json(os.path.join(
                root,
                'homework_grading',
                'pass2_report',
                'red_blue_review.json',
            ), {
                'status': 'ready',
                'score': 4.2,
                'color': 'purple',
                'color_label': '紫·平衡',
            })
            run_id = '20260718_181504'
            os.makedirs(os.path.join(root, versions.ARCHIVES_DIR, run_id))
            self._write_json(os.path.join(
                root,
                versions.ARCHIVES_DIR,
                run_id,
                'homework_grading',
                'pass2_report',
                'red_blue_review.json',
            ), {
                'status': 'ready',
                'score': 3.8,
                'color': 'blue',
                'color_label': '蓝·证据偏重',
            })
            self._write_json(os.path.join(root, versions.ARCHIVES_DIR, versions.ARCHIVES_INDEX), {
                'versions': [{
                    'run_id': run_id,
                    'label': '历史版本 3',
                    'archived_at': '2026-07-18T18:15:05.810672',
                    'source_created_at': '2026-07-09T17:34:03.336492',
                    'status': 'completed',
                }],
            })

            result = versions.list_homework_versions('user', self.analysis_id)

        self.assertEqual(result[0]['run_id'], versions.CURRENT_RUN_ID)
        self.assertEqual(result[0]['created_at'], '2026-07-18T18:16:34.957650')
        self.assertEqual(result[1]['created_at'], '2026-07-18T18:15:05.810672')
        self.assertGreater(result[0]['created_at'], result[1]['created_at'])
        self.assertEqual(result[0]['red_blue_score'], 4.2)
        self.assertEqual(result[0]['red_blue_color'], 'purple')
        self.assertEqual(result[1]['red_blue_score'], 3.8)
        self.assertEqual(result[1]['red_blue_color'], 'blue')

    def test_current_version_falls_back_to_created_time_for_old_manifest(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            versions, '_container_root', return_value=root,
        ):
            self._write_json(os.path.join(root, 'manifest.json'), {
                'created_at': '2026-07-09T17:34:03.336492',
                'status': 'completed',
            })

            result = versions.list_homework_versions('user', self.analysis_id)

        self.assertEqual(result[0]['created_at'], '2026-07-09T17:34:03.336492')
        self.assertEqual(result[0]['red_blue_status'], 'missing')
        self.assertIsNone(result[0]['red_blue_score'])

    def test_archive_copies_only_formal_version_artifacts(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            versions, '_container_root', return_value=root,
        ):
            self._write_json(os.path.join(root, 'manifest.json'), {
                'created_at': '2026-07-27T11:20:56',
                'updated_at': '2026-07-27T11:20:56',
                'status': 'completed',
            })
            base = os.path.join(root, 'homework_grading')
            self._write_json(os.path.join(base, 'sample_meta.json'), {'subject': 'chinese'})
            self._write_json(os.path.join(base, 'iteration_context.json'), {'enabled': False})
            self._write_json(os.path.join(base, 'pass1_json', 'page1.json'), {'page': 1})
            self._write_json(os.path.join(
                base,
                'pass2_report',
                'red_blue_review.json',
            ), {
                'status': 'ready',
                'score': 3.7,
                'color': 'purple',
            })
            self._write_json(os.path.join(
                base,
                'layout_evidence',
                'slot_presence',
                'page1.presence.json',
            ), {'status': 'present'})
            self._write_json(os.path.join(
                base,
                'gemini_targeted_regression_with_a_long_workspace_name',
                'pass2_report',
                'experiment.json',
            ), {'experimental': True})

            run_id = versions.archive_homework_run_if_exists('user', self.analysis_id)
            archive = os.path.join(root, versions.ARCHIVES_DIR, run_id)

            self.assertTrue(os.path.isfile(os.path.join(archive, 'manifest.json')))
            self.assertTrue(os.path.isfile(os.path.join(
                archive,
                'homework_grading',
                'iteration_context.json',
            )))
            self.assertTrue(os.path.isfile(os.path.join(
                archive,
                'homework_grading',
                'pass2_report',
                'red_blue_review.json',
            )))
            self.assertTrue(os.path.isfile(os.path.join(
                archive,
                'homework_grading',
                'layout_evidence',
                'slot_presence',
                'page1.presence.json',
            )))
            self.assertFalse(os.path.exists(os.path.join(
                archive,
                'homework_grading',
                'gemini_targeted_regression_with_a_long_workspace_name',
            )))
            self.assertTrue(os.path.isfile(os.path.join(
                root,
                'homework_grading',
                'gemini_targeted_regression_with_a_long_workspace_name',
                'pass2_report',
                'experiment.json',
            )))
            with open(
                os.path.join(root, versions.ARCHIVES_DIR, versions.ARCHIVES_INDEX),
                'r',
                encoding='utf-8',
            ) as file:
                index = json.load(file)
            self.assertEqual([item['run_id'] for item in index['versions']], [run_id])
            self.assertFalse(any(name.startswith('.') for name in os.listdir(
                os.path.join(root, versions.ARCHIVES_DIR),
            )))

    def test_archive_copy_failure_removes_temporary_and_partial_archive(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            versions, '_container_root', return_value=root,
        ):
            self._write_json(os.path.join(root, 'manifest.json'), {
                'created_at': '2026-07-27T11:20:56',
                'status': 'completed',
            })
            self._write_json(os.path.join(
                root,
                'homework_grading',
                'pass1_json',
                'page1.json',
            ), {'page': 1})

            with mock.patch.object(
                versions,
                '_copy_homework_version_workspace',
                side_effect=OSError('copy failed'),
            ):
                with self.assertRaisesRegex(OSError, 'copy failed'):
                    versions.archive_homework_run_if_exists('user', self.analysis_id)

            archive_parent = os.path.join(root, versions.ARCHIVES_DIR)
            self.assertEqual(os.listdir(archive_parent), [])
            self.assertTrue(os.path.isfile(os.path.join(
                root,
                'homework_grading',
                'pass1_json',
                'page1.json',
            )))

    def test_archive_index_failure_removes_promoted_archive(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(
            versions, '_container_root', return_value=root,
        ):
            self._write_json(os.path.join(root, 'manifest.json'), {
                'created_at': '2026-07-27T11:20:56',
                'status': 'completed',
            })
            self._write_json(os.path.join(
                root,
                'homework_grading',
                'pass1_json',
                'page1.json',
            ), {'page': 1})

            with mock.patch.object(
                versions,
                '_save_archives_index',
                side_effect=OSError('index failed'),
            ):
                with self.assertRaisesRegex(OSError, 'index failed'):
                    versions.archive_homework_run_if_exists('user', self.analysis_id)

            self.assertEqual(os.listdir(os.path.join(root, versions.ARCHIVES_DIR)), [])


if __name__ == '__main__':
    unittest.main()
