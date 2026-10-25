"""真实内置资源只读＋合成上下文；不验证原课标语义质量。"""
import tempfile
import unittest
from unittest.mock import patch
from .feedback_curriculum import freeze_builtin_curriculum, curriculum_entries
from .feedback_metadata import resolve_feedback_metadata
from .feedback_skills_test import runtime_fixture
from . import profile


class CurriculumRuntimeTest(unittest.TestCase):
    def test_ranges_and_frozen_content(self):
        for name in ('高中·高二·数学·作业.pdf','小学··语文·作业.pdf','大学·大二·数学·作业.pdf'):
            self.assertIsNone(freeze_builtin_curriculum(resolve_feedback_metadata(name)))
        name='小学·四年级·数学·作业.pdf'
        resource=freeze_builtin_curriculum(resolve_feedback_metadata(name))
        self.assertEqual(resource['stage_key'],'S2')
        r=runtime_fixture(name,curriculum=resource);before=curriculum_entries(r)
        resource['content']['stages'].clear()
        self.assertEqual(curriculum_entries(r),before)
        self.assertEqual(len(before),73)

    def test_mismatch_rejected(self):
        resource=freeze_builtin_curriculum(resolve_feedback_metadata('小学·四年级·数学·作业.pdf'))
        with self.assertRaises(ValueError):runtime_fixture('高中·高二·数学·作业.pdf',curriculum=resource)

    def test_no_curriculum_profile_does_not_load_global(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(profile,'label_to_id_map',side_effect=AssertionError('mutable curriculum')):
            result=profile.build_student_profile(tmp,'math','synthetic',feedback_runtime=runtime_fixture())
        self.assertEqual(result['subject'],'physics')
