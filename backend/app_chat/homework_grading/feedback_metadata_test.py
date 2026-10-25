"""设计书F01–F11的合成协议用例，不是学生材料或真实运行。"""
import unittest

from app_chat.homework_grading.feedback_metadata import parse_feedback_filename
from app_chat.homework_grading.feedback_metadata import resolve_feedback_metadata, resolve_resource_stage


class FilenameTest(unittest.TestCase):
    def test_f01_standard(self):
        result = parse_feedback_filename('初中·八年级·物理·作业·力与运动.pdf')
        self.assertEqual(result['parse_status'], 'parsed')
        self.assertEqual([v['value'] for v in result['fields'].values()],
                         ['junior', '八年级', 'physics', 'homework'])

    def test_f02_title(self):
        self.assertEqual(parse_feedback_filename('大学·大一·高等数学·笔记·极限·连续性.pdf')['title'], '极限·连续性')

    def test_f03_unicode_original(self):
        name = '初中 · ８年级 ・ Physics • 作业 · 力与运动.PDF'
        result = parse_feedback_filename(name)
        self.assertEqual(result['original_filename'], name)
        self.assertEqual(result['fields']['grade']['value'], '8年级')
        self.assertEqual(result['fields']['subject']['value'], 'physics')

    def test_f04_empty_slot(self):
        result = parse_feedback_filename('初中··物理·作业·力与运动.pdf')
        self.assertIsNone(result['fields']['grade']['value'])
        self.assertEqual(result['fields']['subject']['value'], 'physics')

    def test_f05_no_shifting(self):
        result = parse_feedback_filename('初中·物理·作业·力与运动.pdf')
        self.assertEqual(result['parse_status'], 'ambiguous')
        self.assertIsNone(result['fields']['material_type']['value'])

    def test_f06_conflict(self):
        self.assertEqual(parse_feedback_filename('初中·高二·物理·作业.pdf')['parse_status'], 'conflict')

    def test_f07_grade_spellings(self):
        for value in ['七年级', '初一', '7年级', '二年级']:
            self.assertEqual(parse_feedback_filename(f'初中·{value}·物理·作业.pdf')['fields']['grade']['status'], 'declared')

    def test_f08_custom_and_no_title(self):
        result = parse_feedback_filename('大学·大一·材料力学·自定义品类.pdf')
        self.assertEqual(result['fields']['subject']['value'], '材料力学')
        self.assertEqual(result['fields']['material_type']['value'], '自定义品类')
        self.assertEqual(result['title'], '')

    def test_f09_title_does_not_infer(self):
        result = parse_feedback_filename('初中·未知·物理·作业·数学_四年级-1.5.pdf')
        self.assertIsNone(result['fields']['grade']['value'])
        self.assertEqual(result['title'], '数学_四年级-1.5')

    def test_f10_unstructured_and_reordered(self):
        for name in ['数学一年级.pdf', '初中·八年级.pdf', '初中-八年级-物理-作业.pdf']:
            self.assertEqual(parse_feedback_filename(name)['parse_status'], 'unstructured')
        result = parse_feedback_filename('物理·初中·八年级·作业.pdf')
        self.assertEqual(result['parse_status'], 'ambiguous')
        self.assertIsNone(result['fields']['subject']['value'])


class MetadataTest(unittest.TestCase):
    def test_alias_grades(self):
        for text in ['初二', '八年级', '8年级', '二年级']:
            result = resolve_feedback_metadata(f'初中·{text}·物理·作业.pdf')
            self.assertEqual((result['grade_in_level'], result['grade_global']), (2, 8))
        self.assertEqual(resolve_feedback_metadata('高中·二年级·化学·试卷.pdf')['grade_global'], 11)

    def test_priority_and_unknown_lock(self):
        name = '初中·八年级·物理·作业.pdf'
        result = resolve_feedback_metadata(name, {'grade': None}, {'grade': '初三', 'subject': '数学'})
        self.assertIsNone(result['grade_global'])
        self.assertEqual(result['subject_code'], 'physics')
        self.assertEqual(result['locked_unknown_fields'], ['grade'])
        self.assertEqual(resolve_feedback_metadata(name, {'grade': '初三'})['grade_global'], 9)

    def test_inferred_and_locked_level(self):
        name = '·一年级·数学·作业.pdf'
        self.assertEqual(resolve_feedback_metadata(name)['metadata_source']['education_level'], 'inferred')
        result = resolve_feedback_metadata(name, {'education_level': '未知'})
        self.assertEqual(result['education_level'], 'unknown')
        self.assertIsNone(result['grade_global'])

    def test_conflict_not_filled_by_observation(self):
        result = resolve_feedback_metadata('初中·高二·物理·作业.pdf', reliable_observations={'grade': '初二'})
        self.assertEqual(result['grade_status'], 'conflict')
        self.assertIsNone(result['grade_global'])
        fixed = resolve_feedback_metadata('初中·高二·物理·作业.pdf', {'education_level': '高中'})
        self.assertEqual(fixed['grade_global'], 11)

    def test_observation_fills_missing_only(self):
        result = resolve_feedback_metadata('初中··物理·作业.pdf', reliable_observations={'grade': '初二'})
        self.assertEqual(result['metadata_source']['grade'], 'observation')
        self.assertEqual(result['grade_global'], 8)

    def test_custom_university_and_school_system(self):
        result = resolve_feedback_metadata('大学·大一·高等数学·笔记.pdf')
        self.assertEqual(result['grade_in_level'], 1)
        self.assertIsNone(result['grade_global'])
        other = resolve_feedback_metadata('大学·大一·材料力学·笔记.pdf')
        self.assertNotEqual(result['subject_key'], other['subject_key'])
        result = resolve_feedback_metadata('初中·初二·物理·作业.pdf', {'school_system': '非六三三'})
        self.assertIsNone(result['grade_global'])

    def test_resource_stage_is_explicit_and_unique(self):
        resource = [{'stage_key': 'S4', 'education_level': 'junior', 'grade_min': 1, 'grade_max': 3}]
        result = resolve_feedback_metadata('初中·初二·物理·作业.pdf')
        self.assertEqual(resolve_resource_stage(result, resource), 'S4')
        self.assertIsNone(resolve_resource_stage(result, resource * 2))
        for name in ['高中·高二·物理·作业.pdf', '大学·大一·物理·笔记.pdf', '初中·未知·物理·作业.pdf', '初中·高二·物理·作业.pdf']:
            self.assertIsNone(resolve_resource_stage(resolve_feedback_metadata(name), resource))


if __name__ == '__main__':
    unittest.main()
