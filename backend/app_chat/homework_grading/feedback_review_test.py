"""合成复核请求与缓存隔离验证。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import grader_pass1_review as g
from .feedback_skills_test import runtime_fixture
from .feedback_pass1_test import PAGE


class ReviewRuntimeTest(unittest.TestCase):
    def test_page_request_and_audit(self):
        r=runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,'image_to_data_uri_for_gemini_review',return_value='synthetic'),patch.object(g,'_call_review_llm',return_value={'items':[{'id':'1','ok':True}]}) as call:
            result=g.review_page('synthetic',copy.deepcopy(PAGE),'math',1,str(Path(tmp)/'review.json'),feedback_runtime=r)
        self.assertEqual(result['feedback_execution']['config_fingerprint'],r.fingerprint)
        self.assertIs(call.call_args.kwargs['feedback_runtime'],r)
        self.assertIn('physics',call.call_args.args[0][0]['content'])

    def test_reuse_requires_fingerprint(self):
        r=runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp,patch.object(g,'pass1_review_reuse_existing',return_value=True),patch.object(g,'_review_snapshot_signature',return_value='sig'):
            path=str(Path(tmp)/'page1.json'); report_path=Path(g._review_json_path(path))
            report={'pre_review_signature':'sig','items':[]}
            report_path.write_text(json.dumps(report),encoding='utf-8')
            self.assertIsNone(g._load_reusable_review_report(path,PAGE,'physics',feedback_runtime=r))
            report['feedback_execution']=r.audit();report_path.write_text(json.dumps(report),encoding='utf-8')
            self.assertIsNotNone(g._load_reusable_review_report(path,PAGE,'physics',feedback_runtime=r))

    def test_workers_forward_same_runtime(self):
        r=runtime_fixture()
        with patch.object(g,'_review_one_page',return_value={'issues':0,'applied':0}) as call:
            g._run_review_candidates([('one','image'),('two','image')],'physics',None,None,2,False,feedback_runtime=r)
        self.assertEqual(call.call_count,2)
        self.assertTrue(all(c.kwargs['feedback_runtime'] is r for c in call.call_args_list))

    def test_unmatched_focused_skipped(self):
        report={}
        result=g._run_focused_chinese_visual_review('unused',PAGE,report,'unused',None,None,feedback_runtime=runtime_fixture())
        self.assertEqual(result,[])
        self.assertTrue(report['feedback_skips'])
