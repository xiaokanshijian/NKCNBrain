import copy
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from app_chat import ci_test_support  # noqa: F401
from django.test import RequestFactory

from .feedback_metadata import resolve_feedback_metadata
from .feedback_runtime import prepare_feedback_runtime
from .feedback_skills import load_registry
from .feedback_prompts import stage_instructions
from .managed_feedback_rules import (
    bind_managed_rules, delete_rule, list_rules, load_document, save_rule,
)


def _copy_document(target):
    source = Path(__file__).parent / 'data' / 'managed_feedback_rules.json'
    target.write_bytes(source.read_bytes())


def _runtime(filename):
    return prepare_feedback_runtime(resolve_feedback_metadata(filename),
        model_config={'roles': {'qwen': {'model': 'synthetic'}}},
        preprocessing={'mode': 'off'}, retrieval={'version': 'test-v1'},
        references={'status': 'not_provided', 'reference_text': '', 'documents': []},
        curriculum_selection=None)


class ManagedFeedbackRulesTest(unittest.TestCase):
    def test_initial_rules_match_all_builtin_sources(self):
        document = load_document()
        self.assertEqual(len(document['rules']), 28)
        source = {}
        for skill in load_registry()[0]:
            manifest = skill['content']['manifest']
            for rule in manifest['rules']:
                source[rule['id']] = (rule, skill['content']['resources']['texts'][rule['text_key']])
        builtins = {rule['id']: rule for rule in document['rules'] if rule['built_in']}
        self.assertEqual(set(builtins), set(source))
        for rule_id, item in builtins.items():
            original, body = source[rule_id]
            self.assertEqual(item['body'], body)
            for key in ('stages', 'condition', 'evaluation_item', 'refines', 'conflicts'):
                self.assertEqual(item.get(key, []), original.get(key, []))

    def test_open_material_rules_match_only_their_material_and_stage(self):
        notes = _runtime('初中·初一·数学·笔记.pdf')
        composition = _runtime('初中·初一·语文·作文.pdf')
        homework = _runtime('初中·初一·数学·作业.pdf')

        self.assertIn('区分印刷正文', stage_instructions(notes, 'grade'))
        self.assertNotIn('页边界不是天然段落边界', stage_instructions(notes, 'grade'))
        self.assertIn('页边界不是天然段落边界', stage_instructions(composition, 'detect'))
        self.assertIn('一至两条必要', stage_instructions(notes, 'pass2'))
        self.assertIn('一至两条必要', stage_instructions(composition, 'pass2'))
        self.assertNotIn('一至两条必要', stage_instructions(homework, 'pass2'))

    def test_matching_edit_delete_and_old_runtime_are_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rules.json'
            _copy_document(path)
            payload = {'name': '合成物理理解规则', 'education_levels': ['junior'], 'grades': [2],
                       'subjects': ['physics'], 'material_types': ['exam'],
                       'usages': ['understanding'], 'body': 'synthetic-managed-rule'}
            created = save_rule(payload, path)
            skills = load_registry()[0]
            physics = resolve_feedback_metadata('初中·初二·物理·试卷.pdf')
            selected = [skill for skill in skills if skill['content']['manifest']['kind'] == 'general']
            bound, ids = bind_managed_rules(physics, selected, path)
            self.assertIn(created['id'], ids)
            self.assertIn('synthetic-managed-rule', bound[0]['content']['resources']['texts'].values())
            math = resolve_feedback_metadata('小学·四年级·数学·试卷.pdf')
            _, math_ids = bind_managed_rules(math, selected, path)
            self.assertNotIn(created['id'], math_ids)
            old = copy.deepcopy(bound)
            updated = save_rule({'id': created['id'], 'body': 'synthetic-managed-rule-updated'}, path)
            rebound, _ = bind_managed_rules(physics, selected, path)
            self.assertNotEqual(old[0]['content_hash'], rebound[0]['content_hash'])
            self.assertEqual(updated['body'], 'synthetic-managed-rule-updated')
            self.assertIn('synthetic-managed-rule', old[0]['content']['resources']['texts'].values())
            delete_rule(created['id'], path)
            rebound, ids = bind_managed_rules(physics, selected, path)
            self.assertNotIn(created['id'], ids)
            self.assertNotIn('synthetic-managed-rule-updated', rebound[0]['content']['resources']['texts'].values())

    def test_validation_corruption_and_concurrent_updates(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rules.json'
            _copy_document(path)
            with self.assertRaises(ValueError):
                save_rule({'name': '', 'education_levels': [], 'grades': [], 'subjects': [],
                           'material_types': [], 'usages': ['bad'], 'body': ''}, path)
            common = {'name': '范围错误', 'subjects': ['math'], 'material_types': ['homework'],
                      'usages': ['understanding'], 'body': 'synthetic'}
            with self.assertRaisesRegex(ValueError, '学段内'):
                save_rule(dict(common, education_levels=['junior'], grades=[9]), path)
            with self.assertRaisesRegex(ValueError, '只能选择一个学段'):
                save_rule(dict(common, education_levels=['primary', 'junior'], grades=[]), path)
            with self.assertRaisesRegex(ValueError, '先选择一个学段'):
                save_rule(dict(common, education_levels=[], grades=[3]), path)
            document = json.loads(path.read_text(encoding='utf-8'))
            document['rules'].append(copy.deepcopy(document['rules'][0]))
            path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '重复'):
                load_document(path)
            path.write_text('{broken', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '无法读取'):
                load_document(path)
            _copy_document(path)
            initial_count = len(list_rules(path))
            payload = {'education_levels': [], 'grades': [], 'subjects': [],
                       'material_types': [], 'usages': ['grading'], 'body': 'concurrent'}
            with ThreadPoolExecutor(max_workers=3) as executor:
                list(executor.map(lambda number: save_rule(dict(payload, name='并发规则' + str(number)), path), range(6)))
            self.assertEqual(len(list_rules(path)), initial_count + 6)

    def test_failed_atomic_publish_preserves_rule_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rules.json'
            _copy_document(path)
            original = path.read_bytes()
            payload = {'name': '发布失败规则', 'education_levels': [], 'grades': [], 'subjects': [],
                       'material_types': [], 'usages': ['grading'], 'body': 'never-published'}
            with patch('app_chat.homework_grading.managed_feedback_rules.atomic_json',
                       side_effect=OSError('synthetic publish failure')):
                with self.assertRaises(OSError):
                    save_rule(payload, path)
            self.assertEqual(path.read_bytes(), original)

    def test_runtime_uses_managed_body_and_api_crud(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rules.json'
            _copy_document(path)
            document = json.loads(path.read_text(encoding='utf-8'))
            target = next(rule for rule in document['rules'] if rule['id'] == 'math-detect-rules')
            target['body'] = 'managed-math-detect-body'
            path.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')
            with patch('app_chat.homework_grading.managed_feedback_rules.RULES_PATH', path):
                runtime = _runtime('小学·四年级·数学·试卷.pdf')
                bodies = runtime.dependencies['skills'][0]['content']['resources']['texts'].values()
                self.assertIn('managed-math-detect-body', bodies)
                from app_chat.views_feedback_rules import feedback_rules
                factory = RequestFactory()
                response = feedback_rules(factory.get('/api/ci/feedback-rules'))
                self.assertEqual(json.loads(response.content)['error_num'], 0)
                payload = {'name': '接口规则', 'education_levels': [], 'grades': [], 'subjects': [],
                           'material_types': [], 'usages': ['grading'], 'body': 'api-rule'}
                response = feedback_rules(factory.post('/api/ci/feedback-rules', payload,
                    content_type='application/json'))
                created = json.loads(response.content)['rule']
                response = feedback_rules(factory.delete('/api/ci/feedback-rules',
                    json.dumps({'id': created['id']}), content_type='application/json'))
                self.assertEqual(json.loads(response.content)['error_num'], 0)


if __name__ == '__main__':
    unittest.main()
