"""P02合成协议测试；不代表真实学生材料或模型质量。"""
import copy
import tempfile
import unittest
from pathlib import Path
from shutil import copytree

from .feedback_skills import SKILL_ROOT, load_registry, load_skill
from .feedback_context import freeze_feedback_context
from .feedback_metadata import resolve_feedback_metadata
from .feedback_runtime import freeze_feedback_runtime, FrozenFeedbackRuntime


def runtime_fixture(filename='高中·高二·物理·试卷.pdf', skills=None, curriculum=None):
    skills = load_registry()[0][:1] if skills is None else skills
    context = freeze_feedback_context(resolve_feedback_metadata(filename),
        skill_bindings=[{'id': s['id'], 'version': s['version'], 'content_hash': s['content_hash']} for s in skills],
        curriculum_binding=None if curriculum is None else {k: curriculum[k] for k in ('resource_id','version','stage_key')})
    return freeze_feedback_runtime(context, skills=skills, curriculum=curriculum,
        references={'status':'not_provided','reference_text':'','documents':[]},
        model_config={'roles': {'qwen': {'model':'synthetic-qwen','extra_body':{'enable_thinking':False}}, 'deepseek':{'model':'synthetic-deepseek'}, 'review':{'model':'synthetic-review'}, 'quality':{'model':'kimi-k3'}}}, preprocessing={'mode':'off'}, retrieval={'version':'test-v1'})


class SkillLoaderTest(unittest.TestCase):
    def test_general_and_frozen_runtime(self):
        runtime = runtime_fixture()
        data = runtime.to_dict()
        data['dependencies']['skills'][0]['content']['resources']['texts'].clear()
        self.assertTrue(runtime.dependencies['skills'][0]['content']['resources']['texts'])
        self.assertEqual(runtime.context['grade_global'], 11)
        self.assertEqual(FrozenFeedbackRuntime(runtime._json).fingerprint, runtime.fingerprint)

    def test_missing_general_and_corruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'skills'
            copytree(SKILL_ROOT,root)
            p=root/'general-feedback/1.0.0/instructions.md'
            p.write_text('changed',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'通用规则不可用'):
                load_registry(root)
            p.unlink()
            with self.assertRaises(ValueError):
                load_registry(root)

    def test_path_rejected(self):
        for identity in ('../escape','C:/escape','x/y'):
            with self.assertRaises(ValueError):
                load_skill({'id':identity,'version':'1.0.0'})

    def test_runtime_binding_tamper(self):
        r=runtime_fixture()
        import json
        data=r.to_dict()
        data['dependencies']['skills'][0]['version']='9.0.0'
        with self.assertRaises(ValueError):
            FrozenFeedbackRuntime(json.dumps(data))
