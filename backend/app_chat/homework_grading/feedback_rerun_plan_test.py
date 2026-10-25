import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .feedback_preprocess_test import runtime
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .feedback_rerun_plan import choose_rerun_runtime


class RerunPlanTest(unittest.TestCase):
    def prepare(self, tmp):
        frozen = runtime()
        args = snapshot_arguments(tmp)
        args.update(context=frozen.context, **frozen.dependencies)
        root = Path(tmp) / 'run'
        prepare_feedback_snapshot(root, **args)
        return root, frozen

    def test_default_and_equivalent_alias_inherit_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, frozen = self.prepare(tmp)
            with patch('app_chat.homework_grading.feedback_rerun_plan.execution_configuration',
                       side_effect=AssertionError('默认不能加载最新配置')):
                restored, plan = choose_rerun_runtime(root, '试卷.pdf', {'rerun_stage': 'understanding'})
                self.assertEqual(restored.fingerprint, frozen.fingerprint)
                self.assertTrue(plan['clone'])
                aliased, _ = choose_rerun_runtime(root, '试卷.pdf', {'feedback_overrides': {'grade': '大2'}})
                self.assertEqual(aliased.fingerprint, frozen.fingerprint)

    def test_changed_basis_requires_whole_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, frozen = self.prepare(tmp)
            for change in ({'reference_text': '合成新资料'}, {'preprocess_mode': 'off'},
                           {'feedback_overrides': {'grade': '大三'}}):
                with self.subTest(change=change):
                    updated, plan = choose_rerun_runtime(root, '试卷.pdf', change)
                    self.assertNotEqual(updated.fingerprint, frozen.fingerprint)
                    self.assertFalse(plan['clone'])
                    with self.assertRaises(ValueError):
                        choose_rerun_runtime(root, '试卷.pdf', dict(change, session_ids=['s1']))
                    with self.assertRaises(ValueError):
                        choose_rerun_runtime(root, '试卷.pdf', dict(change, resume=True))

    def test_missing_snapshot_and_invalid_resource_cannot_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                choose_rerun_runtime(tmp, '试卷.pdf', {'resume': True})
            root, _ = self.prepare(tmp)
            with self.assertRaises(ValueError):
                choose_rerun_runtime(root, '试卷.pdf', {'curriculum_selection': {'resource_id': 'unsupported'}})
            with self.assertRaises(ValueError):
                choose_rerun_runtime(root, '试卷.pdf', {'resume': True, 'session_ids': ['s1']})
