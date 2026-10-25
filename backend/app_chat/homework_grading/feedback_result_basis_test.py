import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .feedback_preprocess_test import runtime
from .feedback_runtime import prepare_feedback_runtime
from .feedback_metadata import resolve_feedback_metadata
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .feedback_result_basis import result_basis
from .feedback_curriculum import curriculum_entries


class ResultBasisTest(unittest.TestCase):
    def test_result_reads_frozen_mapping_and_corrupt_snapshot_never_loads_latest(self):
        template = runtime()
        deps = template.dependencies
        selected = prepare_feedback_runtime(resolve_feedback_metadata('小学·二年级·数学·作业.pdf'),
            **{key: deps[key] for key in ('model_config', 'preprocessing', 'retrieval', 'references')})
        label = curriculum_entries(selected)[0]['label']
        point_id = curriculum_entries(selected)[0]['id']
        from .feedback_runtime import freeze_feedback_runtime
        deps = selected.dependencies
        deps['retrieval']['display_names'] = {'math': {label: '合成冻结名称'}}
        selected = freeze_feedback_runtime(selected.context, **deps)
        with tempfile.TemporaryDirectory() as tmp:
            args = snapshot_arguments(tmp)
            args.update(context=selected.context, **selected.dependencies)
            root = Path(tmp) / 'run'
            manifest = prepare_feedback_snapshot(root, **args)
            with patch('app_chat.homework_grading.feedback_result_basis.label_to_cn_map',
                       side_effect=AssertionError('不能读最新映射')):
                state, restored, names, domains = result_basis(root, manifest)
                self.assertEqual(state['snapshot_status'], 'complete')
                self.assertEqual(names[label], '合成冻结名称')
                self.assertIn(label, domains)
                self.assertEqual(names[point_id], names[label])
                self.assertEqual(domains[point_id], domains[label])
                from .service import _build_curriculum_mastery
                memory = {'knowledge_point_frequency': [
                    {'point': point_id, 'total_count': 3, 'error_count': 1},
                    {'point': label, 'total_count': 2, 'error_count': 0}]}
                mastery = _build_curriculum_mastery(memory, 'math', domains)
                self.assertEqual(len(mastery['by_domain']), 1)
                self.assertEqual(mastery['by_domain'][0]['total'], 5)
                self.assertEqual(mastery['by_domain'][0]['domain'], domains[label])
                self.assertEqual(restored.fingerprint, selected.fingerprint)
                (root / 'curriculum_snapshot.json').write_text('{}')
                state, restored, names, domains = result_basis(root, manifest)
                self.assertEqual(state['snapshot_status'], 'invalid')
                self.assertIsNone(restored)
                self.assertEqual((names, domains), ({}, {}))

    def test_university_has_no_primary_mapping(self):
        selected = runtime()
        with tempfile.TemporaryDirectory() as tmp:
            args = snapshot_arguments(tmp)
            args.update(context=selected.context, **selected.dependencies)
            root = Path(tmp) / 'run'
            manifest = prepare_feedback_snapshot(root, **args)
            state, _, names, domains = result_basis(root, manifest)
            self.assertEqual(state['feedback_context']['grade_in_level'], 2)
            self.assertEqual((names, domains), ({}, {}))


if __name__ == '__main__':
    unittest.main()
