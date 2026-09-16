import unittest

from app_chat.keyword_utils import (
    CARD_KEYWORDS_HARD_CAP,
    CARD_KEYWORDS_HARD_CAP_LONG,
    CARD_KEYWORDS_HARD_CAP_MID,
    CARD_KEYWORDS_PREFERRED_LONG,
    CARD_KEYWORDS_PREFERRED_MID,
    CARD_KEYWORDS_SOFT_CAP,
    SEMANTIC_KEYWORDS_FINAL_MARKER,
    build_keyword_extraction_instruction,
    keyword_count_bounds_for_content,
    normalize_semantic_keywords,
    parse_final_semantic_keywords,
    parse_llm_color_dmt_response,
    trim_keyword_length,
)


class KeywordUtilsTest(unittest.TestCase):
    def test_trim_no_longer_hard_cuts(self):
        self.assertEqual(trim_keyword_length('一百零八塔设计'), '一百零八塔设计')
        self.assertEqual(trim_keyword_length('「数列思想」'), '数列思想')

    def test_normalize_keywords(self):
        self.assertEqual(normalize_semantic_keywords('塔设计，数列思想'), '塔设计，数列思想')

    def test_normalize_does_not_hard_truncate_length(self):
        long_kw = '单元学习任务单总体框架'
        self.assertEqual(normalize_semantic_keywords(long_kw), long_kw)

    def test_normalize_max_count(self):
        self.assertEqual(
            normalize_semantic_keywords('甲，乙，丙，丁', max_count=3),
            '甲，乙，丙',
        )

    def test_keyword_count_bounds_by_length(self):
        self.assertEqual(keyword_count_bounds_for_content('短' * 100), (2, 4, CARD_KEYWORDS_HARD_CAP))
        self.assertEqual(keyword_count_bounds_for_content('中' * 1499), (2, 4, CARD_KEYWORDS_HARD_CAP))
        self.assertEqual(
            keyword_count_bounds_for_content('长' * 1500),
            (4, CARD_KEYWORDS_SOFT_CAP, CARD_KEYWORDS_HARD_CAP),
        )
        self.assertEqual(
            keyword_count_bounds_for_content('长' * 3000),
            (4, CARD_KEYWORDS_SOFT_CAP, CARD_KEYWORDS_HARD_CAP),
        )
        self.assertEqual(
            keyword_count_bounds_for_content('长' * 3001),
            (5, CARD_KEYWORDS_PREFERRED_MID, CARD_KEYWORDS_HARD_CAP_MID),
        )
        self.assertEqual(
            keyword_count_bounds_for_content('长' * 4000),
            (5, CARD_KEYWORDS_PREFERRED_MID, CARD_KEYWORDS_HARD_CAP_MID),
        )
        self.assertEqual(
            keyword_count_bounds_for_content('长' * 4001),
            (6, CARD_KEYWORDS_PREFERRED_LONG, CARD_KEYWORDS_HARD_CAP_LONG),
        )
        self.assertEqual(CARD_KEYWORDS_HARD_CAP, 10)
        self.assertEqual(CARD_KEYWORDS_HARD_CAP_MID, 15)
        self.assertEqual(CARD_KEYWORDS_HARD_CAP_LONG, 20)

    def test_extraction_instruction_is_semantic(self):
        text = build_keyword_extraction_instruction(3, min_keywords=2)
        self.assertIn('语义关键词', text)
        self.assertIn('不会事后硬截断', text)
        self.assertIn('认知协同', text)
        self.assertIn('具体实在的知识内容', text)
        self.assertIn('名词体系', text)
        self.assertIn('原子化', text)
        self.assertIn(SEMANTIC_KEYWORDS_FINAL_MARKER, text)
        self.assertIn('以「合适」为准', text)
        self.assertIn('硬上限 10', text)
        self.assertIn('一眼可读', text)
        self.assertIn('D/M/T', text)
        self.assertIn('语义段', text)
        self.assertIn('研究', text)
        self.assertIn('无区分度泛词', text)
        self.assertIn('C1', text)
        self.assertIn('先审「理解」', text)
        self.assertIn('增、删、改', text)
        self.assertIn('简单而深刻', text)
        self.assertIn('强制对齐示范', text)
        self.assertIn('样例1·应输出', text)
        self.assertIn('DRG，医学本体论，医患共生，价值付费', text)
        self.assertIn('自适应机制', text)
        self.assertIn('三类知识', text)
        self.assertIn('传统知识', text)
        self.assertIn('邻接矩阵', text)
        self.assertIn('样例4·应输出', text)
        self.assertIn('样例5·应输出', text)
        self.assertIn('体联除乘加', text)
        self.assertIn('精准PSI', text)
        self.assertIn('样例6·应输出', text)
        self.assertIn('鱼嘴一筛', text)
        self.assertIn('熵增区', text)
        self.assertIn('分离机制', text)
        self.assertIn('错误抽法（禁止再犯）', text)
        self.assertIn('慎取文末归纳口号', text)
        self.assertIn('组织协同', text)

    def test_parse_final_marker(self):
        raw = (
            '理解：……\n第一版：甲，乙\n审核：乙有歧义改为丙\n'
            f'{SEMANTIC_KEYWORDS_FINAL_MARKER}\n共享单车，看门狗回滚，DMT微版面\n'
        )
        self.assertEqual(
            parse_final_semantic_keywords(raw),
            '共享单车，看门狗回滚，DMT微版面',
        )

    def test_parse_color_dmt_with_noise(self):
        self.assertEqual(parse_llm_color_dmt_response('判定为 RD'), ('R', 'D'))
        self.assertEqual(parse_llm_color_dmt_response('R,D'), ('R', 'D'))


if __name__ == '__main__':
    unittest.main()
