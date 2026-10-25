"""跨页冻结依据/失败离线验证。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import cross_page, grader_pass1_5
from .grader_pass1 import _merge_detect_and_grade
from .feedback_skills_test import runtime_fixture
from .qwen_api_regression_test import _FakeCompletions, _fake_qwen_client


class CrossRuntimeTest(unittest.TestCase):
    def test_retry_uses_same_context(self):
        r=runtime_fixture();c=_FakeCompletions('{"corrections": []}')
        with patch.object(grader_pass1_5,'image_to_data_uri',return_value='synthetic'),_fake_qwen_client(c):
            result=grader_pass1_5.grade_cross_page_group(['synthetic'],'math',[1,2],{},feedback_runtime=r)
        self.assertIn('physics',c.calls[0]['messages'][0]['content'])
        self.assertEqual(result['feedback_execution']['config_fingerprint'],r.fingerprint)

    def test_disabled_audited(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(cross_page,'pass1_5_enabled',return_value=False):
            path=Path(tmp)/'pass1';path.mkdir()
            self.assertEqual(cross_page.resolve_cross_pages(str(path),tmp,'math','synthetic',feedback_runtime=runtime_fixture()),[])
            self.assertEqual(json.loads((Path(tmp)/'feedback_cross_page_audit.json').read_text(encoding='utf-8'))['status'],'disabled')

    def test_mismatch_rejected_without_modifying_pages(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(cross_page,'pass1_5_enabled',return_value=True),patch.object(cross_page,'_load_all_page_jsons',return_value=({1:{'page':1,'questions':[]}},{})):
            with self.assertRaisesRegex(ValueError,'配置不一致'):
                cross_page.resolve_cross_pages(str(Path(tmp)/'pass1'),tmp,'math','synthetic',feedback_runtime=runtime_fixture())

    def test_open_material_is_not_resolved_before_cross_page_pass(self):
        runtime = runtime_fixture('初中·初一·语文·作文.pdf')
        detected = {'questions': [{
            'id': 'paragraph-1', 'position': [10, 20, 900, 980],
            'stem_excerpt': '跨页作文段落', 'cross_page': True,
        }]}
        graded = {'questions': [{
            'id': 'paragraph-1', 'student_answer': '合成作文片段',
            'understanding': '该段内容延续到下一页', 'verdict': 'correct',
        }]}
        merged = _merge_detect_and_grade(
            detected, graded, 'chinese', 1, feedback_runtime=runtime,
        )
        question = merged['questions'][0]
        self.assertFalse(question.get('cross_page_resolved', False))
        self.assertTrue(cross_page._question_needs_resolution(question, merged))
