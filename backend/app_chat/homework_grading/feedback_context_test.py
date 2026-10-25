"""设计书第5节的合成上下文测试；不代表实际绑定或批改。"""
import json
import unittest
from dataclasses import FrozenInstanceError

from app_chat.homework_grading.feedback_context import FrozenFeedbackContext, freeze_feedback_context, legacy_homework_attributes
from app_chat.homework_grading.feedback_metadata import resolve_feedback_metadata


def context_fixture(name='初中·初二·物理·作业.pdf'):
    return freeze_feedback_context(resolve_feedback_metadata(name))


class ContextTest(unittest.TestCase):
    def test_deep_freeze_and_roundtrip(self):
        data = resolve_feedback_metadata('初中·初二·物理·作业.pdf')
        skills = [{'id': 'synthetic-general', 'version': 'test-1'}]
        frozen = freeze_feedback_context(data, skill_bindings=skills)
        original = frozen.to_json()
        skills[0]['version'] = 'changed'
        data['metadata_source']['subject'] = 'changed'
        output = frozen.to_dict()
        output['skill_bindings'].clear()
        self.assertEqual(frozen.to_json(), original)
        self.assertEqual(FrozenFeedbackContext.from_json(original).to_json(), original)
        with self.assertRaises(FrozenInstanceError):
            frozen._json = '{}'

    def test_unknown_and_sources_preserved(self):
        data = resolve_feedback_metadata('初中·初二·物理·作业.pdf', {'grade': None})
        output = freeze_feedback_context(data).to_dict()
        self.assertIsNone(output['grade_global'])
        self.assertEqual(output['locked_unknown_fields'], ['grade'])
        self.assertEqual(output['metadata_source'], data['metadata_source'])
        self.assertIsNone(output['curriculum_binding'])
        self.assertEqual(output['skill_bindings'], [])

    def test_custom_university_not_k12(self):
        frozen = context_fixture('大学·大一·高等数学·笔记.pdf')
        self.assertEqual(frozen.to_dict()['subject_name'], '高等数学')
        self.assertFalse(legacy_homework_attributes(frozen)['is_k12_homework'])
        self.assertIsNone(legacy_homework_attributes(frozen)['homework_grade'])
        self.assertEqual(legacy_homework_attributes(context_fixture())['homework_subject'], 'physics')

    def test_malformed_contexts_rejected(self):
        good = context_fixture().to_dict()
        for key, value in [('schema_version', 'future'), ('grade_global', True), ('skill_bindings', 'x'),
                           ('metadata_source', None), ('curriculum_binding', {'resource_id': 'missing-version'})]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                FrozenFeedbackContext.from_json(json.dumps({**good, key: value}))
        with self.assertRaises(ValueError):
            FrozenFeedbackContext.from_json('broken')


if __name__ == '__main__':
    unittest.main()
