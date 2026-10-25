import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app_chat import ci_test_support  # noqa: F401
from .completion import (summarize_completion, finish_delivery, available_actions,
                         review_coverage, saved_report_ready)


def complete_manifest():
    return {'status': 'completed', 'processing_stage': 'completed', 'target_stage': 'grading',
            'stages': {'layout': 'done', 'understanding': 'done', 'grading': 'done'},
            'pass1_review': {'enabled': True, 'errors': 0, 'quota_limited': False,
                            'coverage': review_coverage([1, 2], [{'page': 1}, {'page': 2}])},
            'hallucination': {'status': 'ready'}, 'content_validation': {'status': 'inconclusive'},
            'red_blue_review': {'status': 'ready'},
            'output_validation': {'status': 'passed', 'target_stage': 'grading'}}


class CompletionTest(unittest.TestCase):
    def test_review_quality_matrix_keeps_report_but_never_claims_full_delivery(self):
        for review in ('passed', 'failed', 'quota', 'missing', 'final_failed', 'feedback_partial'):
            for quality in ('ready', 'failed'):
                with self.subTest(review=review, quality=quality):
                    manifest = complete_manifest()
                    manifest['red_blue_review']['status'] = quality
                    if review == 'failed': manifest['pass1_review']['errors'] = 1
                    if review == 'quota': manifest['pass1_review']['quota_limited'] = True
                    if review == 'missing': manifest['pass1_review']['coverage']['incomplete_pages'] = [2]
                    if review == 'final_failed': manifest['content_validation']['failed_checks'] = ['hallucination']
                    if review == 'feedback_partial': manifest['content_validation']['status'] = 'needs_review'
                    result = finish_delivery(manifest)
                    self.assertEqual(result['report_usable'], review == 'passed')
                    all_done = review == 'passed' and quality == 'ready'
                    self.assertEqual(result['status'], 'complete' if all_done else 'incomplete')
                    self.assertEqual(manifest['status'], 'completed' if all_done else 'partial')
                    actions = available_actions(manifest, result, snapshot_ok=True, artifacts_ok=True)
                    self.assertEqual(actions['retry_quality']['enabled'], review == 'passed' and quality != 'ready')

    def test_coverage_distinguishes_policy_skip_missing_image_and_quota(self):
        coverage = review_coverage([1, 2, 3, 4], [
            {'page': 1}, {'page': 2, 'skipped': True, 'skip_reason': 'no_high_risk_verdict'},
            {'page': 3, 'skipped': True, 'skip_reason': 'gemini_quota_limited'}])
        self.assertEqual(coverage['policy_skipped_pages'], [2])
        self.assertEqual(coverage['incomplete_pages'], [3, 4])
        self.assertEqual(review_coverage([1], [{'page': 1, 'skipped': True,
                                               'skip_reason': 'not_skipped'}])['incomplete_pages'], [1])
        manifest = complete_manifest()
        manifest['pass1_review']['coverage'] = review_coverage([1], [
            {'page': 1, 'skipped': True, 'skip_reason': 'no_high_risk_verdict'}])
        self.assertEqual(summarize_completion(manifest)['status'], 'complete')

    def test_early_targets_do_not_require_review_report_or_quality(self):
        for target in ('layout', 'understanding'):
            manifest = {'target_stage': target, 'stages': {target: 'done'},
                        'output_validation': {'status': 'passed', 'target_stage': target}}
            result = finish_delivery(manifest)
            self.assertEqual(result['status'], 'complete')
            self.assertFalse(result['report_usable'])
            self.assertEqual(manifest['status'], 'partial')

    def test_historical_read_is_unverified_and_does_not_write_or_invent_success(self):
        manifest = complete_manifest()
        manifest.pop('output_validation')
        before = copy.deepcopy(manifest)
        self.assertEqual(summarize_completion(manifest)['status'], 'unverified')
        self.assertEqual(manifest, before)
        manifest['pass1_review']['errors'] = 1
        self.assertEqual(summarize_completion(manifest)['status'], 'incomplete')

    def test_task_lifecycle_and_old_completion_are_not_delivery_evidence(self):
        manifest = complete_manifest()
        manifest.update(status='running', processing_stage='review', completion={'status': 'complete'})
        result = summarize_completion(manifest)
        self.assertEqual(result['status'], 'running')
        self.assertFalse(result['report_usable'])
        self.assertFalse(available_actions(manifest, result, snapshot_ok=True, artifacts_ok=True)['retry_quality']['enabled'])
        manifest.update(status='interrupted', processing_stage='review')
        actions = available_actions(manifest, summarize_completion(manifest), snapshot_ok=True)
        self.assertTrue(actions['resume']['enabled'])
        self.assertEqual(actions['resume']['rerun_stage'], 'grading')
        self.assertFalse(available_actions(manifest, result, snapshot_ok=True, current=False)['resume']['enabled'])

    def test_successful_quality_retry_clears_only_resolved_warning(self):
        manifest = complete_manifest()
        manifest['warnings'] = ['保留的其他告警', '批改结果已保留，但质量评分未成功；可在结果中单独重试评分']
        manifest['completion'] = {'status': 'incomplete'}
        finish_delivery(manifest)
        self.assertEqual(manifest['warnings'], ['保留的其他告警'])
        self.assertEqual(manifest['completion']['status'], 'complete')

    def test_saved_receipt_checks_original_bytes_without_invalidating_for_new_code(self):
        from .feedback_artifacts_test import ArtifactTest
        from .execution_checkpoints import stage_receipt
        with tempfile.TemporaryDirectory() as tmp:
            paths, pages, metadata, _ = ArtifactTest().fixture(tmp)
            paths['base'] = tmp
            manifest = {**metadata, **complete_manifest(), 'source_page_count': 2}
            manifest['stage_receipts'] = {'grading': stage_receipt(paths, 'grading',
                manifest['config_fingerprint'], code={'actual_code_fingerprint': 'saved-old-code'})}
            with patch('app_chat.homework_grading.staged_pipeline.load_homework_clean_pages', return_value=pages):
                self.assertTrue(saved_report_ready(paths, manifest))
                page = Path(paths['pass1_json']) / 'synthetic_page1.json'
                page.write_text(json.dumps({'questions': [{'id': 'changed'}]}))
                self.assertFalse(saved_report_ready(paths, manifest))
                result = summarize_completion(manifest, artifacts_valid=False)
                self.assertEqual(result['status'], 'incomplete')
                self.assertFalse(result['report_usable'])


if __name__ == '__main__':
    unittest.main()
