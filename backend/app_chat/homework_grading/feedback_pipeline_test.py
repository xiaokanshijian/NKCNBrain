"""P02 串联协议夹具：真实消费者、临时合成图像，仅替代外部模型客户端。

所有答案和质量分均为模型响应夹具，不属于人工判题或真实质量验收。
"""
import copy
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from . import (llm_clients, grader_pass1, grader_pass1_review, cross_page, sessions,
               memory, profile, ontology_builder, grader_pass2, hallucination_filter,
               red_blue_review, verifiers, render)
from .feedback_metadata import resolve_feedback_metadata
from .feedback_runtime import prepare_feedback_runtime, FrozenFeedbackRuntime
from .feedback_skills_test import runtime_fixture
from .feedback_pass1_test import PAGE
from .feedback_prompts import context_block
from .red_blue_review_test import _raw_review
from .utils import safe_json_load


class SyntheticClient:
    def __init__(self):
        self.payload = {}
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content=json.dumps(self.payload, ensure_ascii=False), reasoning_content=''))])


class OfflinePipelineTest(unittest.TestCase):
    def test_actual_cross_page_resolution_and_fake_target(self):
        from .feedback_runtime import freeze_feedback_runtime, stamp_feedback
        from .utils import safe_json_dump
        r = runtime_fixture()
        deps = r.dependencies
        deps['preprocessing']['environment'] = {'HOMEWORK_PASS1_5_ENABLED':'1'}
        r = freeze_feedback_runtime(r.context, **deps)
        with tempfile.TemporaryDirectory() as tmp:
            pass1 = Path(tmp)/'pass1'
            pass1.mkdir()
            for n in (1, 2):
                page = dict(copy.deepcopy(PAGE), page=n, boundary={'continues_to_next':n==1,'continues_from_prev':n==2})
                page['questions'][0].update(verdict='uncertain', cross_page=True)
                safe_json_dump(str(pass1/f'fixture_page{n}.json'), stamp_feedback(page, r))
                Image.new('RGB', (100,100), 'white').save(Path(tmp)/f'fixture_page{n}.png')
            client = SyntheticClient()
            client.payload = {'corrections':[
                {'page':1, 'id':'1', 'verdict':'wrong', 'correct_answer':'y'},
                {'page':1, 'id':'missing', 'verdict':'correct'}]}
            with patch.object(llm_clients, '_qwen_client', return_value=client):
                cross_page.resolve_cross_pages(str(pass1), tmp, 'math', 'fixture', feedback_runtime=r)
            page = safe_json_load(str(pass1/'fixture_page1.json'))
            self.assertEqual(len(page['questions']), 1)
            self.assertEqual(page['questions'][0]['verdict'], 'wrong')
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(safe_json_load(str(Path(tmp)/'feedback_cross_page_audit.json'))['status'], 'completed')

    def test_actual_consumers_matrix(self):
        names = ['高中·高二·物理·试卷.pdf', '初中·初二·物理·作业.pdf',
                 '大学·大二·嵌入式系统·作业.pdf', '小学·四年级·数学·作业.pdf',
                 '小学·四年级·语文·试卷.pdf', '小学·四年级·英语·作业.pdf']
        for name in names:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
                config = runtime_fixture().dependencies
                runtime = prepare_feedback_runtime(resolve_feedback_metadata(name),
                    **{k: config[k] for k in ('model_config', 'preprocessing', 'retrieval', 'references')})
                # 冻结序列化可跨进程重建；调用链使用同一规范指纹。
                runtime = FrozenFeedbackRuntime(runtime._json)
                subject = runtime.context['subject_code']
                dirs = {k: str(Path(tmp)/k) for k in ('pass1_json', 'clean', 'pass2_report')}
                for p in dirs.values(): Path(p).mkdir()
                dirs['base'] = tmp
                image = str(Path(dirs['clean'])/'fixture_page1.png')
                Image.new('RGB', (600, 800), 'white').save(image)
                client = SyntheticClient()
                stack.enter_context(patch.object(llm_clients, '_qwen_client', return_value=client))
                stack.enter_context(patch.object(llm_clients, '_homework_review_client_and_model',
                    return_value=(client, 'synthetic-review', False)))
                stack.enter_context(patch.object(llm_clients, '_homework_red_blue_client', return_value=client))
                for module in (llm_clients, ontology_builder, grader_pass2):
                    stack.enter_context(patch.object(module, '_deepseek_client', return_value=client))
                stack.enter_context(patch.dict('os.environ', {'NKCN_HOMEWORK_PASS1_SELF_REVIEW':'1'}))
                client.payload = {'sessions':[{'start_page':1, 'end_page':1, 'session_title':'合成协议篇目'}]}
                session_path = sessions.build_pre_pass1_session_map(subject, 'fixture',
                    str(Path(tmp)/'absent.pdf'), dirs['clean'], dirs['pass2_report'], feedback_runtime=runtime)
                client.payload = dict(copy.deepcopy(PAGE), subject=subject)
                page_path = str(Path(dirs['pass1_json'])/'synthetic_page1.json')
                page = grader_pass1.grade_page(image, 'math', 1, page_path, feedback_runtime=runtime)
                self.assertEqual(page['subject'], subject)
                cross_page.resolve_cross_pages(dirs['pass1_json'], dirs['clean'], 'math', 'fixture', feedback_runtime=runtime)
                client.payload = {'items':[{'id':'1', 'ok':True}]}
                review = grader_pass1_review.review_pass1_dir(dirs['pass1_json'],
                    [{'page':1, 'clean_abs_path':image}], 'math', workers=1, feedback_runtime=runtime)
                self.assertEqual(review['feedback_execution']['config_fingerprint'], runtime.fingerprint)
                verification = verifiers.verify_pass1_dir('math', dirs['pass1_json'],
                    str(Path(dirs['pass2_report'])/f'{subject}_fixture_verification.json'), feedback_runtime=runtime)
                mem = memory.build_memory(dirs['pass1_json'], 'math', 'fixture', feedback_runtime=runtime)
                memory.save_memory(mem, dirs['pass2_report'], 'math', 'fixture', feedback_runtime=runtime)
                session_memories = sessions.build_all_session_memories(dirs['pass1_json'], dirs['pass2_report'],
                    'math', 'fixture', sessions_json_path=session_path, feedback_runtime=runtime)
                prof = profile.build_student_profile(dirs['pass2_report'], 'math', 'fixture', feedback_runtime=runtime)
                client.payload = {'mastery_trajectory':[], 'evolution_narrative':'合成协议证据',
                    'zones':{'blind_spot':[{'knowledge_point':'synthetic_concept','evidence':['p1:1'],
                        'curriculum_id':'','explanation':'合成证据描述'}], 'friction_zone':[], 'zpd':[]}}
                ontology = ontology_builder.build_ontology('math', 'fixture', tmp, dirs['pass2_report'],
                    {}, session_memories, prof, feedback_runtime=runtime)
                self.assertNotEqual(ontology.get('status'), 'failed')
                self.assertEqual(ontology['zones']['blind_spot'][0]['evidence'], ['p1:1'])
                client.payload = {'per_question_feedback':[{'qid_global':'p1:1', 'page':1, 'id':'1',
                    'comment':'请对照题目检查合成响应中的差异。', 'zone':'blind_spot'}]}
                report_path = str(Path(dirs['pass2_report'])/f'{subject}_fixture_report.json')
                report = grader_pass2.analyze_pass2(mem, 'math', 'fixture', report_path,
                    str(Path(tmp)/'thinking.txt'), ontology=ontology, feedback_runtime=runtime)
                filtered = hallucination_filter.run_hallucination_filter('math', dirs['pass1_json'], report_path,
                    str(Path(dirs['pass2_report'])/f'{subject}_fixture_hallucination.json'),
                    str(Path(tmp)/'student_ontology.json'), feedback_runtime=runtime)
                client.payload = _raw_review()
                quality = red_blue_review.evaluate_homework_red_blue(dirs,
                    {'subject':'math', 'group_id':'homework_fixture'}, feedback_runtime=runtime)
                self.assertNotEqual(quality.get('status'), 'failed', quality.get('error'))
                self.assertEqual(quality['feedback_execution']['config_fingerprint'], runtime.fingerprint)
                for result in (page, verification, mem, prof, ontology, report, filtered):
                    self.assertEqual(result['feedback_execution']['config_fingerprint'], runtime.fingerprint)
                final_page = safe_json_load(page_path)
                self.assertEqual(final_page['questions'][0]['position'], PAGE['questions'][0]['position'])
                self.assertEqual(mem['error_questions'][0]['qid_global'], 'p1:1')
                self.assertEqual(safe_json_load(report_path)['per_question_feedback'][0]['qid_global'], 'p1:1')
                render.render_page(page_path, image, str(Path(tmp)/'rendered.png'))
                self.assertTrue((Path(tmp)/'rendered.png').is_file())
                self.assertGreaterEqual(len(client.calls), 4)
                for call in client.calls:
                    self.assertIn(call['model'], {'synthetic-qwen','synthetic-review','synthetic-deepseek','kimi-k3'})
                    self.assertTrue(any(context_block(runtime) in str(m['content']) for m in call['messages']))
