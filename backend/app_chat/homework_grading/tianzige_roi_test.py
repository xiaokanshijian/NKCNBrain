import os
import tempfile
import unittest

import cv2
import numpy as np

from app_chat.homework_grading.tianzige_roi import (
    crop_tianzige_evidence,
    crop_tianzige_targets,
    detect_tianzige_cells,
)


class TianzigeRoiTest(unittest.TestCase):
    def _write_grid(self, path, groups, *, missing_boundaries=()):
        image = np.full((320, 900, 3), 255, dtype=np.uint8)
        top, bottom = 100, 160
        x = 70
        boundary_number = 0
        for group_index, count in enumerate(groups):
            left = x
            right = x + count * 60
            cv2.line(image, (left, top), (right, top), (0, 0, 0), 2)
            cv2.line(image, (left, bottom), (right, bottom), (0, 0, 0), 2)
            for offset in range(count + 1):
                boundary_number += 1
                if boundary_number not in missing_boundaries:
                    bx = left + offset * 60
                    cv2.line(image, (bx, top), (bx, bottom), (0, 0, 0), 2)
            # Handwriting-like strokes must not be promoted to full grid boundaries.
            cv2.line(image, (left + 18, top + 12), (left + 42, bottom - 12), (0, 0, 0), 3)
            x = right + (30 if group_index < len(groups) - 1 else 0)
        ok = cv2.imencode('.png', image)[1]
        ok.tofile(path)
        return [
            int(round(55 / 900 * 1000)),
            265,
            int(round(min(895, x + 15) / 900 * 1000)),
            535,
        ]

    def test_detects_exact_two_and_ten_real_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            for groups, count in (((2,), 2), ((2, 2, 2, 2, 2), 10)):
                with self.subTest(groups=groups):
                    path = os.path.join(tmp, f'grid-{count}.png')
                    position = self._write_grid(path, groups)
                    roi = detect_tianzige_cells(path, position, count)
                    self.assertEqual(roi['status'], 'available')
                    self.assertEqual(len(roi['cells']), count)
                    self.assertLessEqual(roi['width_cv'], 0.20)
                    if len(groups) > 1:
                        self.assertEqual(roi['group_break_slots'], [2, 4, 6, 8])

    def test_missing_separator_fails_without_equal_division_or_interpolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'missing.png')
            position = self._write_grid(path, (2,), missing_boundaries=(2,))
            roi = detect_tianzige_cells(path, position, 2)
            self.assertEqual(roi['status'], 'roi_unavailable')
            self.assertEqual(roi['cells'], [])
            self.assertIn(roi['failure_reason'], {
                'detected_slot_count_mismatch',
                'grid_row_pair_missing',
            })

    def test_count_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'two.png')
            position = self._write_grid(path, (2,))
            roi = detect_tianzige_cells(path, position, 3)
            self.assertEqual(roi['status'], 'roi_unavailable')
            self.assertEqual(roi['cells'], [])

            three_path = os.path.join(tmp, 'three.png')
            three_position = self._write_grid(three_path, (3,))
            subset = detect_tianzige_cells(three_path, three_position, 2)
            self.assertEqual(subset['status'], 'roi_unavailable')
            self.assertEqual(subset['detected_slot_count'], 3)
            self.assertEqual(subset['cells'], [])

    def test_crops_target_and_whole_row_for_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'grid.png')
            position = self._write_grid(path, (2,))
            roi = detect_tianzige_cells(path, position, 2)
            crops = crop_tianzige_evidence(
                path,
                roi,
                [1, 2],
                os.path.join(tmp, 'audit'),
            )
            self.assertTrue(os.path.exists(crops['row_path']))
            self.assertEqual([item['slot'] for item in crops['targets']], [1, 2])
            self.assertTrue(all(os.path.exists(item['path']) for item in crops['targets']))
            self.assertLess(crops['targets'][0]['box'][0], roi['cells'][0][0])
            self.assertGreater(crops['targets'][0]['box'][2], roi['cells'][0][2])

    def test_single_cell_crop_does_not_generate_row_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'grid.png')
            position = self._write_grid(path, (2,))
            roi = detect_tianzige_cells(path, position, 2)
            prefix = os.path.join(tmp, 'single')
            crops = crop_tianzige_targets(path, roi, [2], prefix)

            self.assertEqual(list(crops), ['targets'])
            self.assertEqual([item['slot'] for item in crops['targets']], [2])
            self.assertTrue(os.path.exists(crops['targets'][0]['path']))
            self.assertFalse(os.path.exists(prefix + '.row.png'))


if __name__ == '__main__':
    unittest.main()
