import hashlib
import os
import tempfile
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from django.test import SimpleTestCase

from app_chat.homework_grading import fixed_sample_crossout, staged_pipeline


class FixedSampleCrossoutTest(SimpleTestCase):
    def test_long_path_image_write_rename_audit_and_model_read(self):
        from .utils import windows_io_path, safe_json_load, image_to_data_uri, image_to_data_uri_for_gemini_review
        import base64
        import shutil
        root = tempfile.mkdtemp(prefix='p03-crossout-path-')
        try:
            clean_path = os.path.join(root, 'math_sample_page15.png')
            image = np.full((12, 12, 3), 255, dtype=np.uint8)
            image[4:7, 4:7] = 0
            cv2.imencode('.png', image)[1].tofile(clean_path)
            source_hash = fixed_sample_crossout._sha256_file(clean_path)
            case = {'case_id': 'synthetic', 'subject': 'math', 'page': 15,
                    'source_sha256': source_hash, 'image_size_wh': [12, 12],
                    'operations': [{'type': 'whiteout', 'bbox_xyxy': [4, 4, 7, 7]}],
                    'expected_changed_pixel_count': 9}
            repaired, _ = fixed_sample_crossout.apply_fixed_sample_operations(image, case)
            case['expected_output_sha256'] = hashlib.sha256(cv2.imencode('.png', repaired)[1].tobytes()).hexdigest()
            target = os.path.join(root, 'a'*90, 'b'*90, 'fixed_sample_crossout')
            output, audit = fixed_sample_crossout.repair_fixed_sample_image(
                clean_path, target, 'math', 15, manifest={'version': 'test', 'cases': [case]})
            self.assertGreater(len(os.path.abspath(output)), 260)
            self.assertTrue(audit['applied'])
            self.assertFalse(os.path.exists(windows_io_path(output+'.tmp')))
            self.assertTrue(safe_json_load(output+'.audit.json')['original_clean_preserved'])
            for encode in (image_to_data_uri, image_to_data_uri_for_gemini_review):
                payload = base64.b64decode(encode(output).split(',', 1)[1])
                self.assertEqual(hashlib.sha256(payload).hexdigest(), case['expected_output_sha256'])
            self.assertEqual(fixed_sample_crossout._sha256_file(clean_path), source_hash)
        finally:
            shutil.rmtree(windows_io_path(root))

    def test_manifest_is_limited_to_the_six_approved_pages(self):
        manifest = fixed_sample_crossout.load_fixed_sample_crossout_manifest()
        cases = manifest['cases']
        self.assertEqual(manifest['version'], 'fixed_crossout_samples_v3')
        self.assertEqual(
            [(case['subject'], case['page']) for case in cases],
            [
                ('math', 15),
                ('math', 17),
                ('chinese', 3),
                ('chinese', 11),
                ('chinese', 13),
                ('chinese', 41),
            ],
        )
        self.assertEqual(
            [operation['question_id'] for operation in cases[0]['operations']],
            ['1', '1'],
        )
        self.assertEqual(
            [operation['question_id'] for operation in cases[1]['operations']],
            ['2-2', '2-3', '2-2'],
        )
        self.assertEqual(
            [operation['question_id'] for operation in cases[2]['operations']],
            ['3-1'],
        )
        self.assertEqual(
            cases[2]['operations'][0]['sample_part'],
            'incomplete_teacher_xiang_residual',
        )
        self.assertEqual(
            cases[2]['operations'][0]['bbox_xyxy'],
            [579, 1844, 626, 1940],
        )
        self.assertEqual(
            [operation['question_id'] for operation in cases[3]['operations']],
            ['4-4', '4-4'],
        )
        self.assertEqual(
            [operation['question_id'] for operation in cases[4]['operations']],
            ['4-2'],
        )
        self.assertEqual(
            [operation['question_id'] for operation in cases[5]['operations']],
            ['3-2', '3-2'],
        )
        self.assertEqual(
            [operation['type'] for operation in cases[3]['operations']],
            ['whiteout', 'whiteout_line'],
        )
        self.assertEqual(
            [case['expected_changed_pixel_count'] for case in cases[2:]],
            [1154, 2349, 1874, 6679],
        )
        self.assertEqual(
            [case['expected_output_sha256'] for case in cases[2:]],
            [
                '6b74bd241409206dac8ab0ee7815a6e3baa8470222e695ad3ff983048dd1e9e3',
                '687131f97355ed0206bbbdeff39e54245f3427bb837c0a4d77740fa00b46f276',
                '40890d462168e7002b3b1b15dff987f06ab9c0c1dbead2a4850ee10304e77b01',
                'feedd29e54ffd0dcd9087a6cbdb7da6ab02cfeea4a64e0c5e26f7cd1cb49b400',
            ],
        )

    def test_operations_modify_only_approved_pixels(self):
        image = np.full((20, 20, 3), 255, dtype=np.uint8)
        image[2:5, 2:5] = 0
        image[10:13, 10:13] = 0
        image[15, 2:7] = 0
        case = {
            'operations': [
                {'type': 'whiteout', 'bbox_xyxy': [10, 10, 13, 13]},
                {
                    'type': 'whiteout_line',
                    'start_xy': [2, 15],
                    'end_xy': [6, 15],
                    'thickness': 1,
                },
                {
                    'type': 'move_ink',
                    'source_bbox_xyxy': [2, 2, 5, 5],
                    'source_clear_bbox_xyxy': [1, 1, 6, 6],
                    'destination_bbox_xyxy': [14, 2, 17, 5],
                    'ink_threshold_gray_lt': 250,
                    'expected_ink_pixel_count': 9,
                },
            ],
            'expected_changed_pixel_count': 32,
        }
        repaired, audit = fixed_sample_crossout.apply_fixed_sample_operations(
            image,
            case,
        )
        self.assertTrue(np.all(repaired[1:6, 1:6] == 255))
        self.assertTrue(np.all(repaired[10:13, 10:13] == 255))
        self.assertTrue(np.all(repaired[15, 2:7] == 255))
        self.assertTrue(np.all(repaired[2:5, 14:17] == 0))
        self.assertEqual(audit['changed_pixel_count'], 32)
        self.assertEqual(audit['changed_outside_approved_regions'], 0)

    def test_prepare_attaches_model_path_only_for_exact_source_hash(self):
        with tempfile.TemporaryDirectory() as root:
            clean_path = os.path.join(root, 'math_sample_page15.png')
            image = np.full((12, 12, 3), 255, dtype=np.uint8)
            image[4:7, 4:7] = 0
            cv2.imencode('.png', image)[1].tofile(clean_path)
            source_hash = hashlib.sha256(Path(clean_path).read_bytes()).hexdigest()

            case = {
                'case_id': 'synthetic_page15',
                'subject': 'math',
                'page': 15,
                'source_sha256': source_hash,
                'image_size_wh': [12, 12],
                'operations': [
                    {'type': 'whiteout', 'bbox_xyxy': [4, 4, 7, 7]},
                ],
                'expected_changed_pixel_count': 9,
            }
            repaired, _audit = fixed_sample_crossout.apply_fixed_sample_operations(
                image,
                case,
            )
            encoded = cv2.imencode('.png', repaired)[1].tobytes()
            case['expected_output_sha256'] = hashlib.sha256(encoded).hexdigest()
            manifest = {'version': 'test_v1', 'cases': [case]}
            page = {'page': 15, 'clean_abs_path': clean_path}

            with mock.patch.object(
                fixed_sample_crossout,
                'load_fixed_sample_crossout_manifest',
                return_value=manifest,
            ):
                summary = fixed_sample_crossout.prepare_fixed_sample_crossout_images(
                    [page],
                    root,
                    'math',
                )

            self.assertEqual(summary['applied_page_count'], 1)
            self.assertTrue(os.path.isfile(page['model_abs_path']))
            self.assertEqual(
                hashlib.sha256(Path(clean_path).read_bytes()).hexdigest(),
                source_hash,
            )

            nonmatching = {'page': 15, 'clean_abs_path': clean_path}
            bad_manifest = {
                'version': 'test_v1',
                'cases': [{**case, 'source_sha256': '0' * 64}],
            }
            with mock.patch.object(
                fixed_sample_crossout,
                'load_fixed_sample_crossout_manifest',
                return_value=bad_manifest,
            ):
                summary = fixed_sample_crossout.prepare_fixed_sample_crossout_images(
                    [nonmatching],
                    root,
                    'math',
                )
            self.assertEqual(summary['applied_page_count'], 0)
            self.assertNotIn('model_abs_path', nonmatching)

    def test_layout_uses_clean_but_stage_b_uses_repaired_model_image(self):
        with tempfile.TemporaryDirectory() as root:
            clean_path = os.path.join(root, 'math_sample_page17.png')
            model_path = os.path.join(root, 'math_sample_page17.fixed_crossout.png')
            Path(clean_path).write_bytes(b'clean')
            Path(model_path).write_bytes(b'model')
            page = {
                'page': 17,
                'clean_abs_path': clean_path,
                'model_abs_path': model_path,
            }
            paths = {'pass1_json': root}
            with mock.patch.object(
                staged_pipeline,
                'detect_page_only',
            ) as detect_page:
                staged_pipeline._detect_page_job(
                    page,
                    paths,
                    'math',
                    grade=4,
                    stage=2,
                )
            self.assertEqual(detect_page.call_args.args[0], clean_path)

            with (
                mock.patch.object(
                    staged_pipeline,
                    'pass1_two_stage_enabled',
                    return_value=True,
                ),
                mock.patch.object(
                    staged_pipeline,
                    'grade_page_from_detect',
                ) as grade_page,
                mock.patch.object(
                    staged_pipeline,
                    'slot_presence_apply_approved',
                    return_value=False,
                ),
            ):
                staged_pipeline._grade_page_job(
                    page,
                    paths,
                    'math',
                    prior_context=None,
                    grade=4,
                    stage=2,
                )
            self.assertEqual(grade_page.call_args.args[0], model_path)

    def test_feature_is_limited_to_supported_subjects_and_can_be_disabled(self):
        self.assertTrue(fixed_sample_crossout.fixed_sample_crossout_enabled('math'))
        self.assertTrue(fixed_sample_crossout.fixed_sample_crossout_enabled('chinese'))
        self.assertFalse(fixed_sample_crossout.fixed_sample_crossout_enabled('english'))
        with mock.patch.dict(
            os.environ,
            {fixed_sample_crossout.FIXED_SAMPLE_CROSSOUT_ENV: '0'},
        ):
            self.assertFalse(
                fixed_sample_crossout.fixed_sample_crossout_enabled('math')
            )
            self.assertFalse(
                fixed_sample_crossout.fixed_sample_crossout_enabled('chinese')
            )
