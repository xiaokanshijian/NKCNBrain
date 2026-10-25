"""隔离服务初始化，运行实际线程调度函数及页面重试函数。"""
import ast
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
import unittest
from unittest.mock import Mock, patch

from .feedback_preprocess_test import runtime


def workers():
    source = Path(__file__).with_name('staged_pipeline.py').read_text(encoding='utf-8')
    names = {'_pass1_parallelism', '_pass1_page_max_attempts',
             '_run_pass1_page_with_retry', '_detect_page_job', '_run_detect_all_pages'}
    tree = ast.parse(source)
    tree.body = [item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name in names]
    scope = dict(__package__=__package__, Any=Any, Dict=Dict, List=List, Optional=Optional,
                 ThreadPoolExecutor=ThreadPoolExecutor, as_completed=as_completed,
                 DEFAULT_PASS1_PARALLELISM=3, traceback=SimpleNamespace(print_exc=lambda: None),
                 _question_json_path=lambda directory, image: directory + '/' + image,
                 detect_page_only=Mock(), _update_task=Mock(),
                 backfill_cross_page_detect_dir=Mock(), backfill_parent_stems_in_detect_dir=Mock(),
                 backfill_same_page_detect_dir=Mock())
    exec(compile(tree, str(Path(__file__)), 'exec'), scope)
    return scope


class StagedWorkerTest(unittest.TestCase):
    def test_threads_and_retry_receive_identical_runtime(self):
        scope = workers()
        frozen = runtime()
        calls = []

        def detect(image, *args, **kwargs):
            calls.append((image, kwargs['feedback_runtime']))
            if image == 'page1' and sum(item[0] == image for item in calls) == 1:
                raise TimeoutError('synthetic transient failure')

        scope['detect_page_only'] = detect
        pages = [{'page': n, 'clean_abs_path': 'page' + str(n)} for n in (1, 2)]
        with patch('time.sleep'), patch.dict('os.environ', {'HOMEWORK_PASS1_PAGE_MAX_ATTEMPTS': '1'}):
            scope['_run_detect_all_pages']('synthetic-task', pages, {'pass1_json': 'synthetic'},
                                           'custom', None, None, 2, feedback_runtime=frozen)
        self.assertEqual(len(calls), 3)
        self.assertTrue(all(item[1] is frozen for item in calls))
        scope['backfill_cross_page_detect_dir'].assert_called_once()


if __name__ == '__main__':
    unittest.main()
