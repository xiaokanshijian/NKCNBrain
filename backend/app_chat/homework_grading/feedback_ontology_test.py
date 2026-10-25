"""诊断证据与无证据降级的合成验证。"""
import tempfile
import unittest
from unittest.mock import patch
from . import ontology_builder as o, prompts
from .feedback_skills_test import runtime_fixture


class OntologyRuntimeTest(unittest.TestCase):
    def test_no_observation_not_math_extension(self):
        r=runtime_fixture('大学·大二·嵌入式系统·作业.pdf')
        with tempfile.TemporaryDirectory() as tmp:
            result=o.build_ontology('math','synthetic',tmp,tmp,{'grade':4},[],feedback_runtime=r)
        self.assertEqual(result['status'],'insufficient_evidence')
        for items in result['zones'].values():
            self.assertEqual(items[0]['knowledge_point'],'no_observed')
            self.assertEqual(items[0]['evidence'],[])
        self.assertIsNone(result['grade'])

    def test_evidence_survives_and_fabricated_id_removed(self):
        r=runtime_fixture()
        pack={'session_timeline':[{'kp_observations':[{'evidence_question_ids':['p1:1']}]}]}
        with patch.object(o,'_valid_qids_from_pack',return_value={'p1:1'}):
            result=o._runtime_ontology({'zones':{'blind_spot':[{'knowledge_point':'force','evidence':['p1:1','p99:x']}] }},pack,r)
        self.assertEqual(result['zones']['blind_spot'][0]['evidence'],['p1:1'])
        self.assertEqual(result['zones']['zpd'][0]['knowledge_point'],'no_observed')

    def test_prompt_no_mutable_curriculum(self):
        r=runtime_fixture()
        with patch.object(prompts,'load_curriculum_entries',side_effect=AssertionError('global curriculum')):
            text=prompts.ontology_system('math',2,feedback_runtime=r)
        self.assertIn('physics',text)
        self.assertNotIn('MA_S2',text)
