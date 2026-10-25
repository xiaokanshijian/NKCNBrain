"""作文多维证据产生多值zone时的兼容与拒绝边界；不调用真实模型。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from . import grader_pass2
from .feedback_runtime import stamp_feedback
from .feedback_skills_test import runtime_fixture
from .note_evidence import normalize_feedback_zones, validate_note_feedback


class FeedbackZoneNormalizationTest(unittest.TestCase):
    def setUp(self):
        self.runtime = runtime_fixture('初中·七年级·语文·作文.pdf')
        q = {'page': 1, 'id': 'auto-1', 'qid_global': 'p1:auto-1', 'student_answer': '合成段落',
             'understanding': '段落表达清楚，可以补充个人感受。', 'verdict': 'correct'}
        self.memory = stamp_feedback({'error_questions': [q]}, self.runtime)
        self.ontology = stamp_feedback({'zones': {
            'blind_spot': [],
            'friction_zone': [{'knowledge_point': '表达组织', 'evidence': ['p1:auto-1'],
                               'evidence_basis': 'content', 'rationale': '个人感受较少。'}],
            'zpd': [{'knowledge_point': '感受深化', 'evidence': [], 'evidence_basis': 'content',
                     'error_clusters': [{'evidence': ['p1:auto-1']}], 'rationale': '可补充个人感受。'}],
        }}, self.runtime)
        self.payload = {'open_material_overview': {
            'subject_and_layout': '一页手写作文。', 'content_review': '表达清楚，可补充感受。',
            'next_steps': ['在人物事迹之后补一句个人感受。']},
            'per_question_feedback': [{'page': 1, 'id': 'auto-1', 'qid_global': 'p1:auto-1',
                'zone': 'friction_zone,zpd', 'comment': '表达清楚，可在人物事迹后补一句自己的感受。'}]}

    def test_valid_multiple_zones_preserve_comment_evidence_and_audit(self):
        original = copy.deepcopy(self.payload)
        ontology = copy.deepcopy(self.ontology)
        normalize_feedback_zones(self.payload, self.ontology)
        validate_note_feedback(self.payload, self.memory, self.ontology, material_type='composition')
        self.assertEqual(self.payload['per_question_feedback'][0]['zone'], 'friction_zone')
        self.assertEqual(self.payload['per_question_feedback'][0]['comment'], original['per_question_feedback'][0]['comment'])
        self.assertEqual(self.payload['_zone_normalizations'][0]['original_zone'], 'friction_zone,zpd')
        self.assertEqual(self.payload['_zone_normalizations'][0]['supported_zones'], ['friction_zone', 'zpd'])
        self.assertEqual(self.ontology, ontology)
        normalized = copy.deepcopy(self.payload)
        normalize_feedback_zones(self.payload, self.ontology)
        self.assertEqual(self.payload, normalized)

    def test_separators_array_and_duplicates_keep_first_supported_zone(self):
        for raw in ('zpd，friction_zone', 'zpd / friction_zone', 'zpd|friction_zone',
                    ['zpd', 'friction_zone'], 'zpd,zpd'):
            with self.subTest(raw=raw):
                payload = copy.deepcopy(self.payload)
                payload['per_question_feedback'][0]['zone'] = raw
                normalize_feedback_zones(payload, self.ontology)
                self.assertEqual(payload['per_question_feedback'][0]['zone'], 'zpd')

    def test_unsupported_zone_must_not_be_silently_dropped(self):
        for raw in ('friction_zone,blind_spot', 'friction_zone,unknown', ['zpd', 'unknown'],
                    'friction_zone,', [], {}, 7):
            with self.subTest(raw=raw):
                payload = copy.deepcopy(self.payload)
                payload['per_question_feedback'][0]['zone'] = raw
                with self.assertRaises(ValueError):
                    normalize_feedback_zones(payload, self.ontology)
                self.assertEqual(payload['per_question_feedback'][0]['zone'], raw)

    def test_single_or_empty_zone_unchanged_and_unknown_qid_rejected(self):
        for raw in ('friction_zone', '', None):
            payload = copy.deepcopy(self.payload)
            payload['per_question_feedback'][0]['zone'] = raw
            original = copy.deepcopy(payload)
            normalize_feedback_zones(payload, self.ontology)
            self.assertEqual(payload, original)
        self.payload['per_question_feedback'][0]['qid_global'] = 'p99:auto-1'
        with self.assertRaises(ValueError):
            normalize_feedback_zones(self.payload, self.ontology)

    def test_uncertain_and_annotation_protection_still_reject_false_claims(self):
        payload = copy.deepcopy(self.payload)
        payload['per_question_feedback'][0]['comment'] = '学生未掌握这一知识。'
        normalize_feedback_zones(payload, self.ontology)
        self.memory['error_questions'][0]['verdict'] = 'uncertain'
        with self.assertRaisesRegex(ValueError, '待确认'):
            validate_note_feedback(payload, self.memory, self.ontology, material_type='composition')
        self.memory['error_questions'][0]['verdict'] = 'correct'
        for entries in self.ontology['zones'].values():
            for entry in entries:
                entry['evidence_basis'] = 'annotation'
        with self.assertRaisesRegex(ValueError, '标注观察'):
            validate_note_feedback(payload, self.memory, self.ontology, material_type='composition')

    def test_pass2_accepts_compatible_model_output_once_and_persists_audit(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))])
        create = Mock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as tmp, patch.object(grader_pass2, '_deepseek_client', return_value=client):
            path = Path(tmp) / 'report.json'
            report = grader_pass2.analyze_pass2(self.memory, 'chinese', 'synthetic', str(path),
                str(Path(tmp) / 'thinking.txt'), ontology=self.ontology, feedback_runtime=self.runtime)
            saved = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(create.call_count, 1)
        self.assertEqual(report['per_question_feedback'][0]['zone'], 'friction_zone')
        self.assertEqual(len(saved['_zone_normalizations']), 1)
        self.assertEqual(report['zone_classification']['zpd'][0]['evidence_question_ids'], ['p1:auto-1'])

    def test_unsupported_combination_still_uses_failure_and_retry_path(self):
        self.payload['per_question_feedback'][0]['zone'] = 'friction_zone,blind_spot'
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.payload)))])
        create = Mock(return_value=response)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as tmp, patch.object(grader_pass2, '_deepseek_client', return_value=client):
            with self.assertRaisesRegex(ValueError, '分区与诊断证据不一致'):
                grader_pass2._call_pass2_feedback_llm(self.memory, 'chinese', 'synthetic', self.ontology,
                    str(Path(tmp) / 'thinking.txt'), feedback_runtime=self.runtime)
        self.assertEqual(create.call_count, 2)


if __name__ == '__main__':
    unittest.main()
