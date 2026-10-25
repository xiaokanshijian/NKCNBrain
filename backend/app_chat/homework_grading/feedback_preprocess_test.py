import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from .feedback_metadata import resolve_feedback_metadata
from .feedback_runtime import prepare_feedback_runtime
from .preprocess import preprocess_page_image
from .utils import write_sample_meta


def runtime():
    return prepare_feedback_runtime(
        resolve_feedback_metadata('大学·大二·嵌入式系统·试卷.pdf'),
        model_config={'version': 'synthetic'}, retrieval={'version': 'synthetic'},
        references={'status': 'not_provided', 'reference_text': '', 'documents': []},
        preprocessing={'version': 'synthetic', 'mode': 'scan', 'environment': {
            'HOMEWORK_RED_INK_RESIDUAL_MASK': '0',
            'HOMEWORK_GRADING_BLACK_INK_IMAGE': '0'}})


class FrozenPreprocessTest(unittest.TestCase):
    def test_environment_changes_do_not_change_scan_pixels(self):
        frozen = runtime()
        source = np.full((100, 100, 3), 240, dtype=np.uint8)
        source[40:45, 40:45] = (0, 0, 255)
        with patch.dict('os.environ', {'HOMEWORK_GRADING_BLACK_INK_IMAGE': '1',
                                      'HOMEWORK_RED_INK_RESIDUAL_MASK': '1'}):
            actual, _, _ = preprocess_page_image(source, 'scan', feedback_runtime=frozen)
        with patch.dict('os.environ', {'HOMEWORK_GRADING_BLACK_INK_IMAGE': '0',
                                      'HOMEWORK_RED_INK_RESIDUAL_MASK': '0'}):
            expected, _, _ = preprocess_page_image(source, 'scan')
        np.testing.assert_array_equal(actual, expected)
        self.assertEqual(actual[0, 0, 0], 240)

    def test_metadata_uses_frozen_university_identity(self):
        frozen = runtime()
        with tempfile.TemporaryDirectory() as root:
            meta = write_sample_meta(root, 'math', 'synthetic', 4,
                                     feedback_runtime=frozen)
        self.assertIsNone(meta['grade'])
        self.assertIsNone(meta['stage'])
        self.assertEqual(meta['feedback_context']['grade_in_level'], 2)
        self.assertEqual(meta['config_fingerprint'], frozen.fingerprint)


if __name__ == '__main__':
    unittest.main()
