"""合成证据：不代表任何真实学生材料的标准答案。"""
import copy
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from .evidence_contract import (required_review_units, unit_coverage, material_groups,
                               material_dependency, valid_material_quotes)
from . import artifact_transaction as tx, staged_pipeline as pipeline
from .feedback_skills_test import runtime_fixture
from .grader_pass1_review import _page_needs_review
from .red_blue_pipeline_test import RedBluePipelineTest
from .utils import safe_json_dump, safe_json_load


class EvidenceContractTest(unittest.TestCase):
    def test_material_sources_preserve_answer_continuations_and_bound_budget(self):
        from .evidence_contract import combine_material_groups
        groups, blocked = combine_material_groups([[1, 4]], [[1, 2, 3]], 4)
        self.assertEqual(groups, [[1, 2, 3, 4]])
        self.assertFalse(blocked)
        groups, blocked = combine_material_groups([[1, 4]], [[1, 2, 3]], 3)
        self.assertEqual(blocked, {1, 2, 3, 4})
        self.assertTrue(all(len(group) <= 3 for group in groups))

    def test_late_negative_claim_requires_reviewed_evidence(self):
        from .evidence_contract import validate_final_evidence
        pages = [{'page': 1, 'questions': [{'id': '1', 'verdict': 'correct'}]}]
        report = {'per_question_feedback': [{'qid_global': 'p1:1', 'comment': '学生未掌握'}]}
        with self.assertRaises(ValueError):
            validate_final_evidence(report, {}, pages, [], [])
        validate_final_evidence(report, {}, pages, [], [1])
        report['per_question_feedback'][0]['comment'] = '不能据此判断学生未掌握'
        validate_final_evidence(report, {}, pages, [], [])

    def test_generic_partial_is_required_and_quota_is_not_success(self):
        page = {'page': 1, 'questions': [{'id': '1', 'verdict': 'partial', 'error_type': '合成疑点'}]}
        self.assertTrue(_page_needs_review(page, 'physics', feedback_runtime=runtime_fixture()))
        required = required_review_units(page)
        self.assertEqual(unit_coverage(required, [{'page': 1, 'skipped': True,
            'skip_reason': 'gemini_quota_limited'}])[0]['status'], 'quota_skipped')
        self.assertEqual(unit_coverage(required, [])[0]['status'], 'not_reviewed')
        page['questions'][0] = {'id': '1', 'verdict': 'correct', 'understanding': '可继续探索'}
        self.assertFalse(required_review_units(page))

    def test_material_sources_include_local_nonadjacent_and_indirect(self):
        pages = {1: {'questions': [{'id': 's', 'stem_excerpt': '材料一 合成甲'}]},
                 4: {'questions': [{'id': 's', 'stem_excerpt': '材料二 合成乙'},
                                   {'id': 'a', 'stem_excerpt': '结合上述两则材料作答'}]}}
        groups, blocked = material_groups(pages, 3)
        self.assertIn([1, 4], groups)
        self.assertFalse(blocked)
        dependency = material_dependency(pages[4]['questions'][1])
        units = {'p1:s': (1, pages[1]['questions'][0]), 'p4:s': (4, pages[4]['questions'][0])}
        evidence = [{'qid_global': ref, 'quote': text, 'material_label': label}
                    for ref, text, label in [('p1:s', '合成甲', '材料一'), ('p4:s', '合成乙', '材料二')]]
        self.assertTrue(valid_material_quotes(evidence, units, dependency))
        self.assertFalse(valid_material_quotes(evidence[:1], units, dependency))
        evidence[1]['quote'] = '编造的引文'
        self.assertFalse(valid_material_quotes(evidence, units, dependency))
        self.assertTrue(material_groups(pages, 1)[1])

    def test_images_are_private_until_commit_and_rollback_with_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            paths = {'base': str(base)}
            for name in ('pass1_json', 'pass2_report', 'annotated', 'annotated_understanding'):
                (base / name).mkdir()
                paths[name] = str(base / name)
            image = base / 'annotated/page.png'
            image.write_bytes(b'old')
            def fail(candidate):
                Path(candidate['annotated'], 'page.png').write_bytes(b'new')
                self.assertEqual(image.read_bytes(), b'old')
                raise RuntimeError('synthetic render failure')
            with self.assertRaises(RuntimeError):
                tx.candidate_transaction(paths, fail, include_images=True)
            self.assertEqual(image.read_bytes(), b'old')
            def succeed(candidate):
                Path(candidate['annotated'], 'page.png').write_bytes(b'new')
                safe_json_dump(Path(candidate['pass2_report'], 'report.json'), {'new': True})
            tx.candidate_transaction(paths, succeed, include_images=True)
            self.assertEqual(image.read_bytes(), b'new')
            self.assertTrue(safe_json_load(base / 'pass2_report/report.json')['new'])


class BoundedRebuildTest(unittest.TestCase):
    def run_case(self, repeat=False):
        helper = RedBluePipelineTest()
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            paths = helper._workspace(tmp)
            page_path = Path(paths['pass1_json'], 'math_fixture_page1.json')
            safe_json_dump(page_path, {'page': 1, 'questions': [{'id': '1', 'verdict': 'wrong', 'student_answer': 'old'}]})
            pages = [{'page': 1, 'clean_abs_path': str(Path(paths['clean'], 'math_fixture_page1.png'))}]
            helper._base_patches(stack, pages)
            def mock(name, **kwargs):
                return stack.enter_context(patch.object(pipeline, name, **kwargs))
            mock('_stages_needed_for_target', return_value=['grading'])
            mock('infer_homework_stage_status', return_value={'understanding': 'done'})
            for name in ('resolve_cross_pages', 'verify_pass1_dir', 'verify_answer_statements'):
                mock(name, return_value={})
            mock('review_pass1_dir', return_value={'enabled': True, 'details': [{'page': 1}], 'errors': 0})
            for name in ('_reapply_slot_presence_guards_for_pages', '_reapply_fixed_english_choice_guards_for_pages',
                         '_reapply_fixed_english_page15_guards_for_pages', '_reapply_fixed_math_sample_guards_for_pages'):
                mock(name, return_value=0)
            mock('slot_presence_mode', return_value='off')
            mock('build_memory', side_effect=lambda folder, *a, **k: {'error_questions': [
                dict(safe_json_load(next(Path(folder).glob('*page1.json')))['questions'][0], qid_global='p1:1')]})
            mock('save_memory')
            mock('build_all_session_memories', return_value=[])
            mock('build_student_profile', return_value={})
            mock('load_sample_meta', return_value={})
            def ontology(**kw):
                safe_json_dump(Path(kw['base_dir'], 'student_ontology.json'), {'zones': {}})
                return {'zones': {}}
            diagnostic = mock('build_ontology', side_effect=ontology)
            def report(memory, subject, sample, output, *a, **k):
                safe_json_dump(output, {'diagnosis': 'synthetic', 'per_question_feedback': [],
                                       'basis_answer': memory['error_questions'][0]['student_answer']})
            mock('analyze_pass2', side_effect=report)
            calls = []
            def review(subject, folder, *a, **kw):
                calls.append(1)
                target = next(Path(folder).glob('*page1.json'))
                value = safe_json_load(target)
                value['questions'][0]['student_answer'] = str(len(calls)) if repeat else 'corrected'
                safe_json_dump(target, value)
                return {'status': 'ready'}
            mock('run_hallucination_filter', side_effect=review)
            def render(current, *a, **kw):
                for name in ('annotated', 'annotated_understanding'):
                    Path(current[name], 'page.png').write_bytes(b'corrected-image')
            mock('_render_pages', side_effect=render)
            score = mock('evaluate_homework_red_blue', return_value={'status': 'ready'})
            mock('pass1_5_enabled', return_value=False)
            mock('build_pre_pass1_session_map', return_value=None)
            pipeline.execute_staged_homework_grading('synthetic', 'user', 'fixture.pdf', 'homework_fixture', paths,
                {'homework_subject': 'math', 'homework_grade': 4}, 'grading', lambda *a: [])
            manifest = safe_json_load(paths['manifest'])
            self.assertEqual(len(calls), 2)
            self.assertEqual(diagnostic.call_count, 2)
            if repeat:
                self.assertEqual(manifest['postprocess']['status'], 'rejected')
                self.assertEqual(safe_json_load(page_path)['questions'][0]['student_answer'], 'old')
                score.assert_not_called()
            else:
                self.assertEqual(manifest['postprocess']['rebuild_count'], 1)
                self.assertEqual(safe_json_load(page_path)['questions'][0]['student_answer'], 'corrected')
                report_path = next(Path(paths['pass2_report']).glob('*_report.json'))
                self.assertEqual(safe_json_load(report_path)['basis_answer'], 'corrected')
                self.assertEqual(Path(paths['annotated'], 'page.png').read_bytes(), b'corrected-image')
                score.assert_called_once()

    def test_fact_correction_rebuilds_report_and_images_once(self):
        self.run_case()

    def test_second_fact_change_rejects_candidate_and_does_not_score(self):
        self.run_case(repeat=True)
