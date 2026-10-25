import json
import tempfile
from pathlib import Path
from unittest import TestCase
from app_chat import ci_test_support  # noqa: F401
from django.test import RequestFactory, override_settings
from .feedback_material_settings import (
    material_settings,
    merge_saved_material_settings,
    settings_path,
)


class MaterialSettingsTest(TestCase):
    def call(self, filename, workspace='alice_book', **extra):
        from django.conf import settings
        source = Path(settings.BASE_DIR) / 'received_dir/user_raw_file' / workspace / filename
        source.parent.mkdir(parents=True, exist_ok=True)
        if not source.exists():
            source.write_bytes(('synthetic-pdf:' + filename).encode('utf-8'))
        request = RequestFactory().post('/', {'files': [filename], **extra}, content_type='application/json')
        request.ci_workspace = workspace
        # 身份及路径鉴权包装已有独立回归；此处验证持久化业务，不连接真实账号。
        return json.loads(material_settings.__wrapped__.__wrapped__(request).content)

    def call_public(self, filename, workspace='alice_book', **extra):
        request = RequestFactory().post('/', {
            'username': workspace, 'files': [filename], **extra,
        }, content_type='application/json')
        return json.loads(material_settings(request).content)

    def test_save_read_isolation_and_no_task(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            first = self.call('试卷.pdf')
            self.assertFalse(first['material_saved'])
            self.assertEqual(first['parse_status'], 'unstructured')
            material = {'feedback_overrides': {'education_level': '大学', 'grade': '大二',
                        'subject': '嵌入式系统', 'material_type': '试卷'},
                        'curriculum_selection': None, 'reference_text': '合成参考'}
            saved = self.call('试卷.pdf', save=True, material=material)
            self.assertEqual(saved['error_num'], 0)
            self.assertNotIn('task_id', saved)
            again = self.call('试卷.pdf')
            self.assertEqual(again['material'], material)
            self.assertEqual(again['feedback_context']['grade_in_level'], 2)
            self.assertIsNone(again['feedback_context']['grade_global'])
            self.assertFalse(self.call('试卷.pdf', workspace='bob_book')['material_saved'])
            self.assertFalse(self.call('其他.pdf')['material_saved'])

    def test_standard_and_invalid_save(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            result = self.call('小学·四年级·数学·作业.pdf')
            self.assertEqual(result['parse_status'], 'parsed')
            self.assertTrue(result['feedback_eligible'])
            self.assertEqual(self.call('试卷.pdf', save=True, material={'curriculum_selection': 'unsupported'})['error_num'], 1)
            self.assertFalse(settings_path('alice_book', '试卷.pdf').exists())
            self.assertEqual(self.call('试卷.pdf', save=True, material={'feedback_overrides': {'material_type': '笔记'}})['error_num'], 0)
            self.assertTrue(self.call('试卷.pdf')['feedback_eligible'])

    def test_saved_values_merge_by_field_and_corruption_is_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            saved = {
                'feedback_overrides': {
                    'education_level': '初中', 'grade': '初一',
                    'subject': '数学', 'material_type': '笔记',
                },
                'curriculum_selection': None,
                'reference_text': '保存的附加信息',
            }
            self.assertEqual(self.call('笔记.pdf', save=True, material=saved)['error_num'], 0)
            merged, exists = merge_saved_material_settings('alice_book', '笔记.pdf', {
                'feedback_overrides': {'subject': '历史'},
                'reference_text': '本次显式附加信息',
            })
            self.assertTrue(exists)
            self.assertEqual(merged['feedback_overrides']['education_level'], '初中')
            self.assertEqual(merged['feedback_overrides']['subject'], '历史')
            self.assertIsNone(merged['curriculum_selection'])
            self.assertEqual(merged['reference_text'], '本次显式附加信息')

            path = settings_path('alice_book', '笔记.pdf')
            path.write_text('{bad json', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, '已保存材料设置无法读取'):
                merge_saved_material_settings('alice_book', '笔记.pdf', {})

    def test_public_endpoint_accepts_workspace_without_cookie(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(BASE_DIR=Path(tmp)):
            result = self.call_public('小学·四年级·数学·作业.pdf')
            self.assertEqual(result['error_num'], 0)
            self.assertTrue(result['feedback_eligible'])
