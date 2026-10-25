"""离线提取对照，直接与旧常量逐字比较，不模拟真实判分。"""
import importlib
import unittest
from .feedback_skills import load_registry
from .feedback_skill_matching import compose_skills
from .feedback_metadata import resolve_feedback_metadata


class ExtractionTest(unittest.TestCase):
    def test_all_registered_fragments_match_source(self):
        skills,_=load_registry()
        for skill in skills[1:]:
            for rule in skill['content']['manifest']['rules']:
                filename,constant=rule['source'].split(':')
                module=importlib.import_module('app_chat.homework_grading.'+filename[:-3])
                value=getattr(module,constant.split('[')[0])
                if '[' in constant:value=value[constant.split('[')[1][:-1]]
                self.assertEqual(skill['content']['resources']['texts'][rule['text_key']],value)

    def test_registered_subject_scope(self):
        skills,_=load_registry()
        for s in skills[1:]:
            subject=s['content']['manifest']['subject_scope'][0]
            for grade,expected in [('四年级',2),('五年级',1),('',1)]:
                meta=resolve_feedback_metadata(f'小学·{grade}·{subject}·作业.pdf')
                selected,_=compose_skills(meta,skills)
                self.assertEqual(len(selected),expected)
