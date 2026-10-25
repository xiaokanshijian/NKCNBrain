"""合成时序页面，不代表真实作答或质量。"""
import copy
import tempfile
import unittest
from pathlib import Path
from .feedback_pass1_test import PAGE
from .feedback_skills_test import runtime_fixture
from .feedback_runtime import stamp_feedback
from .memory import build_memory
from .sessions import build_all_session_memories, build_pre_pass1_session_map
from .utils import safe_json_dump, safe_json_load


class MemoryRuntimeTest(unittest.TestCase):
    def test_sequence_identity_and_subject(self):
        r=runtime_fixture('大学·大二·嵌入式系统·作业.pdf')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'pass1';p.mkdir();out=Path(tmp)/'report';out.mkdir()
            for page in (1,2):
                data=copy.deepcopy(PAGE);data['page']=page;data['questions'][0]['id']=str(page)
                safe_json_dump(str(p/f'sample_page{page}.json'),stamp_feedback(data,r))
            memory=build_memory(str(p),'math','synthetic',feedback_runtime=r)
            sessions=build_all_session_memories(str(p),str(out),'math','synthetic',feedback_runtime=r)
        self.assertEqual(memory['subject'],r.context['subject_code'])
        self.assertEqual([q['qid_global'] for q in memory['error_questions']],['p1:1','p2:2'])
        self.assertEqual((sessions[0]['page_start'],sessions[-1]['page_end']),(1,2))
        self.assertTrue(all(s['feedback_execution']['config_fingerprint']==r.fingerprint for s in sessions))

    def test_old_pages_cannot_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            safe_json_dump(str(Path(tmp)/'sample_page1.json'),PAGE)
            with self.assertRaisesRegex(ValueError,'配置'):
                build_memory(tmp,'math','synthetic',feedback_runtime=runtime_fixture())

    def test_open_material_keeps_correct_units_for_feedback_without_demotion(self):
        runtime = runtime_fixture('初中·初一·数学·笔记.pdf')
        with tempfile.TemporaryDirectory() as tmp:
            data = copy.deepcopy(PAGE)
            data['questions'][0].update(id='note-1', verdict='correct', error_type='')
            safe_json_dump(str(Path(tmp) / 'notes_page1.json'), stamp_feedback(data, runtime))
            memory = build_memory(tmp, 'math', 'synthetic', feedback_runtime=runtime)
        self.assertEqual(memory['verdict_distribution']['correct'], 1)
        self.assertEqual(memory['error_questions'][0]['qid_global'], 'p1:note-1')
        self.assertEqual(memory['error_questions'][0]['verdict'], 'correct')

    def test_composition_pages_form_one_session(self):
        runtime = runtime_fixture('初中·初一·语文·作文.pdf')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / 'clean'
            report = root / 'report'
            clean.mkdir()
            report.mkdir()
            for page in range(1, 4):
                (clean / f'composition_page{page}.png').write_bytes(b'synthetic')
            path = build_pre_pass1_session_map(
                'chinese', 'synthetic', str(root / 'composition.pdf'),
                str(clean), str(report), use_llm=False,
                feedback_runtime=runtime,
            )
            document = safe_json_load(path)
        self.assertEqual(document['session_count'], 1)
        self.assertEqual(document['sessions'][0]['page_start'], 1)
        self.assertEqual(document['sessions'][0]['page_end'], 3)
        self.assertEqual(document['sessions'][0]['split_source'], 'composition_document')
