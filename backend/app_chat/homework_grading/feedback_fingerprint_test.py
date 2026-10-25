"""A13/A14/A16/S04基础对照；所有资源为明确合成fixture。"""
import copy
import unittest

from app_chat.homework_grading.feedback_context import freeze_feedback_context
from app_chat.homework_grading.feedback_context_test import context_fixture
from app_chat.homework_grading.feedback_metadata import resolve_feedback_metadata
from app_chat.homework_grading.feedback_fingerprint import compute_config_fingerprint


def dependency_fixture():
    return {'skills': [], 'curriculum': None,
            'references': {'status': 'none', 'reference_text': '', 'documents': []},
            'model_config': {'model': 'synthetic-model', 'temperature': 0},
            'preprocessing': {'version': 'synthetic-pre-1'}, 'retrieval': {'version': 'synthetic-retrieval-1'}}


class FingerprintTest(unittest.TestCase):
    def test_aliases_title_whitespace_and_sources_equal(self):
        names = ['初中·初二·物理·作业·标题.pdf', '初中·八年级·物理·作业·不同标题.pdf',
                 '初中 · ８年级 ・ Physics • 作业 · 数学四年级.PDF']
        fingerprints = {compute_config_fingerprint(context_fixture(name), **dependency_fixture()) for name in names}
        override = freeze_feedback_context(resolve_feedback_metadata('普通标题.pdf',
            {'education_level': '初中', 'grade': '初二', 'subject': '物理', 'material_type': '作业'}))
        fingerprints.add(compute_config_fingerprint(override, **dependency_fixture()))
        self.assertEqual(len(fingerprints), 1)

    def test_semantic_context_changes(self):
        names = ['初中·初二·物理·作业.pdf', '初中·初三·物理·作业.pdf', '初中·初二·化学·作业.pdf',
                 '初中·初二·物理·笔记.pdf', '大学·大一·高等数学·笔记.pdf', '大学·大一·材料力学·笔记.pdf']
        self.assertEqual(len({compute_config_fingerprint(context_fixture(n), **dependency_fixture()) for n in names}), len(names))

    def test_each_config_and_reference_state_changes(self):
        context = context_fixture()
        initial = compute_config_fingerprint(context, **dependency_fixture())
        for key, inner, value in [('model_config', 'model', 'synthetic-new'), ('preprocessing', 'version', 'new'),
                                  ('retrieval', 'version', 'new'), ('references', 'status', 'failed'),
                                  ('references', 'reference_text', 'synthetic rubric')]:
            args = dependency_fixture()
            args[key][inner] = value
            self.assertNotEqual(compute_config_fingerprint(context, **args), initial)

    def test_parser_alias_version_and_textbook_change(self):
        data = context_fixture().to_dict()
        initial = compute_config_fingerprint(data, **dependency_fixture())
        for key in ['parser_version', 'alias_version', 'textbook', 'term']:
            self.assertNotEqual(compute_config_fingerprint({**data, key: 'synthetic-new'}, **dependency_fixture()), initial)

    def test_preserves_meaningful_text_and_document_order(self):
        args = dependency_fixture()
        args['references'] = {'status': 'read', 'reference_text': 'a  b\nc', 'documents': [
            {'id': 'a', 'role': 'rubric', 'status': 'read', 'content': 'one'},
            {'id': 'b', 'role': 'background', 'status': 'read', 'content': 'two'}]}
        initial = compute_config_fingerprint(context_fixture(), **args)
        changed = copy.deepcopy(args)
        changed['references']['reference_text'] = 'a b c'
        self.assertNotEqual(compute_config_fingerprint(context_fixture(), **changed), initial)
        args['references']['documents'].reverse()
        self.assertNotEqual(compute_config_fingerprint(context_fixture(), **args), initial)

    def test_skill_content_and_version(self):
        context = freeze_feedback_context(resolve_feedback_metadata('初中·初二·物理·作业.pdf'),
                                          skill_bindings=[{'id': 'synthetic', 'version': '1'}])
        args = dependency_fixture()
        args['skills'] = [{'id': 'synthetic', 'version': '1', 'content': 'synthetic rule'}]
        initial = compute_config_fingerprint(context, **args)
        args['skills'][0]['content'] = 'different rule'
        self.assertNotEqual(compute_config_fingerprint(context, **args), initial)
        args['skills'][0]['version'] = '2'
        with self.assertRaises(ValueError):
            compute_config_fingerprint(context, **args)
        revised = context.to_dict()
        revised['skill_bindings'][0]['version'] = '2'
        self.assertNotEqual(compute_config_fingerprint(revised, **args), initial)

    def test_curriculum_scope_and_binding(self):
        data = context_fixture().to_dict()
        data['curriculum_binding'] = {'resource_id': 'synthetic', 'version': '1', 'stage_key': 'fixture'}
        args = dependency_fixture()
        args['curriculum'] = {**data['curriculum_binding'], 'content': {'label': 'synthetic'}, 'scope': [1, 2]}
        initial = compute_config_fingerprint(data, **args)
        args['curriculum']['scope'] = [2, 3]
        self.assertNotEqual(compute_config_fingerprint(data, **args), initial)
        args['curriculum']['content_hash'] = 'wrong'
        with self.assertRaises(ValueError):
            compute_config_fingerprint(data, **args)

    def test_audit_fields_not_fingerprinted_and_inputs_not_mutated(self):
        args = dependency_fixture()
        initial = copy.deepcopy(args)
        expected = compute_config_fingerprint(context_fixture(), **args)
        self.assertEqual(args, initial)
        args['model_config']['timestamp'] = 'synthetic-time'
        self.assertEqual(compute_config_fingerprint(context_fixture(), **args), expected)

    def test_missing_content_or_binding_rejected(self):
        args = dependency_fixture()
        args['skills'] = [{'id': 'synthetic', 'version': '1', 'path': 'not-content'}]
        with self.assertRaises(ValueError):
            compute_config_fingerprint(context_fixture(), **args)
        with self.assertRaises(ValueError):
            compute_config_fingerprint(context_fixture(), **{**dependency_fixture(), 'model_config': {}})


if __name__ == '__main__':
    unittest.main()
