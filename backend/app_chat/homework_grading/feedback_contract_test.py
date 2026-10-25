"""P01阶段复核：合成边界输入，防止跨模块契约遗漏。"""
import json
import unittest

from app_chat.homework_grading.feedback_context import FrozenFeedbackContext
from app_chat.homework_grading.feedback_context_test import context_fixture
from app_chat.homework_grading.feedback_fingerprint import compute_config_fingerprint
from app_chat.homework_grading.feedback_fingerprint_test import dependency_fixture
from app_chat.homework_grading.feedback_metadata import resolve_feedback_metadata


class ContractBoundaryTest(unittest.TestCase):
    def test_unrecognized_override_is_unconfirmed_not_silently_unknown(self):
        result = resolve_feedback_metadata('初中·初二·物理·作业.pdf', {'grade': '尚待核实的年级'})
        self.assertEqual(result['grade_status'], 'unconfirmed')
        self.assertEqual(result['grade_label'], '尚待核实的年级')
        self.assertIsNone(result['grade_global'])

    def test_deserialized_context_rejects_contradictory_grade(self):
        data = context_fixture().to_dict()
        data['grade_global'] = 4
        with self.assertRaises(ValueError):
            FrozenFeedbackContext.from_json(json.dumps(data))

    def test_malformed_selected_raw_is_rejected_at_context_boundary(self):
        data = context_fixture().to_dict()
        data['declared_metadata']['selected_raw'] = 'not an object'
        with self.assertRaises(ValueError):
            FrozenFeedbackContext.from_json(json.dumps(data))

    def test_custom_material_name_without_optional_key_is_distinct(self):
        data = context_fixture().to_dict()
        data.pop('material_key')
        data.update(material_type='other', material_name='合成品类甲')
        first = compute_config_fingerprint(data, **dependency_fixture())
        data['material_name'] = '合成品类乙'
        self.assertNotEqual(compute_config_fingerprint(data, **dependency_fixture()), first)

    def test_execution_identifiers_do_not_accept_credentials(self):
        args = dependency_fixture()
        args['model_config']['api_key'] = 'synthetic-not-a-real-key'
        with self.assertRaises(ValueError):
            compute_config_fingerprint(context_fixture(), **args)


if __name__ == '__main__':
    unittest.main()
