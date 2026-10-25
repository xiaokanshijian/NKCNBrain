"""标注自问与同页已确认回答的证据角色、诊断重试及下游回归。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from . import ontology_builder as o, grader_pass2 as p, hallucination_filter as h
from .feedback_skills_test import runtime_fixture
from .feedback_runtime import stamp_feedback
from .material_markings import open_units, observation_eligible
from .note_evidence import normalize_annotation_context, validate_note_ontology, validate_note_feedback
from .utils import safe_json_dump, safe_json_load
from .memory import build_memory


class AnnotationContextTest(unittest.TestCase):
    def setUp(self):
        self.runtime = runtime_fixture('初中·七年级·数学·笔记.pdf')
        self.questions = [
            {'page': 4, 'id': 'q', 'qid_global': 'p4:q', 'note_role': 'self_question',
             'student_answer': '为什么要保留二次项？', 'verdict': 'unanswered', 'knowledge_point': '方程'},
            {'page': 4, 'id': 'a', 'qid_global': 'p4:a', 'note_role': 'written_answer',
             'student_answer': '二次项系数不为0。', 'verdict': 'correct', 'knowledge_point': '方程'},
        ]
        self.units = open_units({'error_questions': self.questions}, 'notes')
        self.pack = {'sample_meta': {}, 'open_observations': self.units, 'material_type': 'notes',
                     'session_count': 1, 'session_timeline': []}
        self.ontology = {'mastery_trajectory': [], 'evolution_narrative': '本页可见自问及回答。',
            'zones': {'blind_spot': [], 'friction_zone': [], 'zpd': [{
                'knowledge_point': '自问与回答的对应', 'evidence_basis': 'annotation',
                'evidence': ['p4:q', 'p4:a'], 'error_clusters': [],
                'rationale': '本页自问下方有对应书写。', 'suggested_next_step': '将问题和回答对应整理。'}]}}

    def test_mixed_observation_keeps_primary_and_context_roles(self):
        original_units = copy.deepcopy(self.units)
        with self.assertRaisesRegex(ValueError, '已确认内容不能作为主要标注'):
            validate_note_ontology(self.ontology, self.units)
        normalize_annotation_context(self.ontology, self.units)
        validate_note_ontology(self.ontology, self.units)
        entry = self.ontology['zones']['zpd'][0]
        self.assertEqual(entry['evidence'], ['p4:q'])
        self.assertEqual(entry['content_context_evidence'], ['p4:a'])
        self.assertEqual(self.units, original_units)
        self.assertFalse(observation_eligible(self.units[1]))
        before = copy.deepcopy(self.ontology)
        normalize_annotation_context(self.ontology, self.units)
        self.assertEqual(self.ontology, before)

    def test_invalid_context_never_bypasses_evidence_protection(self):
        for kind in ('uncertain', 'nonanswer', 'unknown', 'different_page', 'no_anchor'):
            with self.subTest(kind=kind):
                questions = copy.deepcopy(self.questions)
                ontology = copy.deepcopy(self.ontology)
                if kind == 'uncertain': questions[1]['verdict'] = 'uncertain'
                if kind == 'nonanswer': questions[1]['note_role'] = 'reading_prompt'
                if kind == 'unknown': ontology['zones']['zpd'][0]['evidence'][1] = 'p4:missing'
                if kind == 'different_page':
                    questions[1].update(page=3, qid_global='p3:a')
                    ontology['zones']['zpd'][0]['evidence'][1] = 'p3:a'
                if kind == 'no_anchor': ontology['zones']['zpd'][0]['evidence'] = ['p4:a']
                with self.assertRaises(ValueError):
                    normalize_annotation_context(ontology, open_units({'error_questions': questions}, 'notes'))

    def test_context_does_not_authorize_mastery_claim_or_error_cluster(self):
        for field, value in [('rationale', '学生已经掌握该知识'),
                             ('error_clusters', [{'cause': '作答错误', 'evidence': ['p4:q']}])]:
            ontology = copy.deepcopy(self.ontology)
            ontology['zones']['zpd'][0][field] = value
            normalize_annotation_context(ontology, self.units)
            with self.assertRaises(ValueError): validate_note_ontology(ontology, self.units)

    def test_explicit_context_validated_not_sanitized_away(self):
        normalize_annotation_context(self.ontology, self.units)
        for change in ({'content_context_evidence': ['p4:fake']},
                       {'knowledge_point': 'no_observed'}, {'evidence_basis': 'content'},
                       {'evidence': []}):
            ontology = copy.deepcopy(self.ontology)
            ontology['zones']['zpd'][0].update(change)
            with self.assertRaises(ValueError): validate_note_ontology(ontology, self.units)

    def client(self, outputs):
        responses = [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))]) for value in outputs]
        create = Mock(side_effect=responses)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))), create

    def test_l5_normalizes_and_records_original_response(self):
        raw = json.dumps(self.ontology, ensure_ascii=False)
        client, create = self.client([raw])
        with tempfile.TemporaryDirectory() as tmp, patch.object(o, '_deepseek_client', return_value=client):
            result = o._call_l5(self.pack, 'math', str(Path(tmp) / 'ontology.thinking.txt'), feedback_runtime=self.runtime)
            audit = safe_json_load(Path(tmp) / 'ontology.responses.json')
        self.assertEqual(create.call_count, 1)
        self.assertEqual(audit['attempts'][0]['raw_response'], raw)
        self.assertEqual(audit['attempts'][0]['status'], 'accepted')
        self.assertEqual(result['zones']['zpd'][0]['content_context_evidence'], ['p4:a'])

    def test_retry_contains_prior_response_and_type_guidance(self):
        invalid = copy.deepcopy(self.ontology)
        invalid['zones']['zpd'][0]['evidence'] = ['p4:a']
        first = json.dumps(invalid)
        client, create = self.client([first, json.dumps(self.ontology)])
        with tempfile.TemporaryDirectory() as tmp, patch.object(o, '_deepseek_client', return_value=client):
            o._call_l5(self.pack, 'math', str(Path(tmp) / 'ontology.thinking.txt'), feedback_runtime=self.runtime)
            audit = safe_json_load(Path(tmp) / 'ontology.responses.json')
        self.assertEqual([a['status'] for a in audit['attempts']], ['rejected', 'accepted'])
        messages = create.call_args_list[1].kwargs['messages']
        self.assertTrue(any(m['role'] == 'assistant' and m['content'] == first for m in messages))
        self.assertIn('content_context_evidence', messages[-1]['content'])

    def test_failed_response_saved_and_error_distinguishes_json_from_evidence(self):
        for raw, error_kind in [('not json', 'json'), ('[]', 'evidence')]:
            client, _ = self.client([raw, raw])
            with tempfile.TemporaryDirectory() as tmp, patch.object(o, '_deepseek_client', return_value=client):
                with self.assertRaisesRegex(ValueError, '原始返回已保存'):
                    o._call_l5(self.pack, 'math', str(Path(tmp) / 'ontology.thinking.txt'), feedback_runtime=self.runtime)
                audit = safe_json_load(Path(tmp) / 'ontology.responses.json')
                self.assertEqual(len(audit['attempts']), 2)
                self.assertEqual(audit['attempts'][-1]['error_kind'], error_kind)

    def test_response_audit_never_overwrites_custom_thinking_path(self):
        client, _ = self.client([json.dumps(self.ontology)])
        with tempfile.TemporaryDirectory() as tmp, patch.object(o, '_deepseek_client', return_value=client):
            path = Path(tmp) / 'thinking.txt'
            path.write_text('existing reasoning', encoding='utf-8')
            o._call_l5(self.pack, 'math', str(path), feedback_runtime=self.runtime)
            self.assertEqual(path.read_text(encoding='utf-8'), 'existing reasoning')
            self.assertTrue(Path(str(path) + '.responses.json').exists())

    def test_l5_to_report_filter_and_final_check_preserves_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pages = root / 'pages'; pages.mkdir()
            page = stamp_feedback({'page': 4, 'questions': copy.deepcopy(self.questions)}, self.runtime)
            safe_json_dump(pages / 'page_004.json', page)
            memory = build_memory(str(pages), 'math', 'fixture', feedback_runtime=self.runtime)
            ontology = o._runtime_ontology(copy.deepcopy(self.ontology), self.pack, self.runtime)
            # 归一化、净化后不得把辅助回答并回主要标注。
            ontology = o._sanitize_ontology_evidence(ontology, self.pack)
            validate_note_ontology(ontology, self.units)
            op = root / 'ontology.json'; safe_json_dump(op, ontology)
            payload = {'open_material_overview': {'subject_and_layout': '一页数学笔记。',
                'content_review': '有自问与相邻回答。', 'next_steps': ['对应整理问题与回答。']},
                'per_question_feedback': [{'page': 4, 'id': q['id'], 'qid_global': q['qid_global'],
                    'zone': 'zpd', 'comment': '可将本条书写与相邻的问题对应整理。'} for q in self.questions]}
            client, _ = self.client([json.dumps(payload)])
            with patch.object(p, '_deepseek_client', return_value=client):
                report = p.analyze_pass2(memory, 'math', 'fixture', str(root / 'report.json'),
                    str(root / 'feedback.thinking.txt'), ontology=ontology, feedback_runtime=self.runtime)
            entry = report['zone_classification']['zpd'][0]
            self.assertEqual(entry['evidence_question_ids'], ['p4:q', 'p4:a'])
            self.assertEqual(entry['content_context_evidence'], ['p4:a'])
            with patch.object(h, '_call_retry', side_effect=AssertionError('不应触发标签替换')) as retry:
                h.run_hallucination_filter('math', str(pages), str(root / 'report.json'), str(root / 'filter.json'),
                    ontology_path=str(op), feedback_runtime=self.runtime)
            self.assertEqual(retry.call_count, 0)
            final = safe_json_load(op)
            validate_note_ontology(final, self.units)
            validate_note_feedback(safe_json_load(root / 'report.json'), memory, final)
            self.assertEqual(final['zones']['zpd'][0]['evidence'], ['p4:q'])
            self.assertEqual(final['zones']['zpd'][0]['content_context_evidence'], ['p4:a'])
