import json
import os
import shutil
import tempfile
import unittest

from app_chat.homework_grading.cross_page_detect_backfill import backfill_cross_page_detect_dir
from app_chat.homework_grading.parent_stem_backfill import backfill_parent_stems_in_detect_dir
from app_chat.homework_grading.same_page_detect_backfill import backfill_same_page_detect_dir


SAMPLE_ROOT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    'homework_a96de3a8ba9d',
    'homework_grading',
    'pass1_json',
)


class CrossPageDetectBackfillTest(unittest.TestCase):
    def test_page4_backfill_from_sample_detect(self):
        if not os.path.isdir(SAMPLE_ROOT):
            self.skipTest('sample detect dir missing')

        with tempfile.TemporaryDirectory() as tmp:
            for name in ('math_a96de3a8_page3.detect.json', 'math_a96de3a8_page4.detect.json'):
                shutil.copy2(os.path.join(SAMPLE_ROOT, name), os.path.join(tmp, name))

            stats = backfill_cross_page_detect_dir(tmp)
            backfill_parent_stems_in_detect_dir(tmp)

            self.assertGreater(stats['id_patched'], 0)
            with open(os.path.join(tmp, 'math_a96de3a8_page3.detect.json'), encoding='utf-8') as file:
                page3 = json.load(file)
            with open(os.path.join(tmp, 'math_a96de3a8_page4.detect.json'), encoding='utf-8') as file:
                page4 = json.load(file)

            self.assertTrue(page3['boundary']['continues_to_next'])
            first = page4['questions'][0]
            self.assertEqual(first['id'], '4-2')
            self.assertEqual(first['parent_group_id'], '4')
            self.assertIn('4.', first['parent_stem_excerpt'])
            self.assertTrue(first.get('cross_page_context_ready'))

    def test_same_page_double_column_auto_subquestion_backfill(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'math_sample_page11.detect.json')
            data = {
                'page': 11,
                'subject': 'math',
                'questions': [
                    {
                        'id': 'auto-4',
                        'parent_group_id': '',
                        'parent_stem_excerpt': '',
                        'stem_excerpt': '(2)当a=10时，剩下图形的面积是多少平方厘米？',
                        'position': [615, 100, 700, 245],
                    },
                    {
                        'id': '11-1',
                        'parent_group_id': '11',
                        'parent_stem_excerpt': '11.把如图所示的长方形剪去一个最大的正方形。（图中长方形宽a厘米，高9厘米）',
                        'stem_excerpt': '(1)用含有字母的式子表示剩下图形的面积。',
                        'position': [225, 805, 480, 935],
                    },
                    {
                        'id': '12-1',
                        'parent_group_id': '12',
                        'parent_stem_excerpt': '12.如图所示，一个边长为x米的正方形草坪中间有一个边长为y米的正方形小水池。',
                        'stem_excerpt': '(1)用含有字母的式子表示草坪的面积。',
                        'position': [615, 495, 810, 590],
                    },
                ],
            }
            with open(path, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False)

            stats = backfill_same_page_detect_dir(tmp)
            with open(path, encoding='utf-8') as file:
                patched = json.load(file)
            first = patched['questions'][0]

            self.assertEqual(stats['id_patched'], 1)
            self.assertEqual(first['id'], '11-2')
            self.assertEqual(first['parent_group_id'], '11')
            self.assertIn('长方形宽a厘米，高9厘米', first['parent_stem_excerpt'])


if __name__ == '__main__':
    unittest.main()
