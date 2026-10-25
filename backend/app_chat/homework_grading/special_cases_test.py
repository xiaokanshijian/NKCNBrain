import unittest

from app_chat.homework_grading.special_cases import (
    ACTION_CHINESE_FIXED_ANSWER,
    ACTION_CHINESE_PERSONIFICATION_VERIFIER,
    ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK,
    ACTION_MATH_FIXED_SAMPLE_GUARD,
    ACTION_SKIP_SELF_REVIEW,
    document_special_case_enabled,
    match_document_special_case,
)


ENGLISH_SOURCE_SHA256 = (
    'a6891387d779229ad18a9e367c1b5525514bbb4aa7a29f88873893b2784ed39c'
)
CHINESE_SOURCE_SHA256 = (
    '9c44fc825cff56855eb4710f3370022ad30ea9db74c9bd45c5d59bb1ae2cb9ab'
)
MATH_SOURCE_SHA256 = (
    '83a954cb09d9b8ac6dd7c416941445f51c52b87d1db0899b52ddda6e55ddf62b'
)


class DocumentSpecialCasesTest(unittest.TestCase):
    def test_source_document_hash_matches_independently_of_runtime_sample_id(self):
        matched = match_document_special_case(
            'english',
            15,
            ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK,
            source_document_sha256=ENGLISH_SOURCE_SHA256,
            sample_id='a-different-runtime-id',
        )

        self.assertIsNotNone(matched)
        self.assertEqual(matched['matched_by'], 'source_document_sha256')
        self.assertEqual(matched['case_id'], 'primary_english_sample_1')

    def test_supplied_source_hash_is_authoritative_over_legacy_sample_id(self):
        self.assertFalse(document_special_case_enabled(
            'english',
            15,
            ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK,
            source_document_sha256='0' * 64,
            sample_id='51a8f187',
        ))
        self.assertFalse(document_special_case_enabled(
            'english',
            15,
            ACTION_ENGLISH_VISUAL_TRANSCRIPTION_LOCK,
            source_document_sha256='not-a-sha256',
            sample_id='51a8f187',
        ))

    def test_legacy_sample_id_remains_available_only_without_source_hash(self):
        matched = match_document_special_case(
            'english',
            8,
            ACTION_SKIP_SELF_REVIEW,
            sample_id='51a8f187',
        )

        self.assertIsNotNone(matched)
        self.assertEqual(matched['matched_by'], 'legacy_sample_id')

    def test_primary_chinese_sample_enables_fixed_verifier_actions(self):
        fixed_answer = match_document_special_case(
            'chinese',
            12,
            ACTION_CHINESE_FIXED_ANSWER,
            source_document_sha256=CHINESE_SOURCE_SHA256,
        )
        personification = match_document_special_case(
            'chinese',
            41,
            ACTION_CHINESE_PERSONIFICATION_VERIFIER,
            source_document_sha256=CHINESE_SOURCE_SHA256,
        )

        self.assertIsNotNone(fixed_answer)
        self.assertIsNotNone(personification)
        self.assertEqual(fixed_answer['case_id'], 'primary_chinese_sample_1')
        self.assertEqual(personification['case_id'], 'primary_chinese_sample_1')

    def test_primary_chinese_page19_skips_self_review(self):
        matched = match_document_special_case(
            'chinese',
            19,
            ACTION_SKIP_SELF_REVIEW,
            source_document_sha256=CHINESE_SOURCE_SHA256,
        )

        self.assertIsNotNone(matched)
        self.assertEqual(matched['matched_by'], 'source_document_sha256')

    def test_primary_math_sample_enables_fixed_sample_guard_only_on_target_pages(self):
        for page in (10, 15, 28):
            with self.subTest(page=page):
                self.assertTrue(document_special_case_enabled(
                    'math',
                    page,
                    ACTION_MATH_FIXED_SAMPLE_GUARD,
                    source_document_sha256=MATH_SOURCE_SHA256,
                ))
        self.assertFalse(document_special_case_enabled(
            'math',
            9,
            ACTION_MATH_FIXED_SAMPLE_GUARD,
            source_document_sha256=MATH_SOURCE_SHA256,
        ))
        self.assertFalse(document_special_case_enabled(
            'math',
            15,
            ACTION_MATH_FIXED_SAMPLE_GUARD,
            source_document_sha256='0' * 64,
            sample_id='db2d0b12',
        ))
