"""错误响应、普通材料重试及审计回放；全部模型调用均为合成返回。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

from . import grader_pass1, grader_pass1_5, grader_pass1_review, grader_pass2, ontology_builder, pass3
from .feedback_runtime import stamp_feedback
from .feedback_skills_test import runtime_fixture
from .model_output import ModelOutputError, request_json_object


def response(value, *, finish='stop', raw=False):
    return NS(choices=[NS(finish_reason=finish, message=NS(
        content=value if raw else json.dumps(value, ensure_ascii=False), reasoning_content='合成思考'))])


def client(create):
    return NS(chat=NS(completions=NS(create=create)))


class ModelOutputTest(unittest.TestCase):
    def test_bad_envelopes_and_non_objects_retry_and_keep_both_returns(self):
        invalid = [NS(choices=[]), NS(choices=[NS(message=None)]), response(None), response([]),
                   response(''), response('broken', raw=True), response({'bad': float('nan')}), response({}, finish='length'),
                   NS(choices=[NS(message=NS(content=[{'text': 'wrong shape'}]))])]
        for first in invalid:
            with self.subTest(first=first), tempfile.TemporaryDirectory() as tmp:
                path = str(Path(tmp) / 'responses.json')
                call = Mock(side_effect=[first, response({'ok': True})])
                result = request_json_object(call, [], parser=json.loads, validate=lambda x: x,
                                             audit_path=path, stage='合成')
                records = json.loads(Path(path).read_text(encoding='utf-8'))['attempts']
                self.assertEqual(result, {'ok': True})
                self.assertEqual(call.call_count, 2)
                self.assertEqual([x['status'] for x in records], ['rejected', 'accepted'])
                self.assertIn('raw_response', records[0])
                self.assertIn('上次输出', call.call_args.args[0][-1]['content'])

    def test_exhaustion_is_bounded_and_keeps_all_attempts_across_invocations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'responses.json')
            call = Mock(return_value=response([]))
            with self.assertRaises(ModelOutputError):
                request_json_object(call, [], parser=json.loads, validate=lambda x: x,
                                    audit_path=path, stage='合成')
            self.assertEqual(call.call_count, 2)
            request_json_object(Mock(return_value=response({})), [], parser=json.loads,
                                validate=lambda x: x, audit_path=path, stage='合成')
            records = json.loads(Path(path).read_text(encoding='utf-8'))['attempts']
            self.assertEqual(len(records), 3)
            self.assertNotEqual(records[0]['invocation_id'], records[2]['invocation_id'])

    def test_transport_failure_is_audited_without_additional_retry_or_sensitive_error_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'responses.json')
            call = Mock(side_effect=TimeoutError('synthetic-sensitive-token'))
            with self.assertRaises(TimeoutError):
                request_json_object(call, [], parser=json.loads, validate=lambda x: x,
                                    audit_path=path, stage='合成')
            audit = Path(path).read_text(encoding='utf-8')
            self.assertEqual(call.call_count, 1)
            self.assertIn('call_failed', audit)
            self.assertNotIn('synthetic-sensitive-token', audit)

    def test_unexpected_validator_bug_is_not_retried_and_keeps_raw_response(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'responses.json')
            call = Mock(return_value=response({'value': 'kept'}))
            with self.assertRaises(AttributeError):
                request_json_object(call, [], parser=json.loads,
                    validate=Mock(side_effect=AttributeError('synthetic bug')),
                    audit_path=path, stage='合成')
            record = json.loads(Path(path).read_text(encoding='utf-8'))['attempts'][0]
            self.assertEqual(call.call_count, 1)
            self.assertEqual(json.loads(record['raw_response']), {'value': 'kept'})
            self.assertEqual(record['status'], 'validation_failed')

    def test_audit_write_failure_does_not_repeat_model_call(self):
        call = Mock(return_value=response({}))
        with patch('app_chat.homework_grading.model_output.safe_json_dump', side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                request_json_object(call, [], parser=json.loads, validate=lambda x: x,
                                    audit_path='synthetic.json', stage='合成')
        self.assertEqual(call.call_count, 1)

    def test_pass2_open_and_ordinary_materials_repair_structure_and_coverage_inside_retry(self):
        for filename in ('高中·高二·物理·作业.pdf', '初中·七年级·语文·作文.pdf', '初中·七年级·历史·笔记.pdf'):
            runtime = runtime_fixture(filename)
            memory = stamp_feedback({'error_questions': [{'qid_global': 'p1:1', 'id': '1', 'page': 1,
                'student_answer': '合成', 'verdict': 'correct', 'note_role': 'note'}]}, runtime)
            ontology = stamp_feedback({'zones': {'blind_spot': [], 'friction_zone': [], 'zpd': []}}, runtime)
            valid = {'per_question_feedback': [{'qid_global': 'p1:1', 'page': 1, 'id': '1',
                'zone': '', 'comment': '合成观察。'}], 'open_material_overview': {
                'subject_and_layout': '合成材料。', 'content_review': '可辨识。', 'next_steps': ['核对原文。']}}
            for first in ([], None, {**valid, 'per_question_feedback': [None]},
                          {**valid, 'per_question_feedback': []},
                          {**valid, 'per_question_feedback': [{**valid['per_question_feedback'][0], 'page': 2}]}):
                with self.subTest(filename=filename, first=first), tempfile.TemporaryDirectory() as tmp:
                    create = Mock(side_effect=[response(first), response(valid)])
                    with patch.object(grader_pass2, '_deepseek_client', return_value=client(create)):
                        saved = grader_pass2.analyze_pass2(memory, 'math', 'synthetic', str(Path(tmp)/'report.json'),
                            str(Path(tmp)/'output.thinking.txt'), ontology=ontology, feedback_runtime=runtime)
                    self.assertEqual(create.call_count, 2)
                    self.assertEqual(len(saved['per_question_feedback']), 1)
                    records = json.loads(next(Path(tmp).glob('*.responses.json')).read_text(encoding='utf-8'))['attempts']
                    self.assertEqual([x['status'] for x in records], ['rejected', 'accepted'])

    def test_l5_nested_schema_errors_repair_before_evidence_consumers(self):
        valid = {'zones': {'blind_spot': [], 'friction_zone': [], 'zpd': []}}
        for first in ([], {'zones': []}, {'zones': {'zpd': [None]}},
                      {'zones': {'zpd': [{'error_clusters': ['invalid']}]}},
                      {'zones': {'zpd': [{'knowledge_point': {}}]}},
                      {**valid, 'evolution_narrative': {}}, {**valid, 'mastery_trajectory': [None]}):
            with self.subTest(first=first), tempfile.TemporaryDirectory() as tmp:
                create = Mock(side_effect=[response(first), response(valid)])
                with patch.object(ontology_builder, '_deepseek_client', return_value=client(create)), \
                        patch.object(ontology_builder, 'ontology_system', return_value='synthetic'), \
                        patch.object(ontology_builder, 'ontology_user', return_value='synthetic'):
                    result = ontology_builder._call_l5({'sample_meta': {}}, 'math', str(Path(tmp)/'ontology.thinking.txt'))
                self.assertEqual(result, valid)
                self.assertEqual(create.call_count, 2)

    def test_pass1_review_and_cross_page_share_envelope_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(grader_pass1, '_call_qwen_json', side_effect=[NS(choices=[]), response({'questions': []})]) as call:
                data, message = grader_pass1._call_qwen_json_with_retry([], {}, error_dump_path=str(Path(tmp)/'detect.error.txt'))
                self.assertEqual(data, {'questions': []})
                self.assertEqual(message.reasoning_content, '合成思考')
                self.assertEqual(call.call_count, 2)
            with patch.object(grader_pass1_review, '_call_homework_gemini_json', side_effect=[response({'items': [None]}), response({'items': []})]) as call:
                grader_pass1_review._call_review_llm([], error_dump_path=str(Path(tmp)/'review.error.txt'))
                self.assertEqual(call.call_count, 2)
            with patch.object(grader_pass1_5, '_call_qwen_json', side_effect=[response(None), response({'corrections': []})]) as call:
                grader_pass1_5.grade_cross_page_group([], 'math', [1, 2], {}, audit_path=str(Path(tmp)/'cross.responses.json'))
                self.assertEqual(call.call_count, 2)
            self.assertEqual(len(list(Path(tmp).glob('*.responses.json'))), 3)

    def test_review_quota_detection_survives_audited_exception_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(grader_pass1_review,
                '_call_homework_gemini_json', side_effect=RuntimeError('RESOURCE_EXHAUSTED quota')):
            with self.assertRaises(ModelOutputError) as caught:
                grader_pass1_review._call_review_llm([], error_dump_path=str(Path(tmp)/'review.error.txt'))
            self.assertTrue(grader_pass1_review._is_gemini_quota_error(caught.exception))

    def test_pass3_invalid_items_do_not_fail_after_report_write(self):
        valid = {'transfer_links': [], 'habit_diagnosis': [], 'priority': [], 'summary': '合成摘要。'}
        invalid = copy.deepcopy(valid)
        invalid['priority'] = [None]
        with tempfile.TemporaryDirectory() as tmp:
            create = Mock(side_effect=[response(invalid), response(valid)])
            with patch.object(pass3, '_deepseek_client', return_value=client(create)):
                pass3.cross_subject_analyze('synthetic', 'math', 'chinese', {}, {}, {}, {}, tmp)
            self.assertEqual(create.call_count, 2)
            self.assertTrue((Path(tmp)/'summary.md').is_file())


if __name__ == '__main__':
    unittest.main()
