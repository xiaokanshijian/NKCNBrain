"""模型坐标格式兼容；仅使用合成题目，不调用模型。"""
import copy
import unittest

from .grader_pass1 import _merge_detect_and_grade, _normalize_detect_result, _normalize_pass1_result
from .render import _iter_question_boxes
from .utils import normalize_position


class PositionFormatTests(unittest.TestCase):
    def setUp(self):
        self.position = {'x_min': 28, 'y_min': 175, 'x_max': 520, 'y_max': 390}
        self.page = {'questions': [{'id': '9-1', 'position': self.position, 'stem_excerpt': '合成题'}]}

    def test_object_and_array_coordinates_are_equivalent(self):
        expected = [28, 175, 520, 390]
        self.assertEqual(normalize_position(self.position), expected)
        self.assertEqual(normalize_position(expected), expected)
        for normalizer in (_normalize_detect_result, _normalize_pass1_result):
            result = normalizer(copy.deepcopy(self.page), 'math', 5)
            self.assertEqual(result['questions'][0]['position'], expected)

    def test_cached_detect_merge_and_grade_only_question(self):
        result = _merge_detect_and_grade(copy.deepcopy(self.page), {'questions': []}, 'math', 5)
        self.assertEqual(result['questions'][0]['position'], [28, 175, 520, 390])
        result = _merge_detect_and_grade({'questions': []}, copy.deepcopy(self.page), 'math', 5)
        self.assertEqual(result['questions'][0]['position'], [28, 175, 520, 390])

    def test_legacy_object_renders_without_losing_question(self):
        boxes = list(_iter_question_boxes(self.page, 1000, 1000))
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0][1:], (28, 175, 520, 390))
        self.assertEqual(self.page['questions'][0]['position'], self.position)

    def test_unknown_or_incomplete_object_does_not_invent_coordinates(self):
        for value in ({'x': 1, 'y': 2, 'w': 3, 'h': 4}, {'x_min': 1},
                      {'x_min': 'bad', 'y_min': 1, 'x_max': 4, 'y_max': 5}):
            self.assertEqual(normalize_position(value), [])
