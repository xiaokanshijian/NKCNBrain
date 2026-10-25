"""Offline regressions for page-local question identity; fixtures are synthetic."""

import json
import tempfile
import unittest
from pathlib import Path

from app_chat.homework_grading.memory import aggregate_pages
from app_chat.homework_grading.utils import make_qid_global


class QuestionIdentityTest(unittest.TestCase):
    def test_preserves_complete_local_id(self):
        for page, local_id, expected in (
            (10, '10-1', 'p10:10-1'),
            (10, '1', 'p10:1'),
            (3, '3-1', 'p3:3-1'),
            (3, '3-3-1', 'p3:3-3-1'),
            (35, '六-2', 'p35:六-2'),
            (' p12 ', ' auto-2 ', 'p12:auto-2'),
            (None, '1', ''),
            (1, None, ''),
        ):
            with self.subTest(page=page, local_id=local_id):
                self.assertEqual(make_qid_global(page, local_id), expected)

    def test_memory_keeps_same_page_and_cross_page_questions_distinct(self):
        with tempfile.TemporaryDirectory() as folder:
            files = []
            for page, ids in ((10, ['10-1', '1']), (11, ['10-1', '1'])):
                path = Path(folder) / f'sample_page{page}.json'
                path.write_text(json.dumps({
                    'page': page,
                    'questions': [{'id': qid, 'verdict': 'wrong'} for qid in ids],
                }), encoding='utf-8')
                files.append(str(path))
            questions = aggregate_pages(files)['error_questions']
        self.assertEqual([q['qid_global'] for q in questions],
                         ['p10:10-1', 'p10:1', 'p11:10-1', 'p11:1'])
        self.assertEqual([q['id'] for q in questions], ['10-1', '1', '10-1', '1'])


if __name__ == '__main__':
    unittest.main()
