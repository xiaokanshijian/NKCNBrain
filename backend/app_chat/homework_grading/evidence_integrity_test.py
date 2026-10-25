"""Synthetic offline fixtures for evidence correction; no model calls."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app_chat.homework_grading import hallucination_filter as hf


class EvidenceIntegrityTest(unittest.TestCase):
    def test_cleanup_never_splits_scalars_and_is_idempotent(self):
        from app_chat.homework_grading.grader_pass2 import _flatten_ontology_evidence
        valid = {'p7:4-5', 'p31:4-2'}
        for bad in ('3-1', ['3', '1'], 12, {'id': 'p7:4-5'}, None):
            with self.subTest(value=bad):
                item = {'evidence': bad, 'evidence_question_ids': bad,
                        'error_clusters': [{'evidence': 'p7:4-5'}]}
                zones = {'zpd': [item]}
                hf._apply_zone_corrections(zones, valid, set(), set())
                self.assertEqual(item['evidence'], [])
                self.assertEqual(item['evidence_question_ids'], [])
                self.assertEqual(item['error_clusters'][0]['evidence'], ['p7:4-5'])
                self.assertEqual(_flatten_ontology_evidence(item), ['p7:4-5'])
                self.assertEqual(hf._apply_zone_corrections(zones, valid, set(), set()), [])
        self.assertEqual(_flatten_ontology_evidence({'evidence': '3-1'}), [])
        self.assertEqual(_flatten_ontology_evidence({'evidence': 'p31:4-2'}), ['p31:4-2'])

    def test_retry_preserves_array_members_and_backup(self):
        for source, root, field in [('pass2', 'zone_classification', 'evidence_question_ids'),
                                    ('ontology', 'zones', 'evidence')]:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'report.json'
                before = {root: {'zpd': [{field: ['p3:1', 'p7:4-5', 'p31:4-2']}]}}
                path.write_text(json.dumps(before), encoding='utf8')
                issue = dict(source=source, zone='zpd', index=0, field=field,
                             value='p3:1', hallucination_type='invalid_id')
                audit = []
                hf._pre_patch_with_retry(folder, str(path), str(path),
                                         {hf._issue_key(issue): 'p3:3-1'}, [issue], audit)
                after = json.loads(path.read_text(encoding='utf8'))
                self.assertEqual(after[root]['zpd'][0][field], ['p3:3-1', 'p7:4-5', 'p31:4-2'])
                self.assertEqual(json.loads(Path(str(path)+'.corrected.bak').read_text(encoding='utf8')), before)
                self.assertEqual(audit[0]['before'], before[root]['zpd'][0][field])
                self.assertEqual(audit[0]['after'], after[root]['zpd'][0][field])

    def test_bare_ids_not_in_whitelist_or_accepted_by_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'sample_page3.json').write_text(json.dumps(
                {'page': 3, 'questions': [{'id': '3-1'}, {'id': '1'}]}), encoding='utf8')
            valid = hf._collect_question_ids(folder)
        self.assertEqual(valid, {'p3:3-1', 'p3:1'})
        issue = dict(field='evidence', value='p99:1', hallucination_type='invalid_id')
        with patch.object(hf, '_call_retry', return_value='3-1'):
            self.assertIsNone(hf.retry_field(issue, set(), valid, set())['new_value'])


if __name__ == '__main__':
    unittest.main()
