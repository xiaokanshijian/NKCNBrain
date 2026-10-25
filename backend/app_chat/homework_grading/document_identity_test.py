import hashlib
import os
import tempfile
import unittest
from unittest import mock

from app_chat.homework_grading import service
from app_chat.homework_grading.utils import (
    resolve_source_document_sha256,
    source_document_sha256_from_artifact_path,
    write_sample_meta,
)


class HomeworkDocumentIdentityTest(unittest.TestCase):
    def test_analysis_id_is_stable_across_filename_and_mtime_changes(self):
        payload = b'%PDF-1.7\nsame logical homework\n%%EOF\n'
        expected = f'homework_{hashlib.sha256(payload).hexdigest()[:24]}'
        with tempfile.TemporaryDirectory() as tmp:
            first_path = os.path.join(tmp, 'original.pdf')
            renamed_path = os.path.join(tmp, 'renamed.pdf')
            for path in (first_path, renamed_path):
                with open(path, 'wb') as file:
                    file.write(payload)
            os.utime(first_path, (1_700_000_000, 1_700_000_000))
            os.utime(renamed_path, (1_800_000_000, 1_800_000_000))

            with mock.patch.object(
                service,
                '_resolve_user_file_path',
                side_effect=[first_path, renamed_path],
            ):
                first_id = service.build_homework_analysis_id('user', 'original.pdf')
                renamed_id = service.build_homework_analysis_id('user', 'renamed.pdf')

        self.assertEqual(first_id, expected)
        self.assertEqual(renamed_id, expected)

    def test_analysis_id_changes_when_same_size_file_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_path = os.path.join(tmp, 'first.pdf')
            second_path = os.path.join(tmp, 'second.pdf')
            with open(first_path, 'wb') as file:
                file.write(b'%PDF-1.7\nAAAA\n%%EOF')
            with open(second_path, 'wb') as file:
                file.write(b'%PDF-1.7\nBBBB\n%%EOF')
            timestamp = 1_700_000_000
            os.utime(first_path, (timestamp, timestamp))
            os.utime(second_path, (timestamp, timestamp))

            with mock.patch.object(
                service,
                '_resolve_user_file_path',
                side_effect=[first_path, second_path],
            ):
                first_id = service.build_homework_analysis_id('user', 'same.pdf')
                second_id = service.build_homework_analysis_id('user', 'same.pdf')

        self.assertNotEqual(first_id, second_id)

    def test_source_hash_is_persisted_and_resolved_from_page_artifact(self):
        source_sha256 = hashlib.sha256(b'source pdf').hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            pass1_dir = os.path.join(tmp, 'pass1_json')
            os.makedirs(pass1_dir)
            artifact_path = os.path.join(pass1_dir, 'english_any_page15.grade.json')
            write_sample_meta(
                tmp,
                'english',
                'any',
                4,
                source_document_sha256=source_sha256,
                source_filename='renamed.pdf',
            )

            resolved = source_document_sha256_from_artifact_path(artifact_path)

        self.assertEqual(resolved, source_sha256)

    def test_workspace_rejects_replaced_source_pdf(self):
        original_sha256 = hashlib.sha256(b'original pdf').hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, 'source.pdf')
            with open(source_path, 'wb') as file:
                file.write(b'replaced pdf')
            write_sample_meta(
                tmp,
                'math',
                'sample',
                4,
                source_document_sha256=original_sha256,
            )

            with self.assertRaisesRegex(ValueError, '源PDF内容已变化'):
                resolve_source_document_sha256(tmp, source_path)

    def test_first_run_rejects_pdf_that_no_longer_matches_analysis_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_path = os.path.join(tmp, 'source.pdf')
            with open(source_path, 'wb') as file:
                file.write(b'current pdf')

            with self.assertRaisesRegex(ValueError, '源PDF内容与批改任务身份不一致'):
                resolve_source_document_sha256(
                    tmp,
                    source_path,
                    expected_sha256_prefix='0' * 24,
                )
