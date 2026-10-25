"""合成范围/冲突协议，不是实际学生作业。"""
import copy
import unittest
from .feedback_skills import load_registry
from .feedback_metadata import resolve_feedback_metadata
from .feedback_skill_matching import compose_skills
from .feedback_fingerprint import content_sha256


def synthetic_special(identity='math-primary4-question'):
    s=copy.deepcopy(load_registry()[0][0]); s['id']=identity
    m=s['content']['manifest']
    m.update(id=identity,kind='specialized',subject_scope=['math'],education_scope=['primary'],
             material_scope=['homework','exam'],unit_scope=['question'],grades=[4],priority=10)
    m['rules']=[dict(m['rules'][0],id=identity+'-rule',evaluation_item='synthetic-score')]
    s['content_hash']=content_sha256(s['content'])
    return s


class MatchingTest(unittest.TestCase):
    def test_scope_matrix(self):
        skills=load_registry()[0][:1]+[synthetic_special()]
        for name, expected in [('小学·四年级·数学·作业.pdf',2),('小学·四年级·数学·试卷.pdf',2),
                              ('小学·五年级·数学·作业.pdf',1),('小学··数学·作业.pdf',1),
                              ('初中·高二·数学·作业.pdf',1),('大学·大二·数学·作业.pdf',1),
                              ('小学·四年级·数学·笔记.pdf',1),('小学·四年级·物理·作业.pdf',1)]:
            with self.subTest(name=name):
                selected,audit=compose_skills(resolve_feedback_metadata(name),skills)
                self.assertEqual(len(selected),expected)
                if expected==1:self.assertTrue(audit['excluded'])

    def test_conflict_and_narrower(self):
        meta=resolve_feedback_metadata('小学·四年级·数学·作业.pdf')
        general=load_registry()[0][:1]
        a,b=synthetic_special('a'),synthetic_special('b')
        selected,audit=compose_skills(meta,general+[a,b])
        self.assertEqual(len(selected),1);self.assertEqual(len(audit['excluded']),2)
        b['content']['manifest']['grades']=[3,4]
        selected,_=compose_skills(meta,general+[b,a])
        self.assertEqual([s['id'] for s in selected],['general-feedback','a'])

    def test_duplicate_rule_content_is_rejected(self):
        a,b=synthetic_special('a'),synthetic_special('b')
        b['content']['manifest']['rules']=copy.deepcopy(a['content']['manifest']['rules'])
        b['content']['resources']['texts']['general-evidence']='different'
        with self.assertRaisesRegex(ValueError,'重复规则'):
            compose_skills(resolve_feedback_metadata('小学·四年级·数学·作业.pdf'),load_registry()[0][:1]+[a,b])
