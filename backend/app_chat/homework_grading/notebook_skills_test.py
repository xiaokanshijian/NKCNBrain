"""临时本子与模型替身；不写真实本子、不请求外部模型。"""
import copy
import json
import shutil
import tempfile
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from app_chat import ci_test_support  # noqa: F401
from django.test import override_settings
from . import notebook_skills as skills
from .feedback_preprocess_test import runtime
from .feedback_runtime import freeze_feedback_runtime
from .feedback_snapshot import prepare_feedback_snapshot
from .feedback_snapshot_test import snapshot_arguments
from .feedback_runtime_service import restore_feedback_runtime
from .feedback_rerun_plan import choose_rerun_runtime
from .feedback_prompts import system_prompt, diagnostic_system
from .model_output import request_json_object
from .completion import material_evidence_summary, summarize_completion, available_actions
from .completion_test import complete_manifest
from .semantic_checks import phrase_findings
from .utils import safe_json_dump, windows_io_path

BODY = ('# 测试方法\n## 核心主张\n以原稿证据为准。\n## I — 方法论重述\n'
        '先说明知识关系，再提出待验证问题。\n## E — 执行步骤\n先列条件，再检查反例。\n'
        '## A2 — 何时使用\n用于学习反馈。\n## B — 边界与盲点\n不从一次表现推定人格。')


def fixture(root):
    book = Path(root) / 'received_dir/user_raw_file/synthetic_book'
    directory = book / 'skills/method'
    directory.mkdir(parents=True)
    (book / 'methods.zip').write_bytes(b'fixture source identity')
    path = directory / 'SKILL.md'
    path.write_text('---\nname: method\ndescription: 示例\n---\n' + BODY, encoding='utf-8')
    index = {'skills': {'method': {'pack_zip': 'methods.zip', 'enabled': True}},
             'packs': {'methods.zip': {'members': ['method'], 'enabled': {'method': True}}}}
    (book / 'skills/_index.json').write_text(json.dumps(index), encoding='utf-8')
    return book, path, index


def frozen(bundle):
    old = runtime()
    deps = old.dependencies
    deps['references']['notebook_skills'] = bundle
    return freeze_feedback_runtime(old.context, **deps)


class NotebookSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = override_settings(BASE_DIR=self.temp.name)
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        self.book, self.path, self.index = fixture(self.temp.name)
        self.selected = {'enabled': True, 'names': ['method']}

    def bundle(self):
        return skills.freeze_selection('synthetic_book', self.selected)

    def test_realistic_sections_preserve_steps_boundary_and_length(self):
        content = BODY + '\n## 普通附录\n' + '额外内容' * 5000
        result, headings, truncated = skills.excerpt(content)
        self.assertLessEqual(len(result), 4000)
        self.assertIn('先列条件，再检查反例', result)
        self.assertIn('不从一次表现推定人格', result)
        self.assertTrue(truncated)
        self.assertTrue(any('边界' in h for h in headings))
        self.assertEqual(skills.excerpt('普通无标题方法正文')[0], '普通无标题方法正文')

    def test_disabled_does_not_read_store(self):
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('关闭不读包')):
            bundle = skills.freeze_selection(None, {'enabled': False, 'names': []})
        self.assertFalse(bundle['enabled'])

    def test_invalid_selection_and_unselected_members_rejected(self):
        for value in [None, {}, {'enabled': 1, 'names': ['method']}, {'enabled': True, 'names': []},
                      {'enabled': False, 'names': ['method']}, {'enabled': True, 'names': ['method'] * 2},
                      {'enabled': True, 'names': ['../method']}, {'enabled': True, 'names': ['notebook-hub']},
                      {'enabled': True, 'names': ['method'], 'raw': '客户端替换正文'},
                      {'enabled': True, 'names': ['a', 'b', 'c']}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                skills.freeze_selection('synthetic_book', value)
        with self.assertRaises(ValueError):
            skills.freeze_selection('other_book', self.selected)

    def test_disabled_or_orphaned_or_missing_sources_rejected(self):
        for key in ('orphaned', 'missing', 'enabled'):
            index = copy.deepcopy(self.index)
            index['skills']['method'][key] = key != 'enabled'
            (self.book / 'skills/_index.json').write_text(json.dumps(index))
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.bundle()
        (self.book / 'skills/_index.json').write_text(json.dumps(self.index))
        self.path.unlink()
        with self.assertRaises(ValueError): self.bundle()

    def test_freeze_roundtrip_and_rerun_inherit_after_edit(self):
        value = frozen(self.bundle())
        args = snapshot_arguments(self.temp.name)
        args.update(context=value.context, **value.dependencies)
        root = Path(self.temp.name) / 'run'
        prepare_feedback_snapshot(root, **args)
        self.path.write_text('---\nname: method\n---\n另一个方法', encoding='utf-8')
        restored = restore_feedback_runtime(root)
        self.assertEqual(restored.fingerprint, value.fingerprint)
        inherited, plan = choose_rerun_runtime(root, '试卷.pdf', {'rerun_stage': 'grading'})
        self.assertEqual(inherited.dependencies, value.dependencies)
        self.assertTrue(plan['clone'])
        for bad in ({'rerun_stage': 'grading'}, {'resume': True}, {'session_ids': ['s1']}):
            with self.assertRaises(ValueError):
                choose_rerun_runtime(root, '试卷.pdf', dict(bad, notebook_skill_selection=self.selected), workspace='synthetic_book')
        updated, plan = choose_rerun_runtime(root, '试卷.pdf', {
            'rerun_stage': 'all', 'full_recompute': True, 'notebook_skill_selection': self.selected}, workspace='synthetic_book')
        self.assertNotEqual(updated.fingerprint, value.fingerprint)
        self.assertFalse(plan['clone'])
        self.assertIn('另一个方法', updated.dependencies['references']['notebook_skills']['members'][0]['text'])

    def test_legacy_fingerprint_unchanged_and_unknown_or_corrupt_rejected(self):
        old = runtime()
        self.assertEqual(freeze_feedback_runtime(old.context, **old.dependencies).fingerprint, old.fingerprint)
        self.assertEqual(skills.usage_summary(old)['status'], 'unrecorded')
        for field, bad in [('schema_version', 'future'), ('adapter_version', 'future')]:
            bundle = self.bundle(); bundle[field] = bad
            with self.assertRaises(ValueError): frozen(bundle)
        bundle = self.bundle(); bundle['members'][0]['text'] += '篡改'
        with self.assertRaises(ValueError): frozen(bundle)

    def test_phase_consumers_and_retry_requests_audited(self):
        value = frozen(self.bundle())
        layout = system_prompt(value, 'detect')
        self.assertNotIn('先列条件', layout)
        self.assertNotIn('notebook_skills', layout)
        prompts = {'grade': system_prompt(value, 'grade'), 'review': system_prompt(value, 'review'),
                   'ontology': diagnostic_system(value, 'ontology'), 'pass2': diagnostic_system(value, 'pass2')}
        for phase, prompt in prompts.items():
            with self.subTest(phase=phase):
                audit = Path(self.temp.name) / f'{phase}.responses.json'
                calls = []
                def call(messages):
                    calls.append(messages)
                    self.assertEqual(skills.audit_messages(messages)[0]['phase'], phase)
                    return {'choices': [{'message': {'content': '{}' if len(calls) == 1 else '{"ok":true}'}, 'finish_reason': 'stop'}]}
                def validate(result):
                    if not result.get('ok'): raise ValueError('需要局部修复')
                    return result
                output = request_json_object(call, [{'role': 'system', 'content': prompt}],
                    parser=json.loads, validate=validate, audit_path=str(audit), stage=phase)
                self.assertTrue(output['ok'])
                self.assertEqual(len(calls), 2)
                records = json.loads(audit.read_text(encoding='utf-8'))['attempts']
                self.assertEqual([a['status'] for a in records], ['rejected', 'accepted'])
                self.assertTrue(all(a['request_sent'] for a in records))
        summary = skills.usage_summary(value, self.temp.name)
        self.assertEqual(next(s for s in summary['stages'] if s['phase'] == 'grade')['accepted'], 1)
        self.assertEqual(next(s for s in summary['stages'] if s['phase'] == 'pass2')['sent'], 2)

    def test_checkpoint_audit_is_reuse_not_new_send(self):
        value = frozen(self.bundle())
        path = Path(self.temp.name) / 'cached.responses.json'
        with patch('app_chat.homework_grading.execution_checkpoints.load_checkpoint', return_value={'ok': True}):
            request_json_object(lambda _: self.fail('不得调用模型'),
                [{'role': 'system', 'content': system_prompt(value, 'grade')}],
                parser=json.loads, validate=lambda x: x, audit_path=str(path), stage='grade')
        row = next(s for s in skills.usage_summary(value, self.temp.name)['stages'] if s['phase'] == 'grade')
        self.assertEqual(row, {'phase': 'grade', 'label': '理解', 'sent': 0, 'accepted': 0, 'reused': 1})

    def usage_audit(self, value, identity='synthetic-request'):
        return {'attempts': [{'invocation_id': identity, 'attempt': 1, 'status': 'accepted',
                'request_sent': True, 'notebook_skills': skills.audit_messages([
                    {'role': 'system', 'content': system_prompt(value, 'grade')}])}]}

    def test_usage_reads_long_transaction_paths_and_deduplicates_copies(self):
        value = frozen(self.bundle())
        root = Path(self.temp.name) / 'long-run'
        self.addCleanup(shutil.rmtree, windows_io_path(root))
        base = root / ('run-' + 'a' * 100) / 'homework_grading'
        candidate = base / 'artifact_transactions' / ('b' * 32) / 'candidate' / 'pass1_json'
        audit = candidate / 'page1.responses.json'
        self.assertGreater(len(str(audit)), 260)
        record = self.usage_audit(value)
        safe_json_dump(audit, record)
        safe_json_dump(base / 'pass1_json/page1.responses.json', record)
        safe_json_dump(candidate / 'page2.responses.json', self.usage_audit(value, 'second-request'))
        summary = skills.usage_summary(value, base)
        row = next(s for s in summary['stages'] if s['phase'] == 'grade')
        self.assertEqual(row['sent'], 2)
        self.assertEqual(row['accepted'], 2)
        self.assertEqual(summary['unreadable_audits'], 0)

    def test_usage_directory_scan_failure_preserves_available_counts(self):
        value = frozen(self.bundle())
        root = Path(self.temp.name)
        safe_json_dump(root / 'good.responses.json', self.usage_audit(value))
        def walk(base, *, onerror, followlinks):
            onerror(PermissionError('synthetic unreadable directory'))
            yield str(base), [], ['good.responses.json']
        with patch.object(skills.os, 'walk', side_effect=walk):
            summary = skills.usage_summary(value, root)
        self.assertEqual(summary['unreadable_audits'], 1)
        self.assertEqual(next(s for s in summary['stages'] if s['phase'] == 'grade')['accepted'], 1)

    def test_usage_bad_audit_is_reported_without_losing_good_records(self):
        value = frozen(self.bundle())
        root = Path(self.temp.name)
        (root / 'bad.responses.json').write_text('{broken', encoding='utf-8')
        safe_json_dump(root / 'good.responses.json', self.usage_audit(value))
        summary = skills.usage_summary(value, root)
        self.assertEqual(summary['unreadable_audits'], 1)
        self.assertEqual(next(s for s in summary['stages'] if s['phase'] == 'grade')['accepted'], 1)

    def test_queue_failure_does_not_claim_request_sent(self):
        from .execution_control import BudgetExceeded
        value = frozen(self.bundle())
        path = Path(self.temp.name) / 'failed.responses.json'
        def call(_): raise BudgetExceeded('模拟排队失败', scope='queue')
        with self.assertRaises(BudgetExceeded):
            request_json_object(call, [{'role': 'system', 'content': system_prompt(value, 'grade')}],
                parser=json.loads, validate=lambda x: x, audit_path=str(path), stage='grade')
        row = json.loads(path.read_text(encoding='utf-8'))['attempts'][0]
        self.assertFalse(row['request_sent'])
        self.assertTrue(row['request_attempted'])

    def test_material_blocker_prevents_completion_and_quality_not_generic_uncertain(self):
        manifest = complete_manifest()
        pages = [{'page': 2, 'questions': [{'id': '1', 'verdict': 'uncertain',
                 'material_check': {'status': 'unresolved', 'blocks_assessment': True}}]}]
        manifest['material_evidence'] = material_evidence_summary(pages)
        status = summarize_completion(manifest)
        self.assertEqual(status['status'], 'incomplete')
        self.assertFalse(available_actions(manifest, status, snapshot_ok=True, artifacts_ok=True)['retry_quality']['enabled'])
        pages[0]['questions'][0]['material_check'] = {}
        manifest['material_evidence'] = material_evidence_summary(pages)
        self.assertEqual(summarize_completion(manifest)['status'], 'complete')

    def test_coordinated_denials_and_real_assertions(self):
        pattern = r'不会|未掌握|答错|漏答|不正确'
        for text in ['不能据此判断学生不会或未掌握。', '不据此判断掌握或不会。',
                     '不能据此判断学生未掌握和不会。']:
            with self.subTest(text=text): self.assertEqual(phrase_findings(text, pattern), [])
        for text in ['并非不能判断学生不会或未掌握。', '不能据此判断学生不会，但是学生未掌握。', '学生未掌握。']:
            with self.subTest(text=text): self.assertTrue(phrase_findings(text, pattern))

    def test_open_material_diagnosis_uses_ontology_stage_and_actual_pass2_saves_report(self):
        from .feedback_skills_test import runtime_fixture
        from .feedback_runtime import stamp_feedback
        from . import grader_pass2, feedback_model
        base = runtime_fixture('初中·初一·数学·笔记.pdf')
        deps = base.dependencies
        deps['references']['notebook_skills'] = self.bundle()
        value = freeze_feedback_runtime(base.context, **deps)
        audit = skills.audit_messages([{'role': 'system', 'content': diagnostic_system(value, 'ontology')}])
        self.assertEqual(audit[0]['phase'], 'ontology')
        # 题目型产物回放测试实际Pass2模型调用、校验与落盘；不是模拟学生标准答案。
        base = runtime_fixture()
        deps = base.dependencies; deps['references']['notebook_skills'] = self.bundle()
        value = freeze_feedback_runtime(base.context, **deps)
        memory = stamp_feedback({'error_questions': [{'qid_global': 'p1:1', 'page': 1, 'id': '1'}]}, value)
        ontology = stamp_feedback({'zones': {'blind_spot': [], 'friction_zone': [], 'zpd': []}}, value)
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            self.assertEqual(skills.audit_messages(kwargs['messages'])[0]['phase'], 'pass2')
            payload = {'per_question_feedback': [{'qid_global': 'p1:1', 'page': 1, 'id': '1',
                        'zone': '', 'comment': '合成接口反馈：先列条件，再检查反例。'}]}
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(payload, ensure_ascii=False), reasoning_content=''), finish_reason='stop')])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        target = Path(self.temp.name) / 'actual_report.json'
        with patch.object(grader_pass2, '_deepseek_client', return_value=client), \
                patch.object(feedback_model, 'runtime_client', side_effect=lambda c, *_: c):
            result = grader_pass2.analyze_pass2(memory, 'physics', 'synthetic', str(target),
                str(Path(self.temp.name) / 'thinking.txt'), ontology=ontology, feedback_runtime=value)
        self.assertTrue(calls)
        self.assertEqual(result['per_question_feedback'][0]['qid_global'], 'p1:1')
        self.assertIn('先列条件', target.read_text(encoding='utf-8'))
        self.assertTrue(any(s['accepted'] for s in skills.usage_summary(value, self.temp.name)['stages']))

    def test_normal_start_freezes_selected_content_and_disabled_start_changes_run(self):
        import fitz
        from . import feedback_start_service as start
        from .feedback_start_service_test import InlineThread
        from .feedback_metadata import resolve_feedback_metadata
        from .feedback_workspaces import current_directory
        from app_chat.ci.task_store import update_task
        source = self.book / 'fixture.pdf'
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72, 72), 'Synthetic protocol fixture')
            pdf.save(source)
        container = Path(self.temp.name) / 'runs'
        config = {k: runtime().dependencies[k] for k in ('model_config', 'preprocessing', 'retrieval')}
        def worker(task_id, *args, **kwargs):
            update_task(task_id, {'completed': True})
        with ExitStack() as stack:
            stack.enter_context(patch('app_chat.homework_grading.feedback_runtime_service.execution_configuration', return_value=config))
            stack.enter_context(patch('app_chat.homework_grading.homework_versions._container_root', return_value=str(container)))
            stack.enter_context(patch.object(start.threading, 'Thread', InlineThread))
            stack.enter_context(patch.object(start.CIIndexManager, 'find_by_id', return_value=None))
            stack.enter_context(patch.object(start.CIIndexManager, 'restore_record'))
            stack.enter_context(patch('app_chat.homework_grading.service.check_homework_stage_ready', return_value=False))
            stack.enter_context(patch('app_chat.homework_grading.service.run_homework_grading', side_effect=worker))
            resolution = {'route': 'homework_grading', 'warnings': [],
                          'feedback_context': resolve_feedback_metadata('高中·高二·物理·试卷.pdf')}
            first = start.start_grading_request('synthetic_book', 'fixture.pdf',
                {'notebook_skill_selection': self.selected}, resolution=resolution)
            original = current_directory(container)
            restored = restore_feedback_runtime(original)
            self.assertEqual(restored.dependencies['references']['notebook_skills']['members'][0]['name'], 'method')
            second = start.start_grading_request('synthetic_book', 'fixture.pdf',
                {'notebook_skill_selection': {'enabled': False, 'names': []}}, resolution=resolution)
            self.assertNotEqual(first['run_id'], second['run_id'])
            self.assertNotEqual(first['config_fingerprint'], second['config_fingerprint'])
            self.assertTrue((original / 'reference_snapshot.json').exists())
            with patch('app_chat.feedback_material_settings.merge_saved_material_settings',
                       side_effect=AssertionError('仅更换Skill不能静默采用最新材料设置')):
                third = start.start_grading_request('synthetic_book', 'fixture.pdf', {
                    'analysis_id': second['analysis_id'], 'rerun_stage': 'all', 'full_recompute': True,
                    'notebook_skill_selection': self.selected}, rerun=True)
            self.assertEqual(third['feedback_context'], first['feedback_context'])


if __name__ == '__main__':
    unittest.main()
