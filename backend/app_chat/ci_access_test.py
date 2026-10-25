import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app_chat import ci_test_support  # noqa: F401
from django.http import JsonResponse
from django.test import RequestFactory, override_settings

from app_chat import ci_access as access


class CIAccessTests(unittest.TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch.object(access, '_tasks')
    def test_created_task_gets_client_workspace_compatibility_fields(self, tasks):
        task_store = {}
        tasks.return_value = task_store

        @access.ci_access
        def start(request):
            task_store['task1'] = {}
            return JsonResponse({'error_num': 0, 'task_id': 'task1'})

        response = start(self.factory.post(
            '/api/ci/start', {'username': 'alice_book'}, content_type='application/json'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(task_store['task1']['_ci_workspace'], 'alice_book')
        self.assertEqual(task_store['task1']['_ci_principal'], 'alice_book')

    @patch.object(access, '_tasks', return_value={'t': {'_ci_workspace': 'alice_book'}})
    def test_progress_uses_stored_workspace_without_owner_check(self, tasks):
        seen = {}

        @access.ci_access
        def progress(request, **kwargs):
            seen['workspace'] = request.ci_workspace
            seen['task'] = request.ci_task
            return JsonResponse({'error_num': 0})

        response = progress(self.factory.get(
            '/api/ci/progress/t/', {'username': 'other'}), task_id='t')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen['workspace'], 'alice_book')
        self.assertEqual(seen['task']['_ci_workspace'], 'alice_book')

    @patch.object(access, '_tasks', return_value={})
    def test_request_without_cookie_reaches_view(self, tasks):
        view = Mock(return_value=JsonResponse({'error_num': 0}))
        response = access.ci_access(view)(self.factory.post(
            '/', {'username': 'alice_book'}, content_type='application/json'))
        self.assertEqual(response.status_code, 200)
        view.assert_called_once()
        self.assertEqual(view.call_args.args[0].ci_principal, 'alice_book')

    def test_invalid_ids_and_json_do_not_reach_view(self):
        view = Mock()
        for body in ('[]', '{', '{"username":"alice","analysis_id":"../bob"}'):
            with self.subTest(body=body):
                response = access.ci_access(view)(self.factory.post(
                    '/', body, content_type='application/json'))
                self.assertEqual(response.status_code, 200)
                self.assertEqual(json.loads(response.content)['error_num'], 1)
        view.assert_not_called()

    def test_assets_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as root, override_settings(BASE_DIR=root):
            path = Path(root) / 'received_dir/user_raw_file/alice_book/page.png'
            self.assertEqual(access.assert_workspace_path('alice_book', path), str(path.resolve()))
            for candidate in (path.parent.parent / 'bob_book/page.png', path.parent / '../outside.png'):
                with self.subTest(candidate=candidate), self.assertRaises(access.CIRequestError):
                    access.assert_workspace_path('alice_book', candidate)


if __name__ == '__main__':
    unittest.main()
