"""新能力目录与旧快照兼容；只改临时配置，不调用模型。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import feedback_capabilities as capabilities, feedback_skills as legacy, managed_feedback_rules as managed
from .feedback_runtime_service_test import RuntimeServiceTests
from .feedback_runtime_service import restore_feedback_runtime
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .feedback_skills_test import runtime_fixture
from .feedback_prompts import stage_instructions
from .stage_dependencies import configuration


class CapabilityIsolationTest(unittest.TestCase):
    def test_new_runtime_and_managed_validation_do_not_read_retired_files(self):
        factory = RuntimeServiceTests()
        original = factory.runtime('小学·四年级·数学·作业.pdf')
        with patch.object(legacy, '_read', side_effect=OSError('synthetic retired files unavailable')):
            current = factory.runtime('小学·四年级·数学·作业.pdf')
            self.assertTrue(managed.list_rules())
        self.assertEqual(original.fingerprint, current.fingerprint)
        self.assertTrue(current.has_specialized('math'))
        self.assertTrue(all(s['content']['resource_schema'] == capabilities.SCHEMA for s in current.dependencies['skills']))
        self.assertTrue(all(not s['content']['instructions'] for s in current.dependencies['skills']))
        self.assertTrue(stage_instructions(current, 'grade'))

    def test_catalog_preserves_scopes_verifiers_and_fixed_resources(self):
        old = {s['id']: s for s in legacy.load_registry()[0]}
        for new in capabilities.load_capability_registry()[0]:
            source = old[new['id']]
            self.assertEqual(source['content']['manifest'], new['content']['manifest'])
            expected = copy.deepcopy(source['content']['resources'])
            expected.pop('texts')
            actual = copy.deepcopy(new['content']['resources'])
            actual.pop('texts')
            self.assertEqual(expected, actual)

    def test_old_frozen_runtime_restores_without_any_live_registry(self):
        old = runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            args = snapshot_arguments(tmp)
            args.update(context=old.context, **old.dependencies)
            destination = Path(tmp) / 'old'
            prepare_feedback_snapshot(destination, **args)
            before = (destination / 'skill_snapshot.json').read_bytes()
            with patch.object(legacy, '_read', side_effect=OSError('retired')), \
                    patch.object(capabilities, 'CAPABILITIES_PATH', Path(tmp) / 'missing.json'):
                restored = restore_feedback_runtime(destination)
            self.assertEqual(restored.fingerprint, old.fingerprint)
            self.assertEqual((destination / 'skill_snapshot.json').read_bytes(), before)

    def test_actual_resource_change_changes_stage_basis_and_bad_verifier_fails(self):
        factory = RuntimeServiceTests()
        before = factory.runtime('小学·四年级·数学·作业.pdf')
        document = json.loads(capabilities.CAPABILITIES_PATH.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'capabilities.json'
            math = next(s for s in document['capabilities'] if s['manifest']['id'] == 'math-primary4-question')
            math['resources']['verifiers'].append('english')
            path.write_text(json.dumps(document), encoding='utf-8')
            with patch.object(capabilities, 'CAPABILITIES_PATH', path):
                after = factory.runtime('小学·四年级·数学·作业.pdf')
            self.assertNotEqual(configuration(before, 'grading'), configuration(after, 'grading'))
            math['resources']['verifiers'].append('execute_external_python')
            path.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaises(ValueError):
                capabilities.load_capability_registry(path)

    def test_managed_body_change_still_changes_consuming_stage(self):
        factory = RuntimeServiceTests()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rules.json'
            path.write_bytes(managed.RULES_PATH.read_bytes())
            with patch.object(managed, 'RULES_PATH', path):
                created = managed.save_rule({'name': '合成批改规则', 'education_levels': ['university'],
                    'grades': [2], 'subjects': [], 'material_types': ['exam'],
                    'usages': ['grading'], 'body': 'synthetic first rule'})
                before = factory.runtime()
                managed.save_rule({'id': created['id'], 'body': 'synthetic second rule'})
                after = factory.runtime()
            self.assertNotEqual(before.fingerprint, after.fingerprint)
            self.assertEqual(configuration(before, 'layout'), configuration(after, 'layout'))
            self.assertNotEqual(configuration(before, 'grading'), configuration(after, 'grading'))
