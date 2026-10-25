"""合成页面的校验调度测试。"""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from . import verifiers as v
from .feedback_pass1_test import PAGE
from .feedback_runtime import stamp_feedback
from .feedback_skills_test import runtime_fixture
from .feedback_skill_matching import compose_skills
from .feedback_metadata import resolve_feedback_metadata
from .utils import safe_json_dump


class VerificationRuntimeTest(unittest.TestCase):
    def test_uncovered_and_invalid_identity(self):
        r=runtime_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'pass1';p.mkdir();file=p/'sample_page1.json'
            data=stamp_feedback(copy.deepcopy(PAGE),r);safe_json_dump(str(file),data)
            original=file.read_bytes()
            with patch.dict(v._VERIFIERS,{'physics':lambda *args: self.fail('uncovered verifier')}):
                report=v.verify_pass1_dir('math',str(p),str(Path(tmp)/'audit.json'),feedback_runtime=r)
            self.assertEqual(report['checks'][0]['status'],'not_covered')
            self.assertEqual(original,file.read_bytes())
            data['questions'].append(copy.deepcopy(data['questions'][0]));safe_json_dump(str(file),data)
            with self.assertRaisesRegex(ValueError,'身份'):
                v.verify_pass1_dir('math',str(p),str(Path(tmp)/'audit.json'),feedback_runtime=r)

    def test_english_dictionary_unavailable(self):
        name='小学·四年级·英语·作业.pdf';selected,_=compose_skills(resolve_feedback_metadata(name));r=runtime_fixture(name,skills=selected)
        with tempfile.TemporaryDirectory() as tmp,patch.object(v._CHECKER,'backend','none'):
            p=Path(tmp)/'pass1';p.mkdir();safe_json_dump(str(p/'sample_page1.json'),stamp_feedback(copy.deepcopy(PAGE),r))
            report=v.verify_pass1_dir('math',str(p),str(Path(tmp)/'audit.json'),feedback_runtime=r)
        self.assertTrue(any(x['status']=='unavailable' for x in report['checks']))
