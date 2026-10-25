import os
import tempfile
import unittest
from unittest import mock

import cv2
import fitz
import numpy as np

from app_chat.homework_grading.preprocess import (
    PREPROCESS_MODE_AUTO,
    PREPROCESS_MODE_OFF,
    PREPROCESS_MODE_PHOTO,
    PREPROCESS_MODE_SCAN,
    analyze_page_capture,
    build_student_ink_workflow_image,
    build_teacher_mark_mask,
    load_preprocess_metadata,
    normalize_preprocess_mode,
    preprocess_mode_from_manifest,
    preprocess_mode_matches_manifest,
    preprocess_pdf,
    preprocess_page_image,
    remove_red_ink,
)


class TeacherMarkResidualMaskTest(unittest.TestCase):
    def _synthetic_image(self) -> np.ndarray:
        image = np.full((15, 21, 3), 255, dtype=np.uint8)
        image[7, 10] = (0, 0, 220)       # unambiguous red teacher ink
        image[7, 11] = (245, 245, 250)   # low-saturation pale red residual
        image[7, 9] = (30, 30, 30)       # deep black student stroke
        image[6, 10] = (150, 150, 150)   # medium gray, protected as non-light
        image[1, 1] = (245, 245, 250)     # pale pixel unrelated to red ink
        return image

    def test_residual_expansion_removes_only_nearby_light_pixels(self):
        image = self._synthetic_image()

        cleaned, mask = remove_red_ink(
            image,
            remove_pale_residuals=True,
            return_mask=True,
        )

        self.assertEqual(mask[7, 10], 255)
        self.assertEqual(mask[7, 11], 255)
        self.assertTrue(np.array_equal(cleaned[7, 11], [255, 255, 255]))
        self.assertEqual(mask[7, 9], 0)
        self.assertTrue(np.array_equal(cleaned[7, 9], [30, 30, 30]))
        self.assertEqual(mask[6, 10], 0)
        self.assertTrue(np.array_equal(cleaned[6, 10], [150, 150, 150]))
        self.assertEqual(mask[1, 1], 0)
        self.assertTrue(np.array_equal(cleaned[1, 1], [245, 245, 250]))

    def test_environment_switch_restores_original_red_only_mask(self):
        image = self._synthetic_image()

        with mock.patch.dict(
            os.environ,
            {'HOMEWORK_RED_INK_RESIDUAL_MASK': '0'},
        ):
            mask = build_teacher_mark_mask(image)

        self.assertEqual(mask[7, 10], 255)
        self.assertEqual(mask[7, 11], 0)
        self.assertEqual(mask[7, 9], 0)

    def test_workflow_image_masks_page_wide_light_ghosts_but_keeps_dark_ink(self):
        image = np.full((5, 5, 3), 255, dtype=np.uint8)
        image[1, 1] = (225, 225, 230)
        image[2, 2] = (40, 40, 40)
        image[3, 3] = (180, 180, 180)

        workflow_image = build_student_ink_workflow_image(
            image,
            mask_light_residuals=True,
        )

        self.assertTrue(np.array_equal(workflow_image[1, 1], [255, 255, 255]))
        self.assertTrue(np.array_equal(workflow_image[2, 2], [40, 40, 40]))
        self.assertTrue(np.array_equal(workflow_image[3, 3], [180, 180, 180]))

    def test_workflow_image_environment_switch_preserves_red_clean_image(self):
        image = np.full((3, 3, 3), 255, dtype=np.uint8)
        image[1, 1] = (225, 225, 230)

        with mock.patch.dict(
            os.environ,
            {'HOMEWORK_GRADING_BLACK_INK_IMAGE': '0'},
        ):
            workflow_image = build_student_ink_workflow_image(image)

        self.assertTrue(np.array_equal(workflow_image, image))

    def test_legacy_review_switch_remains_a_compatible_fallback(self):
        image = np.full((3, 3, 3), 255, dtype=np.uint8)
        image[1, 1] = (225, 225, 230)

        with mock.patch.dict(
            os.environ,
            {
                'HOMEWORK_PASS1_REVIEW_BLACK_INK_IMAGE': '0',
            },
        ):
            os.environ.pop('HOMEWORK_GRADING_BLACK_INK_IMAGE', None)
            workflow_image = build_student_ink_workflow_image(image)

        self.assertTrue(np.array_equal(workflow_image, image))


class AdaptivePreprocessTest(unittest.TestCase):
    def _scan_image(self) -> np.ndarray:
        image = np.full((240, 320, 3), 255, dtype=np.uint8)
        for y in range(35, 215, 30):
            cv2.line(image, (25, y), (285, y), (30, 30, 30), 3)
        cv2.line(image, (80, 20), (230, 220), (0, 0, 210), 4)
        return image

    def _photo_image(self) -> np.ndarray:
        height, width = 240, 320
        yy, xx = np.mgrid[0:height, 0:width]
        blue = 145 + 30 * xx / width + 8 * yy / height
        green = 178 + 35 * xx / width + 10 * yy / height
        red = 212 + 32 * xx / width + 8 * yy / height
        image = np.dstack((blue, green, red)).clip(0, 255).astype(np.uint8)
        for y in range(40, 215, 32):
            cv2.line(image, (28, y), (290, y), (35, 35, 35), 3)
        return image

    def test_auto_scan_path_is_pixel_identical_to_legacy_pipeline(self):
        image = self._scan_image()
        expected = build_student_ink_workflow_image(remove_red_ink(image))

        cleaned, record, candidate = preprocess_page_image(
            image,
            requested_mode=PREPROCESS_MODE_AUTO,
        )

        self.assertEqual(analyze_page_capture(image)['classification'], PREPROCESS_MODE_SCAN)
        self.assertEqual(record['effective_mode'], PREPROCESS_MODE_SCAN)
        self.assertIsNone(candidate)
        self.assertTrue(np.array_equal(cleaned, expected))

    def test_warm_uneven_page_routes_to_photo_enhancement(self):
        image = self._photo_image()

        cleaned, record, candidate = preprocess_page_image(
            image,
            requested_mode=PREPROCESS_MODE_AUTO,
        )

        self.assertEqual(analyze_page_capture(image)['classification'], PREPROCESS_MODE_PHOTO)
        self.assertEqual(record['effective_mode'], PREPROCESS_MODE_PHOTO)
        self.assertFalse(record['fallback_used'])
        self.assertIsNotNone(candidate)
        self.assertTrue(np.array_equal(cleaned, candidate))

    def test_auto_blank_page_and_explicit_off_preserve_original(self):
        image = np.full((120, 180, 3), 255, dtype=np.uint8)

        auto_cleaned, auto_record, _ = preprocess_page_image(image, PREPROCESS_MODE_AUTO)
        off_cleaned, off_record, _ = preprocess_page_image(image, PREPROCESS_MODE_OFF)

        self.assertEqual(auto_record['classification'], 'blank')
        self.assertEqual(auto_record['effective_mode'], PREPROCESS_MODE_OFF)
        self.assertEqual(off_record['effective_mode'], PREPROCESS_MODE_OFF)
        self.assertTrue(np.array_equal(auto_cleaned, image))
        self.assertTrue(np.array_equal(off_cleaned, image))

    def test_photo_quality_failure_falls_back_to_original(self):
        image = self._photo_image()
        failed_gate = {
            'passed': False,
            'reasons': ['非红笔迹保留不足'],
        }

        with mock.patch(
            'app_chat.homework_grading.preprocess.evaluate_photo_candidate',
            return_value=failed_gate,
        ):
            cleaned, record, candidate = preprocess_page_image(
                image,
                requested_mode=PREPROCESS_MODE_PHOTO,
            )

        self.assertEqual(record['effective_mode'], PREPROCESS_MODE_OFF)
        self.assertTrue(record['fallback_used'])
        self.assertIn('非红笔迹保留不足', record['fallback_reason'])
        self.assertIsNotNone(candidate)
        self.assertTrue(np.array_equal(cleaned, image))

    def test_mode_helpers_keep_legacy_manifests_compatible(self):
        self.assertEqual(normalize_preprocess_mode(' PHOTO '), PREPROCESS_MODE_PHOTO)
        self.assertEqual(normalize_preprocess_mode('invalid', default=''), '')
        self.assertEqual(preprocess_mode_from_manifest({}), PREPROCESS_MODE_SCAN)
        self.assertEqual(preprocess_mode_from_manifest({'preprocess': {}}), PREPROCESS_MODE_SCAN)
        manifest = {'preprocess': {'requested_mode': PREPROCESS_MODE_AUTO}}
        self.assertTrue(preprocess_mode_matches_manifest(manifest, PREPROCESS_MODE_AUTO))
        self.assertFalse(preprocess_mode_matches_manifest(manifest, PREPROCESS_MODE_SCAN))

    def test_off_mode_copies_rendered_png_bytes_and_writes_audit_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            pdf_path = os.path.join(temp_dir, 'input.pdf')
            document = fitz.open()
            page = document.new_page(width=320, height=240)
            page.insert_text((40, 80), 'student answer', fontsize=18)
            document.save(pdf_path)
            document.close()
            raw_dir = os.path.join(temp_dir, 'raw')
            clean_dir = os.path.join(temp_dir, 'clean')
            metadata_path = os.path.join(temp_dir, 'preprocess_meta.json')

            pages = preprocess_pdf(
                pdf_path,
                raw_dir,
                clean_dir,
                'english',
                'sample',
                preprocess_mode=PREPROCESS_MODE_OFF,
                metadata_path=metadata_path,
            )

            with open(pages[0]['raw_abs_path'], 'rb') as raw_file:
                raw_bytes = raw_file.read()
            with open(pages[0]['clean_abs_path'], 'rb') as clean_file:
                clean_bytes = clean_file.read()
            metadata = load_preprocess_metadata(metadata_path)
            self.assertEqual(raw_bytes, clean_bytes)
            self.assertEqual(metadata['requested_mode'], PREPROCESS_MODE_OFF)
            self.assertEqual(metadata['summary']['off_page_count'], 1)
            with self.assertRaisesRegex(ValueError, '完整迭代整份作业'):
                preprocess_pdf(
                    pdf_path,
                    raw_dir,
                    clean_dir,
                    'english',
                    'sample',
                    page_numbers=[1],
                    preprocess_mode=PREPROCESS_MODE_SCAN,
                    metadata_path=metadata_path,
                )


if __name__ == '__main__':
    unittest.main()
