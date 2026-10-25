import json
import os
import tempfile
import shutil
import unittest
from unittest import mock

from app_chat.homework_grading import homework_versions as versions
from app_chat.homework_grading import staged_pipeline as pipeline


class HomeworkSessionRerunTest(unittest.TestCase):
    analysis_id = 'homework_abcdefgh_fixture'

    def test_prepare_in_unpublished_copy_never_mutates_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = os.path.join(tmp, 'current')
            clone = os.path.join(tmp, 'unpublished')
            os.makedirs(original)
            self._fixture(original)
            shutil.copytree(original, clone)
            with mock.patch.object(versions, '_analysis_root', side_effect=AssertionError('不能回读当前目录')):
                plan = versions.prepare_homework_session_rerun('synthetic', self.analysis_id,
                    'layout', session_ids=['s1'], workspace_root=clone)
            self.assertEqual(plan['scope_page_nums'], [1])
            relative = os.path.join('homework_grading', 'pass1_json', 'math_abcdefgh_page1.detect.json')
            self.assertTrue(os.path.isfile(os.path.join(original, relative)))
            self.assertFalse(os.path.isfile(os.path.join(clone, relative)))

    def _write_json(self, path, body):
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(body, file, ensure_ascii=False)

    def _fixture(self, root):
        base = os.path.join(root, 'homework_grading')
        for name in ('raw', 'clean', 'pass1_json', 'pass1_u1_shadow', 'layout_evidence', 'pass2_report', 'annotated', 'annotated_layout', 'annotated_understanding'):
            os.makedirs(os.path.join(base, name), exist_ok=True)
        for name in ('layout', 'transcription'):
            os.makedirs(os.path.join(base, 'pass1_u1_shadow', name), exist_ok=True)
        os.makedirs(os.path.join(base, 'layout_evidence', 'slot_presence'), exist_ok=True)
        self._write_json(os.path.join(root, 'manifest.json'), {
            'subject': 'math',
            'status': 'completed',
            'stages': {'layout': 'done', 'understanding': 'done', 'grading': 'done'},
            'red_blue_review': {'status': 'ready', 'score': 4.2, 'color': 'purple'},
        })
        self._write_json(os.path.join(base, 'iteration_context.json'), {
            'enabled': True,
            'source_run_id': 'history_1',
        })
        self._write_json(os.path.join(base, 'pass2_report', 'red_blue_review.json'), {
            'status': 'ready',
            'score': 4.2,
            'color': 'purple',
        })
        sessions = {
            'sessions': [
                {'session_id': 's1', 'session_index': 1, 'order_index': 1, 'session_title': '第一篇', 'page_start': 1, 'page_end': 1},
                {'session_id': 's2', 'session_index': 2, 'order_index': 2, 'session_title': '第二篇', 'page_start': 2, 'page_end': 2},
            ],
        }
        self._write_json(os.path.join(base, 'pass2_report', 'math_abcdefgh_sessions.json'), sessions)
        for page in (1, 2):
            name = f'math_abcdefgh_page{page}'
            for directory, suffix in (
                ('raw', '.png'), ('clean', '.png'), ('annotated', '.png'),
                ('annotated_layout', '.png'), ('annotated_understanding', '.png'),
                ('pass1_json', '.detect.json'), ('pass1_json', '.grade.json'),
                ('pass1_json', '.review.json'), ('pass1_json', '.json'),
            ):
                path = os.path.join(base, directory, name + suffix)
                if directory == 'pass1_json' and suffix == '.json':
                    self._write_json(path, {'page': page, 'boundary': {}, 'questions': []})
                else:
                    with open(path, 'wb') as file:
                        file.write(b'fixture')
            for suffix in ('.u1.json', '.u1.error.txt'):
                with open(os.path.join(base, 'pass1_u1_shadow', name + suffix), 'wb') as file:
                    file.write(b'fixture')
            for directory, suffix in (('layout', '.layout.json'), ('transcription', '.u1.json')):
                with open(os.path.join(base, 'pass1_u1_shadow', directory, name + suffix), 'wb') as file:
                    file.write(b'fixture')
            with open(
                os.path.join(base, 'layout_evidence', 'slot_presence', name + '.presence.json'),
                'wb',
            ) as file:
                file.write(b'fixture')
        self._write_json(os.path.join(base, 'pass1_u1_shadow', 'summary.json'), {'enabled': True})
        self._write_json(
            os.path.join(base, 'layout_evidence', 'slot_presence', 'summary.json'),
            {'enabled': True},
        )
        return base

    def test_selected_layout_invalidates_only_selected_pages_and_can_resume(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root):
            base = self._fixture(root)
            prepared = versions.prepare_homework_session_rerun(
                'user', self.analysis_id, 'layout', session_ids=['s1'], archived_run_id='history_1',
            )

            self.assertEqual(prepared['effective_session_ids'], ['s1'])
            self.assertEqual(prepared['remaining_session_ids'], ['s2'])
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_json', 'math_abcdefgh_page1.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_json', 'math_abcdefgh_page1.detect.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_json', 'math_abcdefgh_page1.grade.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_json', 'math_abcdefgh_page2.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_json', 'math_abcdefgh_page2.grade.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'annotated_layout', 'math_abcdefgh_page1.png')))
            self.assertTrue(os.path.exists(os.path.join(base, 'annotated_layout', 'math_abcdefgh_page2.png')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'math_abcdefgh_page1.u1.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'math_abcdefgh_page2.u1.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'layout', 'math_abcdefgh_page1.layout.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'layout', 'math_abcdefgh_page2.layout.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'transcription', 'math_abcdefgh_page1.u1.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'transcription', 'math_abcdefgh_page2.u1.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'summary.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'layout_evidence', 'slot_presence', 'math_abcdefgh_page1.presence.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'layout_evidence', 'slot_presence', 'math_abcdefgh_page2.presence.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'layout_evidence', 'slot_presence', 'summary.json')))

            plan = versions.complete_homework_session_rerun('user', self.analysis_id)
            self.assertEqual(plan['completed_session_ids'], ['s1'])
            self.assertTrue(plan['resume_available'])

            resumed = versions.prepare_homework_session_rerun(
                'user', self.analysis_id, 'layout', resume=True,
            )
            self.assertTrue(resumed['is_resume'])
            self.assertEqual(resumed['effective_session_ids'], ['s2'])
            self.assertEqual(resumed['remaining_session_ids'], [])

    def test_session_id_validation_rejects_empty_duplicate_and_unknown_values(self):
        sessions = [{'session_id': 's1'}, {'session_id': 's2'}]
        with self.assertRaisesRegex(ValueError, '空篇目'):
            versions._validate_session_ids([''], sessions)
        with self.assertRaisesRegex(ValueError, '重复'):
            versions._validate_session_ids(['s1', 's1'], sessions)
        with self.assertRaisesRegex(ValueError, '未知'):
            versions._validate_session_ids(['missing'], sessions)

    def test_grading_rerun_preserves_u1_shadow(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root):
            base = self._fixture(root)
            versions.invalidate_homework_stage_for_rerun(
                'user', self.analysis_id, 'grading', page_nums=[1],
            )
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'math_abcdefgh_page1.u1.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'layout', 'math_abcdefgh_page1.layout.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'transcription', 'math_abcdefgh_page1.u1.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'summary.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'layout_evidence', 'slot_presence', 'math_abcdefgh_page1.presence.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass2_report', 'red_blue_review.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'iteration_context.json')))
            with open(os.path.join(root, 'manifest.json'), 'r', encoding='utf-8') as file:
                manifest = json.load(file)
            self.assertNotIn('red_blue_review', manifest)

    def test_understanding_rerun_preserves_layout_and_clears_transcription(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.object(versions, '_analysis_root', return_value=root):
            base = self._fixture(root)
            versions.invalidate_homework_stage_for_rerun(
                'user', self.analysis_id, 'understanding', page_nums=[1],
            )
            self.assertTrue(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'layout', 'math_abcdefgh_page1.layout.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'transcription', 'math_abcdefgh_page1.u1.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'math_abcdefgh_page1.u1.json')))
            self.assertFalse(os.path.exists(os.path.join(base, 'pass1_u1_shadow', 'summary.json')))
            self.assertTrue(os.path.exists(os.path.join(base, 'layout_evidence', 'slot_presence', 'math_abcdefgh_page1.presence.json')))

    def test_scoped_understanding_keeps_prior_unselected_session_as_context(self):
        pages = [
            {'page': 1, 'clean_abs_path': 'page1.png'},
            {'page': 2, 'clean_abs_path': 'page2.png'},
        ]
        session_map = {
            'sessions': [
                {'session_id': 's1', 'session_index': 1, 'order_index': 1, 'page_start': 1, 'page_end': 1},
                {'session_id': 's2', 'session_index': 2, 'order_index': 2, 'page_start': 2, 'page_end': 2},
            ],
        }
        observed_prior_pages = []
        def capture_prior(_pass1_dir, completed_page_nums, *_args):
            observed_prior_pages.append(set(completed_page_nums))
            return None

        with mock.patch.object(pipeline, '_grade_page_job', return_value={'page': 2}) as grade_page, \
             mock.patch.object(pipeline, '_update_task'), \
             mock.patch.object(pipeline, '_build_prior_summary', side_effect=capture_prior):
            pipeline._run_pass1_grade_all_pages(
                'task', pages, {'pass1_json': 'unused'}, 'math', 4, 2, 1,
                session_map, 10, 0, scope_page_nums={2},
            )

        self.assertEqual(grade_page.call_count, 1)
        self.assertEqual(grade_page.call_args.args[0]['page'], 2)
        self.assertEqual(observed_prior_pages, [{1}])


if __name__ == '__main__':
    unittest.main()
