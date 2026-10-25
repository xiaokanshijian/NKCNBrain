"""本地合成产物与可控向量存储；不请求嵌入/批改服务。"""
import copy
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djangoProject.settings')
from django.test import override_settings
from . import grading_rag as r


class Store:
    def __init__(self):
        self.rows = {}
        self.add_calls = 0

    def get(self, ids, **kwargs):
        return {'ids': [key for key in ids if key in self.rows]}

    def add_documents(self, docs, ids):
        self.add_calls += 1
        self.rows.update(zip(ids, copy.deepcopy(docs)))

    def max_marginal_relevance_search(self, question, **kwargs):
        self.last_query = kwargs
        return list(self.rows.values())  # 故意返回越界候选，验证应用层也过滤。


class GradingRagTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.settings = override_settings(BASE_DIR=self.base)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.workspace = 'synthetic_notebook'
        self.records = []
        self.roots = {}
        self.load = patch('app_chat.ci.index_manager.CIIndexManager.load', side_effect=lambda workspace: self.records)
        self.load.start()
        self.addCleanup(self.load.stop)
        self.resolve = patch('app_chat.homework_grading.homework_versions.resolve_homework_run_root',
                             side_effect=lambda workspace, analysis_id: str(self.roots[analysis_id]))
        self.resolve.start()
        self.addCleanup(self.resolve.stop)
        self.store = Store()

    def fixture(self, name='笔记.pdf', run='p03_' + 'a' * 32):
        base = self.base / 'received_dir' / 'user_raw_file' / self.workspace
        base.mkdir(parents=True, exist_ok=True)
        source = base / name
        source.write_bytes(name.encode('utf-8'))
        sha = r._source_hash(source)
        analysis = 'homework_' + sha[:24]
        root = base / 'continuous_image_dmt' / analysis / '_runs' / run
        report_dir = root / 'homework_grading' / 'pass2_report'
        pages_dir = root / 'homework_grading' / 'pass1_json'
        report_dir.mkdir(parents=True, exist_ok=True)
        pages_dir.mkdir(parents=True, exist_ok=True)
        manifest = {'username': self.workspace, 'selected_files': [name], 'status': 'completed',
                    'stages': {'grading': 'done'}, 'run_id': run, 'group_id': analysis,
                    'subject': 'math', 'subject_label': '数学', 'source_document_sha256': sha}
        report = {'diagnosis': {'summary': '知识整理的模型观察'}, 'zone_classification': {},
                  'per_question_feedback': [{'page': 1, 'id': '1', 'qid_global': 'p1:1', 'comment': '此处待确认。'}],
                  'thinking': '绝不可引用的思考日志'}
        page = {'page': 1, 'questions': [{'id': '1', 'stem_excerpt': '有理数', 'student_answer': '0',
                'understanding': '局部笔迹不清楚', 'verdict': 'uncertain', 'assessment_status': 'unconfirmed',
                'annotation_links': [{'marked_text': '有理数', 'annotation_text': '分类', 'relation': '概括原文'}]}]}
        self.write(root / 'manifest.json', manifest)
        self.write(report_dir / f'math_{sha[:8]}_report.json', report)
        self.write(pages_dir / 'page_001.json', page)
        self.records[:] = [x for x in self.records if x['analysis_id'] != analysis]
        self.records.append({'analysis_id': analysis, 'analysis_type': 'homework_grading', 'files': [name],
                             'mode': 'single', 'status': 'completed', 'updated_at': '2026-09-18'})
        self.roots[analysis] = root
        return source, root, manifest

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def selection(self, names=None):
        return r.inspect_selection(self.workspace, names or ['笔记.pdf'])

    def test_lazy_historical_index_idempotent_and_preserves_report(self):
        _, root, _ = self.fixture()
        item = self.selection()['items'][0]
        before = list((root / 'homework_grading' / 'pass2_report').glob('*.json'))[0].read_bytes()
        chunks = r.ensure_index(item, self.store)
        r.ensure_index(item, self.store)
        self.assertEqual(self.store.add_calls, 1)
        text = '\n'.join(c.page_content for c in chunks)
        self.assertIn('待确认', text)
        self.assertIn('概括原文', text)
        self.assertNotIn('绝不可引用', text)
        self.assertEqual(before, list((root / 'homework_grading' / 'pass2_report').glob('*.json'))[0].read_bytes())
        self.assertEqual(self.selection()['items'][0]['index_status'], 'ready')

    def test_changed_source_and_deleted_source_never_use_vectors(self):
        source, _, _ = self.fixture()
        source.write_bytes(b'replaced')
        self.assertEqual(self.selection()['items'][0]['status'], 'unavailable')
        source.unlink()
        self.assertEqual(self.selection()['items'][0]['status'], 'unavailable')

    def test_running_failed_interrupted_partial_are_unavailable(self):
        _, root, manifest = self.fixture()
        for status in ('running', 'failed', 'interrupted', 'partial'):
            self.write(root / 'manifest.json', {**manifest, 'status': status})
            self.assertEqual(self.selection()['items'][0]['status'], 'unavailable')
        self.write(root / 'manifest.json', manifest)
        self.records[0]['status'] = 'failed'
        self.assertEqual(self.selection()['items'][0]['status'], 'unavailable')

    def test_completed_report_with_failed_check_is_not_used_as_qa_evidence(self):
        _, root, manifest = self.fixture()
        self.write(root / 'manifest.json', {**manifest, 'content_validation': {
            'status': 'inconclusive', 'failed_checks': ['hallucination']}})
        selection = self.selection()
        self.assertEqual(selection['items'][0]['status'], 'unavailable')
        with patch.object(r, '_vector_store', side_effect=AssertionError('不得索引未复核内容')):
            documents, statuses = r.retrieve_selection(selection, '合成问题')
        self.assertEqual(documents, [])
        self.assertIn('复核未完成', statuses[0]['message'])
        self.write(root / 'manifest.json', manifest)
        self.assertEqual(self.selection()['items'][0]['status'], 'available')

    def test_quality_only_partial_remains_usable_but_review_failure_does_not(self):
        from .completion_test import complete_manifest
        _, root, manifest = self.fixture()
        manifest.update(complete_manifest())
        manifest.update(status='partial', red_blue_review={'status': 'failed'})
        self.records[0]['status'] = 'partial'
        self.write(root / 'manifest.json', manifest)
        self.assertEqual(self.selection()['items'][0]['status'], 'available')
        manifest['pass1_review']['quota_limited'] = True
        self.write(root / 'manifest.json', manifest)
        self.assertEqual(self.selection()['items'][0]['status'], 'unavailable')

    def test_saved_completed_but_material_blocked_is_not_qa_evidence(self):
        _, root, _ = self.fixture()
        path = root / 'homework_grading/pass1_json/page_001.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['questions'][0]['material_check'] = {'status': 'unresolved', 'blocks_assessment': True}
        self.write(path, data)
        self.assertEqual(self.selection()['items'][0]['status'], 'unavailable')

    def test_current_version_switch_and_rollback_change_cache(self):
        _, old_root, manifest = self.fixture()
        first = self.selection()
        self.fixture(run='p03_' + 'b' * 32)
        second = self.selection()
        self.assertNotEqual(first['cache_key'], second['cache_key'])
        self.roots[manifest['group_id']] = old_root
        self.assertEqual(first['cache_key'], self.selection()['cache_key'])

    def test_content_or_index_status_change_invalidates_cache(self):
        _, root, _ = self.fixture()
        before = self.selection()
        r.ensure_index(before['items'][0], self.store)
        after = self.selection()
        self.assertNotEqual(before['cache_key'], after['cache_key'])
        page = root / 'homework_grading' / 'pass1_json' / 'page_001.json'
        payload = json.loads(page.read_text(encoding='utf-8'))
        payload['questions'][0]['student_answer'] = '复核后变化'
        self.write(page, payload)
        self.assertNotEqual(after['cache_key'], self.selection()['cache_key'])

    def test_other_workspace_or_unselected_document_is_not_retrieved(self):
        self.fixture()
        self.fixture('试卷.pdf')
        with patch.object(r, '_vector_store', return_value=self.store):
            r._retrieve(self.selection(['试卷.pdf'])['items'], '问题')
            docs, statuses = r._retrieve(self.selection()['items'], '问题')
        self.assertEqual(statuses[0]['status'], 'ready')
        self.assertTrue(all(d.metadata['filename'] == '笔记.pdf' for group in docs for d in group))
        other = r.inspect_selection('another_notebook', ['笔记.pdf'])
        self.assertNotEqual(other['items'][0]['status'], 'available')

    def test_multiple_materials_and_budget_keep_source_citations(self):
        self.fixture()
        self.fixture('试卷.pdf')
        with patch.object(r, '_vector_store', return_value=self.store):
            docs, statuses = r._retrieve(self.selection(['笔记.pdf', '试卷.pdf'])['items'], '共同问题', True)
        merged = r.merge_context([], docs, statuses, 1800)
        text = '\n'.join(d.page_content for group in merged for d in group)
        self.assertIn('笔记.pdf', text)
        self.assertIn('试卷.pdf', text)
        self.assertIn('PDF第1页', text)
        self.assertLessEqual(sum(len(d.page_content) for group in merged for d in group), 1800)
        self.assertEqual(self.store.last_query['k'], 5)

    def test_no_budget_keeps_original_and_reports_limitation(self):
        from langchain_core.documents import Document
        self.fixture()
        with patch.object(r, '_vector_store', return_value=self.store):
            docs, statuses = r._retrieve(self.selection()['items'], '问题')
        original = [[Document(page_content='原文' * 20)]]
        self.assertEqual(r.merge_context(original, docs, statuses, 10), original)
        self.assertEqual(statuses[0]['status'], 'limited')

    def test_embedding_failure_is_retryable_without_changing_grading(self):
        _, root, _ = self.fixture()
        item = self.selection()['items'][0]
        with patch.object(self.store, 'add_documents', side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):
                r.ensure_index(item, self.store)
        self.assertEqual(self.selection()['items'][0]['index_status'], 'failed')
        r.ensure_index(item, self.store)
        self.assertEqual(self.selection()['items'][0]['index_status'], 'ready')
        self.assertEqual(json.loads((root / 'manifest.json').read_text(encoding='utf-8'))['status'], 'completed')

    def test_corrupt_derived_index_state_can_be_rebuilt(self):
        _, root, _ = self.fixture()
        (root / 'grading_rag_state.json').write_text('broken', encoding='utf-8')
        item = self.selection()['items'][0]
        self.assertEqual(item['status'], 'available')
        r.ensure_index(item, self.store)
        self.assertEqual(self.selection()['items'][0]['index_status'], 'ready')

    def test_query_timeout_returns_pending_and_reuses_job(self):
        self.fixture()
        selection = self.selection()
        event = threading.Event()
        self.addCleanup(event.set)
        def slow(*args):
            event.wait(2)
            return [], []
        with patch.object(r, '_retrieve', side_effect=slow) as call:
            for _ in range(2):
                docs, statuses = r.retrieve_selection(selection, '慢请求', wait_seconds=0.01)
                self.assertEqual(docs, [])
                self.assertEqual(statuses[0]['status'], 'pending')
            self.assertEqual(call.call_count, 1)
            event.set()
            r.retrieve_selection(selection, '慢请求', wait_seconds=2)

    def test_rerun_during_retrieval_discards_documents(self):
        self.fixture()
        before = self.selection()
        with patch.object(r, '_vector_store', return_value=self.store):
            docs, statuses = r._retrieve(before['items'], '问题')
        self.fixture(run='p03_' + 'c' * 32)
        with patch.object(r, 'retrieve_selection', return_value=(docs, statuses)):
            result = r.append_grading_context([], self.workspace, ['笔记.pdf'], '问题', selection=before)
        self.assertEqual(result, [])
        self.assertEqual(before['result_status'][0]['status'], 'unavailable')

    def test_legacy_without_source_hash_requires_matching_identity(self):
        _, root, manifest = self.fixture()
        manifest.pop('source_document_sha256')
        self.write(root / 'manifest.json', manifest)
        self.assertEqual(self.selection()['items'][0]['status'], 'available')
        original = self.records[0]['analysis_id']
        self.records[0]['analysis_id'] = 'homework_' + 'd' * 12
        self.roots[self.records[0]['analysis_id']] = self.roots[original]
        self.assertEqual(self.selection()['items'][0]['status'], 'unavailable')

    def test_workspace_and_path_traversal_rejected(self):
        self.fixture()
        self.assertEqual(r.inspect_selection('../outside', ['笔记.pdf'])['items'][0]['status'], 'unavailable')
        self.assertEqual(self.selection(['../../outside.pdf'])['items'][0]['status'], 'unavailable')

    def test_cache_requires_matching_workspace_version_and_retryable_status(self):
        self.fixture()
        selection = self.selection()
        cached = {'grading_cache_key': selection['cache_key'], 'grading_context_status': [{'status': 'ready'}]}
        self.assertTrue(r.cache_matches(cached, selection))
        for status in ('pending', 'failed'):
            self.assertFalse(r.cache_matches({**cached, 'grading_context_status': [{'status': status}]}, selection))
        self.fixture(run='p03_' + 'd' * 32)
        self.assertFalse(r.cache_matches(cached, self.selection()))
        self.assertNotEqual(r.inspect_selection('one', [])['cache_key'], r.inspect_selection('two', [])['cache_key'])

    def test_unavailable_policy_does_not_reuse_old_diagnosis_in_history(self):
        params = {'text': '原文', 'question_with_history': {'model': '历史答案提到旧版诊断'}}
        r.apply_reference_policy(params, [{'filename': '笔记.pdf', 'status': 'unavailable'}])
        self.assertTrue(params['text'].startswith('【本轮材料范围】'))
        self.assertIn('不能声称读取了其批改：笔记.pdf', params['question_with_history']['model'])
        original = {'text': '普通文档原文', 'question_with_history': {'model': '普通问答'}}
        unchanged = copy.deepcopy(original)
        r.apply_reference_policy(unchanged, [{'filename': '普通文档.pdf', 'status': 'not_graded'}])
        self.assertEqual(unchanged, original)

    def test_real_chroma_collection_with_local_embeddings(self):
        from langchain_core.embeddings import Embeddings
        from langchain_community.vectorstores import Chroma
        from chromadb.config import Settings
        class LocalEmbeddings(Embeddings):
            def embed_documents(self, texts):
                return [[float(len(text)), float(text.count('有理数') + 1), 1.0] for text in texts]
            def embed_query(self, text):
                return self.embed_documents([text])[0]
        self.fixture()
        # Chroma在Windows会保留SQLite句柄，使用独立临时路径并允许系统稍后清理。
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as path:
            store = Chroma(collection_name='grading-offline-test', embedding_function=LocalEmbeddings(),
                           persist_directory=path, client_settings=Settings(anonymized_telemetry=False))
            with patch.object(r, '_vector_store', return_value=store):
                docs, statuses = r._retrieve(self.selection()['items'], '有理数')
                self.assertEqual(statuses[0]['status'], 'ready')
                self.assertTrue(docs[0])
                first_count = len(store.get()['ids'])
                r._retrieve(self.selection()['items'], '有理数')
                self.assertEqual(len(store.get()['ids']), first_count)
            store.delete_collection()

    def test_existing_four_retrieval_modes_and_image_parsing_still_work(self):
        from langchain_core.documents import Document
        from llm_langchain import util, parse_input
        self.fixture()
        original = Document(page_content='原文段落', metadata={'source': '笔记.pdf', 'page': 0})
        with patch.object(r, '_vector_store', return_value=self.store), \
             patch.object(parse_input, 'get_vector_by_user', return_value=self.store), \
             patch.object(parse_input, 'get_split_by_user_docs', return_value=[original]), \
             patch.object(util, 'get_docs_by_seq_limit', return_value=[original]), \
             patch.object(util, 'get_docs_by_more', return_value=[original]), \
             patch.object(util, 'get_relevant_docs', return_value=[original]):
            for mode in range(4):
                selection = self.selection()
                groups = util.get_docs_all_split(self.workspace, ['笔记.pdf'], [mode], '问题', grading_selection=selection)
                self.assertIn(original, groups[0])
                self.assertTrue(any(d.metadata.get('type') == 'grading' for group in groups for d in group))
                images, *_ = util.parse_image_in_segment_split(self.workspace, groups)
                self.assertEqual(images, [[] for _ in groups])
                self.assertEqual(selection['result_status'][0]['status'], 'ready')


if __name__ == '__main__':
    unittest.main()
