"""真实消费者＋合成模型响应；不调用模型或使用学生图像。"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import grader_pass1 as g
from .feedback_skills_test import runtime_fixture


PAGE={'page':1,'subject':'physics','questions':[{'id':'1','position':[10,10,100,100],
      'stem_excerpt':'合成协议题目','student_answer':'x','correct_answer':'y','verdict':'wrong',
      'knowledge_point':'synthetic_concept','understanding':'合成理解','error_type':'concept',
      'recognition_confidence':90,'understanding_confidence':90,'grading_confidence':90}]}


class Pass1RuntimeTest(unittest.TestCase):
    def test_all_entrypoints_use_actual_context(self):
        r=runtime_fixture();calls=[]
        def fake(messages,*args,**kwargs):
            calls.append(messages)
            return copy.deepcopy(PAGE),None
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,'image_to_data_uri',return_value='synthetic'),patch.object(g,'_call_qwen_json_with_retry',side_effect=fake),patch.object(g,'attach_fixed_english_choice_slots',side_effect=AssertionError('fixed rule without scope')):
            out=str(Path(tmp)/'page1.json')
            for flag in (False,True):
                with patch.object(g,'_pass1_two_stage_enabled',return_value=flag):
                    result=g.grade_page('synthetic','math',1,out,feedback_runtime=r)
                    self.assertEqual(result['subject'],'physics')
                    self.assertEqual(result['feedback_execution']['config_fingerprint'],r.fingerprint)
            detected=g.detect_page_only('synthetic','math',1,out,feedback_runtime=r)
            result=g.grade_page_from_detect('synthetic','math',1,out,feedback_runtime=r)
            g.supplement_detect_layout_confidence('synthetic','math',1,detected,out,force=True,feedback_runtime=r)
            g.supplement_grade_understanding_fields('synthetic','math',1,detected,PAGE,out,force=True,feedback_runtime=r)
        self.assertGreaterEqual(len(calls),7)
        for messages in calls:
            self.assertIn('physics',messages[0]['content'])
            self.assertNotIn('当前批改对象为4年级',messages[0]['content'])

    def test_model_failure_preserves_detect_evidence(self):
        r=runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,'image_to_data_uri',return_value='synthetic'),patch.object(g,'_call_qwen_json_with_retry',side_effect=ValueError('synthetic failure')):
            result=g.grade_page_questions('synthetic','math',1,copy.deepcopy(PAGE),str(Path(tmp)/'page1.json'),feedback_runtime=r)
        self.assertEqual(result['questions'][0]['id'],'1')
        self.assertEqual(result['questions'][0]['verdict'],'uncertain')
