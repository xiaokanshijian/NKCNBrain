"""无课标知识点与非法引用的合成回归。"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import hallucination_filter as h, red_blue_review as rb
from .feedback_skills_test import runtime_fixture
from .feedback_pass1_test import PAGE
from .feedback_runtime import stamp_feedback
from .utils import safe_json_dump, safe_json_load


class FilterRuntimeTest(unittest.TestCase):
    def open_fixture(self, root, material='作文'):
        from .grader_pass2 import _build_zone_classification_from_ontology
        runtime = runtime_fixture(f'初中·七年级·语文·{material}.pdf')
        pages = root / 'pass1'
        pages.mkdir()
        page = copy.deepcopy(PAGE)
        page.update(subject='chinese')
        page['questions'][0].update(knowledge_point='读后感写作', note_role='note')
        safe_json_dump(pages / 'page_001.json', stamp_feedback(page, runtime))
        ontology = stamp_feedback({'mastery_trajectory': [], 'zones': {
            'blind_spot': [{'knowledge_point': 'no_observed', 'evidence': [], 'error_clusters': [], 'fallback': 'no_observed'}],
            'friction_zone': [{'knowledge_point': '字词书写（同音字、形近字）', 'evidence': ['p1:1'],
                              'error_clusters': [{'cause': '存在形近字误写。', 'evidence': ['p1:1']}],
                              'evidence_basis': 'content', 'rationale': '可见的书写问题。'}],
            'zpd': [{'knowledge_point': '读后感结尾的个人体会', 'evidence': ['p1:1'],
                     'evidence_basis': 'content', 'rationale': '在现有表达上补充个人体会。'}],
        }}, runtime)
        report = stamp_feedback({'zone_classification': _build_zone_classification_from_ontology(ontology),
            'diagnosis': {}, 'open_material_overview': {'next_steps': ['检查形近字。']},
            'per_question_feedback': [{'page': 1, 'id': '1', 'qid_global': 'p1:1',
                                      'zone': 'friction_zone,zpd', 'comment': '检查形近字，并补充自己的体会。'}]}, runtime)
        op, rp = root / 'ontology.json', root / 'report.json'
        safe_json_dump(op, ontology)
        safe_json_dump(rp, report)
        return runtime, pages, op, rp

    def test_open_dimensions_survive_filter_and_final_validation(self):
        from .memory import build_memory
        from .material_markings import open_units
        from .note_evidence import validate_note_ontology, validate_note_feedback, normalize_feedback_zones, align_note_report
        for material in ('作文', '笔记'):
            with self.subTest(material=material), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                runtime, pages, op, rp = self.open_fixture(root, material)
                before = safe_json_load(op)
                with patch.object(h, '_call_retry', side_effect=AssertionError('有据维度不得触发标签猜测')) as retry:
                    audit = h.run_hallucination_filter('chinese', str(pages), str(rp), str(root / 'audit.json'),
                        ontology_path=str(op), feedback_runtime=runtime)
                self.assertEqual(retry.call_count, 0)
                self.assertEqual(audit['total_issues'], 0)
                self.assertEqual(audit['corrections_applied_count'], 0)
                self.assertEqual(safe_json_load(op), before)
                memory = build_memory(str(pages), 'chinese', 'fixture', feedback_runtime=runtime)
                ontology, report = safe_json_load(op), safe_json_load(rp)
                validate_note_ontology(ontology, open_units(memory, runtime.context['material_type']))
                normalize_feedback_zones(report, ontology)
                validate_note_feedback(report, memory, ontology, material_type=runtime.context['material_type'])
                align_note_report(report)
                self.assertEqual(report['per_question_feedback'][0]['zone'], 'friction_zone')
                self.assertEqual(report['zone_classification']['friction_zone'][0]['knowledge_point'],
                                 '字词书写（同音字、形近字）')

    def test_open_report_invalid_references_are_still_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, pages, op, rp = self.open_fixture(root)
            report = safe_json_load(rp)
            item = report['zone_classification']['friction_zone'][0]
            item['evidence_question_ids'].append('p99:fake')
            item['evidence_curriculum_ids'] = ['FAKE']
            safe_json_dump(rp, report)
            with patch.object(h, '_call_retry', side_effect=AssertionError('不能猜引用')) as retry:
                audit = h.run_hallucination_filter('chinese', str(pages), str(rp), str(root / 'audit.json'),
                    ontology_path=str(op), feedback_runtime=runtime)
            self.assertEqual(retry.call_count, 0)
            item = safe_json_load(rp)['zone_classification']['friction_zone'][0]
            self.assertEqual(item['evidence_question_ids'], ['p1:1'])
            self.assertEqual(item['evidence_curriculum_ids'], [])
            self.assertEqual(audit['type_counts'], {'invalid_id': 1, 'invalid_curr_id': 1})
            self.assertTrue(Path(str(rp) + '.corrected.bak').exists())
            self.assertTrue((root / 'corrections_applied.json').exists())

    def test_invalid_ontology_cannot_authorize_new_dimension(self):
        for mutation in ('fake_evidence', 'placeholder_with_evidence'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                runtime, pages, op, rp = self.open_fixture(root)
                ontology = safe_json_load(op)
                entry = ontology['zones']['friction_zone'][0]
                if mutation == 'fake_evidence':
                    entry['evidence'] = ['p99:fake']
                else:
                    entry['knowledge_point'] = 'no_observed'
                safe_json_dump(op, ontology)
                before = op.read_bytes()
                with self.assertRaises(ValueError), patch.object(h, '_call_retry', side_effect=AssertionError('不得猜测')):
                    h.run_hallucination_filter('chinese', str(pages), str(rp), str(root / 'audit.json'),
                        ontology_path=str(op), feedback_runtime=runtime)
                self.assertEqual(op.read_bytes(), before)

    def test_report_only_dimension_does_not_enter_allowlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime, pages, op, rp = self.open_fixture(root)
            report = safe_json_load(rp)
            report['zone_classification']['zpd'][0]['knowledge_point'] = '没有诊断来源的另一维度'
            safe_json_dump(rp, report)
            with patch.object(h, '_call_retry', return_value=''):
                audit = h.run_hallucination_filter('chinese', str(pages), str(rp), str(root / 'audit.json'),
                    ontology_path=str(op), feedback_runtime=runtime)
            self.assertEqual(audit['type_counts'], {'invalid_kp': 1})
            self.assertEqual(safe_json_load(rp)['zone_classification']['zpd'][0]['knowledge_point'], '')

    def test_retry_never_maps_real_point_to_placeholder(self):
        issue = {'source': 'ontology', 'zone': 'friction_zone', 'index': 0,
                 'field': 'knowledge_point', 'value': '真实观察', 'hallucination_type': 'invalid_kp'}
        labels = {'可用知识点', 'no_observed', 'generic_extension'}
        for candidate in ('no_observed', 'generic_extension'):
            with patch.object(h, '_call_retry', return_value=candidate) as call:
                result = h.retry_field(issue, labels, {'p1:1'}, set())
            self.assertIsNone(result['new_value'])
            self.assertNotIn(candidate, call.call_args.args[0])
        with patch.object(h, '_call_retry', side_effect=AssertionError('空候选不调用模型')):
            self.assertEqual(h.retry_field(issue, {'no_observed'}, set(), set())['attempts'], 0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, pages, op, rp = self.open_fixture(root)
            before = op.read_bytes()
            applied = []
            h._pre_patch_with_retry(str(pages), str(rp), str(op),
                {h._issue_key(issue): 'no_observed'}, [issue], applied)
            self.assertEqual(op.read_bytes(), before)
            self.assertEqual(applied, [])

    def test_unregistered_point_kept_invalid_references_removed(self):
        r=runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);pages=root/'pass1';pages.mkdir()
            data=stamp_feedback(copy.deepcopy(PAGE),r);safe_json_dump(str(pages/'sample_page1.json'),data)
            report=stamp_feedback({'zone_classification':{'blind_spot':[{'knowledge_point':'synthetic_concept',
                'evidence_question_ids':['p1:1','p99:x'],'evidence_curriculum_ids':['FAKE']}], 'friction_zone':[], 'zpd':[]}},r)
            path=str(root/'report.json');safe_json_dump(path,report)
            with patch.object(h,'curriculum_index',side_effect=AssertionError('global curriculum')),patch.object(h,'get_seed_labels',side_effect=AssertionError('global labels')),patch.object(h,'_call_retry',side_effect=AssertionError('cannot guess identity')):
                result=h.run_hallucination_filter('math',str(pages),path,str(root/'audit.json'),feedback_runtime=r)
            item=safe_json_load(path)['zone_classification']['blind_spot'][0]
            self.assertEqual(item['knowledge_point'],'synthetic_concept')
            self.assertEqual(item['evidence_question_ids'],['p1:1'])
            self.assertEqual(item['evidence_curriculum_ids'],[])
            self.assertEqual(result['feedback_execution']['config_fingerprint'],r.fingerprint)

    def test_quality_failure_stamped(self):
        r=runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(rb,'build_review_evidence',return_value={}),patch.object(rb,'_call_homework_red_blue_json',side_effect=RuntimeError('synthetic failure')) as call:
            result=rb.evaluate_homework_red_blue({'base':tmp,'pass2_report':tmp},{'subject':'math'},feedback_runtime=r)
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['feedback_execution']['config_fingerprint'],r.fingerprint)
        self.assertIn('physics',call.call_args.args[0][0]['content'])
