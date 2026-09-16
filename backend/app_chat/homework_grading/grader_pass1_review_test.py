import json
import os
import tempfile
import unittest
from unittest import mock

from app_chat.homework_grading.grader_pass1_review import (
    _build_review_snapshot,
    _crop_question_image,
    _focused_fix_should_apply,
    _is_chinese_pinyin_write_question,
    _is_gemini_quota_error,
    _normalize_review_items,
    _run_review_candidates,
    _review_snapshot_signature,
    _needs_focused_chinese_visual_review,
    _page_has_chinese_visual_form_risk,
    _page_has_wrong_verdict,
    _page_needs_review,
    apply_review_to_page,
    focused_chinese_visual_review_enabled,
    pass1_review_parallelism,
    review_pass1_dir,
)


class Pass1ReviewApplyTest(unittest.TestCase):
    def test_apply_verdict_and_student_answer(self):
        page_data = {
            'page': 4,
            'questions': [
                {
                    'id': '4-2',
                    'student_answer': '36×365=13140',
                    'correct_answer': '13140',
                    'verdict': 'correct',
                }
            ],
        }
        review = {
            'items': [
                {
                    'id': '4-2',
                    'ok': False,
                    'reason': '漏转写答句',
                    'fix': {
                        'verdict': 'correct',
                        'student_answer': '36×365=13140(千克)\n答：会浪费13140千克水。',
                    },
                }
            ],
            'stats': {'total': 1, 'issues': 1, 'applied': 0},
        }
        applied = apply_review_to_page(page_data, review)
        question = page_data['questions'][0]
        self.assertEqual(applied, 1)
        self.assertIn('答：', question['student_answer'])
        self.assertFalse(question['self_review']['ok'])
        self.assertTrue(question['self_review']['applied'])

    def test_skip_ok_true(self):
        page_data = {
            'page': 1,
            'questions': [{'id': '1-1', 'verdict': 'wrong', 'student_answer': 'a'}],
        }
        review = {'items': [{'id': '1-1', 'ok': True}], 'stats': {}}
        applied = apply_review_to_page(page_data, review)
        self.assertEqual(applied, 0)
        self.assertNotIn('self_review', page_data['questions'][0])

    def test_page_needs_review_only_when_wrong(self):
        all_correct = {'questions': [{'id': '1-1', 'verdict': 'correct'}]}
        mixed = {'questions': [{'id': '1-1', 'verdict': 'correct'}, {'id': '1-2', 'verdict': 'wrong'}]}
        self.assertFalse(_page_has_wrong_verdict(all_correct))
        self.assertTrue(_page_has_wrong_verdict(mixed))

    def test_high_risk_scope_reviews_wrong_uncertain_and_pinyin_word_pages(self):
        with mock.patch.dict(os.environ, {'HOMEWORK_PASS1_REVIEW_SCOPE': 'high_risk'}):
            uncertain_page = {'questions': [{'id': '11', 'verdict': 'uncertain'}]}
            wrong_page = {'questions': [{'id': '11', 'verdict': 'wrong'}]}
            partial_page = {'questions': [{'id': '11', 'verdict': 'partial'}]}
            chinese_visual_page = {
                'questions': [{
                    'id': '一',
                    'verdict': 'correct',
                    'stem_excerpt': '读拼音，写词语。',
                    'knowledge_point': 'pinyin_words',
                }]
            }
            plain_correct_page = {'questions': [{'id': '1-1', 'verdict': 'correct'}]}

            self.assertTrue(_page_needs_review(uncertain_page, 'english'))
            self.assertTrue(_page_needs_review(wrong_page, 'english'))
            self.assertFalse(_page_needs_review(partial_page, 'english'))
            self.assertTrue(_page_needs_review(chinese_visual_page, 'chinese'))
            self.assertFalse(_page_needs_review(plain_correct_page, 'math'))

    def test_chinese_pinyin_context_write_words_page_needs_review(self):
        with mock.patch.dict(os.environ, {'HOMEWORK_PASS1_REVIEW_SCOPE': 'high_risk'}):
            page = {
                'questions': [{
                    'id': '1-2',
                    'verdict': 'correct',
                    'parent_stem_excerpt': '一、读拼音，结合语境写字词。',
                    'stem_excerpt': 'shū cài ... 功能，能够使',
                    'student_answer': '蔬菜',
                    'knowledge_point': 'character_writing',
                }]
            }
            self.assertTrue(_page_needs_review(page, 'chinese'))

    def test_chinese_pinyin_wrong_question_gets_review_focus_without_extra_page_risk(self):
        page = {
            'questions': [{
                'id': '1',
                'verdict': 'wrong',
                'stem_excerpt': '一、读拼音，写词语。',
                'student_answer': '黄蝶 蜻蜓 屋檐 耍赖 鸡笼',
                'error_type': '字形错误',
            }]
        }

        snapshot = _build_review_snapshot(page, 'chinese')
        self.assertIn('chinese_pinyin_words', snapshot['questions'][0]['review_focus'])
        self.assertFalse(_page_has_chinese_visual_form_risk(page, 'chinese'))

    def test_chinese_non_pinyin_correct_pages_do_not_trigger_visual_review(self):
        stems = [
            '这些树栖的恐龙由树栖到飞行的步骤是：',
            '根据课文内容填空。',
            '古诗默写。',
            '照样子写语句。',
            '填空。',
            '选字组词。',
        ]
        with mock.patch.dict(os.environ, {'HOMEWORK_PASS1_REVIEW_SCOPE': 'high_risk'}):
            for stem in stems:
                with self.subTest(stem=stem):
                    page = {'questions': [{'id': '1', 'verdict': 'correct', 'stem_excerpt': stem}]}
                    self.assertFalse(_page_needs_review(page, 'chinese'))

    def test_wrong_only_scope_keeps_legacy_candidate_rule(self):
        with mock.patch.dict(os.environ, {'HOMEWORK_PASS1_REVIEW_SCOPE': 'wrong_only'}):
            uncertain_page = {'questions': [{'id': '11', 'verdict': 'uncertain'}]}
            wrong_page = {'questions': [{'id': '11', 'verdict': 'wrong'}]}

            self.assertFalse(_page_needs_review(uncertain_page, 'english'))
            self.assertTrue(_page_needs_review(wrong_page, 'english'))

    def test_block_correct_to_uncertain(self):
        page_data = {
            'page': 2,
            'questions': [{'id': '2-1', 'verdict': 'correct', 'student_answer': '12'}],
        }
        review = {
            'items': [{
                'id': '2-1',
                'ok': False,
                'reason': '字迹略糊',
                'fix': {'verdict': 'uncertain'},
            }],
            'stats': {},
        }
        applied = apply_review_to_page(page_data, review)
        question = page_data['questions'][0]
        self.assertEqual(applied, 0)
        self.assertEqual(question['verdict'], 'correct')
        self.assertTrue(question['self_review']['verdict_fix_blocked'])

    def test_apply_correct_to_wrong_with_error_type(self):
        page_data = {
            'page': 3,
            'questions': [{'id': '3-1', 'verdict': 'correct', 'student_answer': '滑翔', 'error_type': ''}],
        }
        review = {
            'items': [{
                'id': '3-1',
                'ok': False,
                'reason': '翔字缺部件',
                'fix': {'verdict': 'wrong', 'error_type': '字形错误：翔字缺部件'},
            }],
            'stats': {},
        }
        applied = apply_review_to_page(page_data, review)
        question = page_data['questions'][0]
        self.assertEqual(applied, 1)
        self.assertEqual(question['verdict'], 'wrong')
        self.assertIn('字形错误', question['error_type'])

    def test_review_snapshot_marks_chinese_visual_and_english_communicative_focus(self):
        chinese = _build_review_snapshot({
            'questions': [{
                'id': '3-1',
                'verdict': 'correct',
                'stem_excerpt': '读拼音，写词语。',
                'student_answer': '滑翔',
            }]
        }, 'chinese')
        english = _build_review_snapshot({
            'questions': [{
                'id': '11',
                'verdict': 'wrong',
                'stem_excerpt': 'Read, ask and write. 完成表格。',
                'student_answer': "Qu's father, driver, staicion",
            }]
        }, 'english')

        self.assertIn('chinese_pinyin_words', chinese['questions'][0]['review_focus'])
        self.assertIn('english_communicative', english['questions'][0]['review_focus'])

    def test_detect_gemini_quota_error(self):
        self.assertTrue(_is_gemini_quota_error('用户额度不足, 剩余额度: $-0.1'))
        self.assertTrue(_is_gemini_quota_error({'code': 'insufficient_user_quota'}))
        self.assertFalse(_is_gemini_quota_error('temporary json parse error'))

    def test_normalize_review_items_keeps_visual_answer_audit_fields(self):
        items = _normalize_review_items([
            {
                'id': '1-1',
                'ok': False,
                'visual_answer': '疏菜',
                'expected_answer': '蔬菜',
                'fix': {
                    'verdict': 'wrong',
                    'student_answer': '疏菜',
                    'error_type': '字形错误：应为蔬菜',
                },
            }
        ], ['1-1'])

        self.assertEqual(items[0]['visual_answer'], '疏菜')
        self.assertEqual(items[0]['expected_answer'], '蔬菜')
        self.assertEqual(items[0]['fix']['student_answer'], '疏菜')

    def test_review_parallelism_defaults_to_small_cap_and_env_override(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(pass1_review_parallelism(candidate_count=30), 5)
            self.assertEqual(pass1_review_parallelism(workers=5, candidate_count=30), 5)
            self.assertEqual(pass1_review_parallelism(workers=2, candidate_count=30), 2)
            self.assertEqual(pass1_review_parallelism(workers=5, candidate_count=2), 2)
        with mock.patch.dict(os.environ, {'HOMEWORK_PASS1_REVIEW_PARALLELISM': '6'}):
            self.assertEqual(pass1_review_parallelism(workers=2, candidate_count=30), 6)
        with mock.patch.dict(os.environ, {'HOMEWORK_PASS1_REVIEW_PARALLELISM': '99'}):
            self.assertEqual(pass1_review_parallelism(workers=2, candidate_count=30), 8)

    def test_review_pass1_dir_reuses_signature_matched_review_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            page_data = {'page': 1, 'questions': [{'id': '1', 'verdict': 'wrong'}]}
            json_path = os.path.join(tmp, 'math_sample_page1.json')
            with open(json_path, 'w', encoding='utf-8') as file:
                json.dump(page_data, file)
            review_path = os.path.join(tmp, 'math_sample_page1.review.json')
            with open(review_path, 'w', encoding='utf-8') as file:
                json.dump({
                    'page': 1,
                    'post_review_signature': _review_snapshot_signature(page_data, 'math'),
                    'stats': {'issues': 1, 'applied': 1},
                    'items': [],
                }, file)

            with mock.patch.dict(os.environ, {
                'HOMEWORK_PASS1_SELF_REVIEW': '1',
                'HOMEWORK_PASS1_REVIEW_REUSE_EXISTING': '1',
            }):
                with mock.patch(
                    'app_chat.homework_grading.grader_pass1_review._run_review_candidates',
                    return_value=[],
                ) as runner:
                    stats = review_pass1_dir(tmp, [{'page': 1, 'clean_abs_path': 'missing.png'}], 'math', workers=5)

            runner.assert_not_called()
            self.assertEqual(stats['pages_reused'], 1)
            self.assertEqual(stats['pages_reviewed'], 1)
            self.assertEqual(stats['issues_found'], 1)
            self.assertEqual(stats['corrections_applied'], 1)

    def test_review_pass1_dir_uses_parallel_scheduler_even_when_stop_on_quota(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages = []
            for page in (1, 2, 3):
                json_path = os.path.join(tmp, f'math_sample_page{page}.json')
                image_path = os.path.join(tmp, f'math_sample_page{page}.png')
                with open(json_path, 'w', encoding='utf-8') as file:
                    json.dump({'page': page, 'questions': [{'id': str(page), 'verdict': 'wrong'}]}, file)
                with open(image_path, 'wb') as file:
                    file.write(b'png')
                pages.append({'page': page, 'clean_abs_path': image_path})

            with mock.patch.dict(os.environ, {
                'HOMEWORK_PASS1_SELF_REVIEW': '1',
                'HOMEWORK_PASS1_REVIEW_SCOPE': 'high_risk',
                'HOMEWORK_PASS1_REVIEW_STOP_ON_QUOTA': '1',
                'HOMEWORK_PASS1_REVIEW_PARALLELISM': '3',
            }):
                with mock.patch(
                    'app_chat.homework_grading.grader_pass1_review._run_review_candidates',
                    return_value=[
                        {'page': 1, 'skipped': False, 'issues': 0, 'applied': 0},
                        {'page': 2, 'skipped': False, 'issues': 0, 'applied': 0},
                        {'page': 3, 'skipped': False, 'issues': 0, 'applied': 0},
                    ],
                ) as runner:
                    stats = review_pass1_dir(tmp, pages, 'math', workers=5)

            self.assertEqual(stats['workers'], 3)
            self.assertEqual(stats['pages_reviewed'], 3)
            self.assertTrue(runner.call_args.args[5])
            self.assertEqual(runner.call_args.args[4], 3)

    def test_serial_quota_stop_marks_remaining_candidates_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            candidates = []
            for page in (1, 2, 3):
                json_path = os.path.join(tmp, f'math_sample_page{page}.json')
                with open(json_path, 'w', encoding='utf-8') as file:
                    json.dump({'page': page, 'questions': [{'id': str(page), 'verdict': 'wrong'}]}, file)
                candidates.append((json_path, os.path.join(tmp, f'math_sample_page{page}.png')))

            with mock.patch(
                'app_chat.homework_grading.grader_pass1_review._run_review_candidate',
                return_value={
                    'page': 1,
                    'skipped': False,
                    'error': '用户额度不足',
                    'quota_limited': True,
                    'issues': 0,
                    'applied': 0,
                },
            ):
                results = _run_review_candidates(candidates, 'math', 4, 2, 1, True)

            self.assertEqual(len(results), 3)
            self.assertTrue(results[0]['quota_limited'])
            self.assertEqual(results[1]['skip_reason'], 'gemini_quota_limited')
            self.assertEqual(results[2]['skip_reason'], 'gemini_quota_limited')

    def test_focused_chinese_visual_review_enabled_by_default_but_can_be_disabled(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertTrue(focused_chinese_visual_review_enabled())
        with mock.patch.dict(os.environ, {'HOMEWORK_PASS1_FOCUSED_CHINESE_VISUAL_REVIEW': '0'}):
            self.assertFalse(focused_chinese_visual_review_enabled())

    def test_focused_chinese_visual_review_requires_position_and_pinyin_write_type(self):
        question = {
            'id': '一-4',
            'verdict': 'correct',
            'stem_excerpt': 'shuǎ lài',
            'parent_stem_excerpt': '读拼音，写词语。',
            'student_answer': '耍赖',
            'position': [590, 248, 703, 290],
        }
        self.assertTrue(_needs_focused_chinese_visual_review(question))
        self.assertFalse(_needs_focused_chinese_visual_review({**question, 'position': []}))
        self.assertTrue(_needs_focused_chinese_visual_review({**question, 'verdict': 'partial'}))
        self.assertTrue(_needs_focused_chinese_visual_review({**question, 'verdict': 'wrong'}))

    def test_crop_question_image_enlarges_focused_review_region(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest('Pillow unavailable')

        with tempfile.TemporaryDirectory() as tmp:
            image_path = os.path.join(tmp, 'page.png')
            Image.new('RGB', (1000, 1000), 'white').save(image_path)
            question = {'position': [400, 400, 500, 500]}

            with mock.patch.dict(os.environ, {
                'HOMEWORK_PASS1_FOCUSED_REVIEW_MARGIN_PX': '20',
                'HOMEWORK_PASS1_FOCUSED_REVIEW_SCALE': '3',
            }):
                crop_path, cleanup_path = _crop_question_image(image_path, question)

            self.assertTrue(cleanup_path)
            try:
                crop = Image.open(crop_path)
                self.assertEqual(crop.size, (420, 420))
                crop.close()
            finally:
                if cleanup_path and os.path.exists(cleanup_path):
                    os.remove(cleanup_path)

    def test_crop_question_image_expands_all_sides_for_pinyin_write(self):
        try:
            from PIL import Image
        except Exception:
            self.skipTest('Pillow unavailable')

        with tempfile.TemporaryDirectory() as tmp:
            image_path = os.path.join(tmp, 'page.png')
            Image.new('RGB', (1000, 1000), 'white').save(image_path)
            plain = {'position': [400, 400, 500, 500]}
            pinyin = {
                'position': [400, 400, 500, 500],
                'parent_stem_excerpt': '二、读拼音，结合语境写字词。',
            }

            with mock.patch.dict(os.environ, {
                'HOMEWORK_PASS1_FOCUSED_REVIEW_MARGIN_PX': '20',
                'HOMEWORK_PASS1_FOCUSED_REVIEW_EXTRA_PAD_RATIO': '0.5',
                'HOMEWORK_PASS1_FOCUSED_REVIEW_SCALE': '1',
            }):
                plain_path, plain_cleanup = _crop_question_image(image_path, plain)
                pinyin_path, pinyin_cleanup = _crop_question_image(image_path, pinyin)

            self.assertTrue(_is_chinese_pinyin_write_question(pinyin))
            try:
                plain_crop = Image.open(plain_path)
                pinyin_crop = Image.open(pinyin_path)
                self.assertEqual(plain_crop.size, (140, 140))
                self.assertEqual(pinyin_crop.size, (240, 240))
                plain_crop.close()
                pinyin_crop.close()
            finally:
                for cleanup_path in (plain_cleanup, pinyin_cleanup):
                    if cleanup_path and os.path.exists(cleanup_path):
                        os.remove(cleanup_path)

    def test_focused_fix_blocked_when_visual_matches_expected(self):
        question = {'correct_answer': '霸气', 'verdict': 'correct'}
        item = {
            'ok': False,
            'visual_answer': '霸气',
            'expected_answer': '霸气',
            'fix': {'verdict': 'wrong', 'student_answer': '霸气', 'error_type': '字形错误'},
        }
        self.assertFalse(_focused_fix_should_apply(item, question))


if __name__ == '__main__':
    unittest.main()
