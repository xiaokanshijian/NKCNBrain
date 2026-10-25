"""第二批：多错误修复、语义边界、显式局部结果及产物事务故障注入。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import artifact_transaction as tx, grader_pass1, grader_pass2
from .model_output import request_json_object
from .note_evidence import validate_note_feedback, normalize_note_fields
from .note_evidence_test import unit, note_ontology
from .partial_feedback import partial_feedback
from .semantic_checks import phrase_findings, evaluation_texts
from .utils import safe_json_dump, safe_json_load
from .validation_issues import ValidationIssues, issue, feedback_repair_plan, ontology_repair_plan


def response(value):
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(value)))])


class SemanticRepairTest(unittest.TestCase):
    def test_negation_quotes_hypotheses_and_assertions(self):
        for text in ('没有证据表明学生不会', '尚不能得出学生不会', '原文写着“不会”，仅为引述'):
            self.assertEqual(phrase_findings(text, '不会'), [], text)
        for text in ('不能说不是不会', '不代表不会，但是学生不会', '学生“不会”'):
            self.assertTrue(phrase_findings(text, '不会'), text)
        self.assertEqual(phrase_findings('如果学生不会，应先核实', '不会')[0]['kind'], 'ambiguous')
        self.assertEqual(list(evaluation_texts({'audit': {'comment': '学生不会'}, 'comment': '仅观察'})),
                         [('/comment', '仅观察')])

    def test_collects_multiple_units_and_preserves_valid_fields(self):
        memory = {'error_questions': [unit('p1:1', 'uncertain'), unit('p1:2', 'uncertain'), unit('p1:3')]}
        good = {'qid_global': 'p1:3', 'id': '3', 'page': 1, 'comment': '文字可见', 'zone': ''}
        original = {'per_question_feedback': [
            {'qid_global': 'p1:1', 'id': '1', 'page': 1, 'comment': '学生不会', 'zone': ''},
            {'qid_global': 'p1:2', 'id': '2', 'page': 1, 'comment': '学生未掌握', 'zone': ''}, good]}
        with self.assertRaises(ValidationIssues) as caught:
            validate_note_feedback(original, memory, note_ontology([]))
        self.assertEqual(len(caught.exception.issues), 2)
        patched = copy.deepcopy(original)
        patched['per_question_feedback'][0]['comment'] = '待确认'
        patched['per_question_feedback'][1]['comment'] = '待确认'
        patched['per_question_feedback'][2]['comment'] = '被模型意外重写'
        merged = feedback_repair_plan(original, caught.exception)['merge'](patched)
        self.assertEqual(merged['per_question_feedback'][2], good)
        validate_note_feedback(merged, memory, note_ontology([]))

    def test_local_repair_cannot_overwrite_or_remove_good_diagnosis(self):
        old = note_ontology(['p1:1'])
        old['zones']['blind_spot'].append({'evidence': ['p1:2'], 'rationale': '有效'})
        error = ValidationIssues([issue(ValueError('无依据'), '/zones/blind_spot/0')])
        plan = ontology_repair_plan(old, error)
        merged = plan['merge'](note_ontology([]))
        self.assertEqual(merged['zones']['blind_spot'], old['zones']['blind_spot'][1:])
        with self.assertRaises(ValueError):
            plan['merge']({'repairs': [{'path': '/zones/blind_spot/1', 'value': None}]})

    def test_missing_coverage_preserves_valid_entries(self):
        memory = {'error_questions': [unit('p1:1'), unit('p1:2')]}
        good = {'qid_global': 'p1:1', 'id': '1', 'page': 1, 'comment': '已核实'}
        original = {'per_question_feedback': [good]}
        with self.assertRaises(ValidationIssues) as caught:
            grader_pass2._validate_runtime_feedback(original, memory)
        replacement = {'per_question_feedback': [dict(good, comment='意外改写'),
                       {'qid_global': 'p1:2', 'id': '2', 'page': 1, 'comment': '新增'}]}
        result = feedback_repair_plan(original, caught.exception)['merge'](replacement)
        self.assertEqual(result['per_question_feedback'][0], good)

    def test_partial_has_placeholder_and_audit_but_all_bad_fails(self):
        memory = {'error_questions': [unit('p1:1'), unit('p1:2')]}
        good = {'qid_global': 'p1:1', 'id': '1', 'page': 1, 'comment': '已核实'}
        original = {'per_question_feedback': [good]}
        error = ValidationIssues([issue(ValueError('缺失'), '/per_question_feedback')])
        result = partial_feedback(original, error, memory, lambda *_: None)
        self.assertEqual(result['per_question_feedback'][0], good)
        self.assertEqual(result['per_question_feedback'][1]['feedback_status'], 'needs_review')
        self.assertEqual(result['content_validation']['status'], 'needs_review')
        grader_pass2._validate_runtime_feedback(result, memory)
        self.assertIsNone(partial_feedback({'per_question_feedback': []}, error, memory, lambda *_: None))

    def test_request_audits_paths_and_merges_patch(self):
        original = {'per_question_feedback': [{'qid_global': 'p1:1', 'comment': ''},
                                             {'qid_global': 'p1:2', 'comment': '保留'}]}
        def validate(data):
            if not data['per_question_feedback'][0]['comment']:
                raise ValidationIssues([issue(ValueError('空白'), '/per_question_feedback/0/comment')])
            return data
        responses = iter([original, {'repairs': [{'path': '/per_question_feedback/0/comment', 'value': '修复'}]}])
        with tempfile.TemporaryDirectory() as tmp:
            audit = Path(tmp) / 'audit.json'
            result = request_json_object(lambda _: response(next(responses)), [], parser=json.loads,
                validate=validate, audit_path=audit, stage='synthetic', repair_plan=feedback_repair_plan)
            self.assertEqual(result['per_question_feedback'][1]['comment'], '保留')
            self.assertEqual(safe_json_load(audit)['attempts'][1]['repair_paths'], ['/per_question_feedback/0/comment'])

    def test_pass1_duplicates_and_missing_ids_retry_before_merge(self):
        for questions in ([{'id': '1'}, {'id': '1'}], [{'id': '1'}], [{'id': '1'}, {'id': '3'}]):
            with patch.object(grader_pass1, '_call_qwen_json', side_effect=[
                    response({'questions': questions}), response({'questions': [{'id': '1'}, {'id': '2'}]})]) as call:
                result, _ = grader_pass1._call_qwen_json_with_retry([], {}, expected_question_ids=['1', '2'])
            self.assertEqual(len(result['questions']), 2)
            self.assertEqual(call.call_count, 2)


class ArtifactTransactionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.paths = {'base': str(self.base)}
        for name in ('pass1_json', 'pass2_report'):
            (self.base / name).mkdir()
            self.paths[name] = str(self.base / name)
        self.target = self.base / 'pass1_json/page_1.json'
        self.target.write_bytes(b'{"original": 1}\n')
        self.before = self.target.read_bytes()

    def operation(self, paths):
        safe_json_dump(Path(paths['pass1_json']) / 'page_1.json', {'modified': True})
        safe_json_dump(Path(paths['pass2_report']) / 'report.json', {'candidate': True})
        return 'validated'

    def test_rejected_candidate_keeps_original_exact_bytes(self):
        def reject(paths):
            self.operation(paths)
            raise ValueError('事实改变，诊断过期')
        with self.assertRaises(ValueError):
            tx.candidate_transaction(self.paths, reject)
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertFalse((self.base / 'pass2_report/report.json').exists())

    def test_publish_failure_rolls_back_and_next_attempt_succeeds(self):
        publish = tx._publish
        failed = False
        def fail_once(path, data):
            nonlocal failed
            if Path(path) == self.base / 'pass2_report/report.json' and not failed:
                failed = True
                raise OSError('synthetic disk error')
            return publish(path, data)
        with patch.object(tx, '_publish', side_effect=fail_once), self.assertRaises(OSError):
            tx.candidate_transaction(self.paths, self.operation)
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertFalse(tx.transaction_pending(self.base))
        self.assertEqual(tx.candidate_transaction(self.paths, self.operation), 'validated')

    def test_process_interruption_recovers_before_next_read(self):
        publish = tx._publish
        def interrupt(path, data):
            if Path(path) == self.base / 'pass2_report/report.json':
                raise KeyboardInterrupt('synthetic crash')
            return publish(path, data)
        with patch.object(tx, '_publish', side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            tx.candidate_transaction(self.paths, self.operation)
        self.assertTrue(tx.transaction_pending(self.base))
        tx.recover_transaction(self.base)
        self.assertEqual(self.target.read_bytes(), self.before)
        self.assertFalse(tx.transaction_pending(self.base))

    def test_journal_cannot_restore_outside_run(self):
        safe_json_dump(self.base / tx.JOURNAL, {'status': 'publishing', 'files': [
            {'target': '../outside.json', 'before': None}]})
        with self.assertRaises(ValueError):
            tx.recover_transaction(self.base)


if __name__ == '__main__':
    unittest.main()
