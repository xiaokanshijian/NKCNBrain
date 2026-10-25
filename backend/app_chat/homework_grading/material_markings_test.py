"""颜色事实贯通和可编辑三区的离线回归；不调用真实模型。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from . import grader_pass1, grader_pass1_review, grader_pass2, ontology_builder, prompts, service
from .feedback_prompts import diagnostic_system, system_prompt
from .feedback_runtime import stamp_feedback
from .feedback_skills_test import runtime_fixture
from .managed_feedback_rules_test import _runtime, _copy_document
from .managed_feedback_rules import save_rule, delete_rule
from .material_markings import normalize_markings, observation_eligible, open_units
from .memory import build_memory
from .note_evidence import validate_note_ontology, validate_note_feedback
from .utils import safe_json_dump


def marked_unit():
    return {'id': 'auto-1', 'page': 1, 'qid_global': 'p1:auto-1', 'position': [10, 10, 200, 120],
            'stem_excerpt': '概念与条件', 'student_answer': '注意条件', 'note_role': 'annotation',
            'verdict': 'correct', 'understanding': '原文条件被标记，旁批可能在强调适用范围。',
            'printed_text_marked': '概念与<黄色荧光笔涂画>条件</黄色荧光笔涂画>',
            'handwritten_text_marked': '<红色笔>注意</红色笔><蓝色笔>条件</蓝色笔>',
            'annotation_links': [{'marked_text': '条件', 'annotation_text': '注意条件', 'relation': '旁批对应原文条件'}]}


def observation_ontology():
    return {'zones': {'blind_spot': [], 'friction_zone': [], 'zpd': [{
        'knowledge_point': '整理方法', 'evidence': ['p1:auto-1'], 'evidence_basis': 'annotation',
        'error_clusters': [], 'rationale': '已用颜色标出条件，可结合原文说明其作用。',
        'suggested_next_step': '尝试用自己的话解释标记处。'}]}, 'mastery_trajectory': []}


class MaterialMarkingsTest(unittest.TestCase):
    def test_multicolor_preserves_plain_transcription_and_unknown_color(self):
        q = marked_unit(); normalize_markings(q)
        self.assertEqual(q['student_answer'], '注意条件')
        self.assertIn('<蓝色笔>', q['handwritten_text_marked'])
        q['handwritten_text_marked'] = '<颜色不明笔>注意条件</颜色不明笔>'
        normalize_markings(q)
        self.assertTrue(observation_eligible(q))
        self.assertNotIn('marking_warnings', q)

    def test_bad_tags_or_text_mismatch_discard_only_marked_copy(self):
        for value in ('<红色笔>别的内容</红色笔>', '<红色笔>注意条件</蓝色笔>', '<script>注意条件</script>'):
            q = marked_unit(); q['handwritten_text_marked'] = value
            normalize_markings(q)
            self.assertEqual(q['student_answer'], '注意条件')
            self.assertNotIn('handwritten_text_marked', q)
            self.assertTrue(q['marking_warnings'])
        q = {'student_answer': '普通黑笔文字'}
        self.assertEqual(normalize_markings(copy.deepcopy(q)), q)

    def test_highlight_without_handwriting_survives_and_supports_observation_only(self):
        for kind in ('笔记', '作文'):
            runtime = runtime_fixture(f'初中·初一·语文·{kind}.pdf')
            q = marked_unit(); q.update(student_answer='', note_role='source_excerpt', verdict='unanswered')
            q.pop('handwritten_text_marked'); q['annotation_links'][0]['annotation_text'] = ''
            detected = grader_pass1._normalize_detect_result({'questions': [q]}, 'chinese', 1)
            merged = grader_pass1._merge_detect_and_grade(detected, {'questions': [q]}, 'chinese', 1, feedback_runtime=runtime)
            units = open_units({'error_questions': [dict(merged['questions'][0], qid_global='p1:auto-1')]}, runtime.context['material_type'])
            self.assertFalse(units[0]['diagnostic_eligible'])
            self.assertTrue(units[0]['observation_eligible'])
            validate_note_ontology(observation_ontology(), units)
            bad = observation_ontology(); bad['zones']['zpd'][0]['evidence_basis'] = 'content'
            with self.assertRaises(ValueError): validate_note_ontology(bad, units)
            bad = observation_ontology(); bad['zones']['zpd'][0]['rationale'] = '学生未掌握条件'
            with self.assertRaises(ValueError): validate_note_ontology(bad, units)
            bad = observation_ontology(); bad['zones']['zpd'][0]['rationale'] = '学生已经掌握条件'
            with self.assertRaises(ValueError): validate_note_ontology(bad, units)

    def test_detection_keeps_only_marked_auto_unit(self):
        q = {'id': 'auto-1', 'printed_text_marked': '<红色圈画>条件</红色圈画>'}
        result = grader_pass1._normalize_detect_result({'questions': [q]}, 'chinese', 1)
        self.assertEqual(len(result['questions']), 1)
        self.assertIn('printed_text_marked', result['questions'][0])

    def test_review_changed_text_invalidates_old_colors_and_annotation(self):
        for kind in ('笔记', '作文'):
            q = marked_unit()
            runtime = runtime_fixture(f'初中·初一·语文·{kind}.pdf')
            grader_pass1_review.apply_review_to_page({'page': 1, 'questions': [q]}, {'items': [{
                'id': q['id'], 'ok': False, 'reason': '核对可见字形', 'fix': {'student_answer': '核对范围'}}]}, feedback_runtime=runtime)
            self.assertEqual(q['student_answer'], '核对范围')
            self.assertNotIn('handwritten_text_marked', q)
            self.assertEqual(q['annotation_links'], [])
            self.assertTrue(q['marking_warnings'])

    def test_review_can_replace_marked_text_with_consistent_new_copy(self):
        q = marked_unit(); runtime = runtime_fixture('初中·初一·语文·作文.pdf')
        items = grader_pass1_review._normalize_review_items([{'id': q['id'], 'ok': False, 'fix': {
            'student_answer': '核对范围', 'handwritten_text_marked': '<蓝色笔>核对范围</蓝色笔>',
            'annotation_links': [], 'understanding': '可见蓝笔补充了范围。'}}], [q['id']])
        grader_pass1_review.apply_review_to_page({'page': 1, 'questions': [q]}, {'items': items}, feedback_runtime=runtime)
        self.assertIn('核对范围', q['handwritten_text_marked'])
        self.assertEqual(q['understanding'], '可见蓝笔补充了范围。')

    def test_real_merge_memory_ontology_feedback_and_result_keep_markings(self):
        for kind in ('笔记', '作文'):
            runtime = _runtime(f'初中·初一·语文·{kind}.pdf')
            q = marked_unit()
            merged = grader_pass1._merge_detect_and_grade({'questions': [q]}, {'questions': [q]}, 'chinese', 1, feedback_runtime=runtime)
            with tempfile.TemporaryDirectory() as tmp:
                file = Path(tmp) / 'sample_page1.json'; safe_json_dump(file, stamp_feedback(merged, runtime))
                memory = build_memory(tmp, 'chinese', 'synthetic', feedback_runtime=runtime)
                pack = ontology_builder.assemble_evidence_pack('chinese', 'synthetic', {}, [memory], {}, feedback_runtime=runtime)
                self.assertIn('黄色荧光笔涂画', json.dumps(pack, ensure_ascii=False))
                self.assertEqual(ontology_builder._valid_qids_from_pack(pack), {'p1:auto-1'})
                ontology = ontology_builder._runtime_ontology(observation_ontology(), pack, runtime)
                prompt = prompts.pass2_feedback_user(memory, ontology, feedback_runtime=runtime)
                self.assertIn('handwritten_text_marked', prompt)
                self.assertIn('annotation', prompt)
                result = service._load_pass1_questions(str(file), 1)[0]
                self.assertEqual(result['printed_text_marked'], q['printed_text_marked'])
                self.assertEqual(result['handwritten_text_marked'], q['handwritten_text_marked'])
                generated = {'per_question_feedback': [{'page': 1, 'id': q['id'], 'qid_global': q['qid_global'],
                    'zone': 'zpd', 'comment': '已标出条件，可试着解释其作用。'}],
                    'open_material_overview': {'subject_and_layout': '可见多色标注。', 'content_review': '旁批对应原文条件。',
                                               'next_steps': ['解释标记处的作用。']}}
                with patch.object(grader_pass2, '_call_pass2_feedback_llm', return_value=generated):
                    report = grader_pass2.analyze_pass2(memory, 'chinese', 'synthetic', str(Path(tmp)/'report.json'),
                        str(Path(tmp)/'thinking.txt'), ontology=ontology, feedback_runtime=runtime)
                self.assertEqual(report['zone_classification']['zpd'][0]['evidence_basis'], 'annotation')
                validate_note_feedback(report, memory, ontology, material_type=runtime.context['material_type'])
                report['per_question_feedback'][0]['comment'] = '从高亮可知学生已经掌握条件'
                with self.assertRaises(ValueError):
                    validate_note_feedback(report, memory, ontology, material_type=runtime.context['material_type'])

    def test_editable_definition_reaches_both_prompts_and_old_snapshot_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rules.json'; _copy_document(path)
            with patch('app_chat.homework_grading.managed_feedback_rules.RULES_PATH', path):
                for kind in ('笔记', '作文'):
                    old = _runtime(f'初中·初一·语文·{kind}.pdf')
                    save_rule({'id': 'open-material-zone-definitions', 'body': '合成新定义：重点反馈标注组织方法。'}, path)
                    new = _runtime(f'初中·初一·语文·{kind}.pdf')
                    for phase in ('ontology', 'pass2', 'pass2_full'):
                        self.assertIn('合成新定义', diagnostic_system(new, phase))
                        self.assertNotIn('出错率>40%', diagnostic_system(new, phase))
                    # 冻结对象读取不依赖当前磁盘规则。
                    before = diagnostic_system(old, 'ontology')
                    save_rule({'id': 'open-material-zone-definitions', 'body': '另一合成定义'}, path)
                    self.assertEqual(before, diagnostic_system(old, 'ontology'))
                delete_rule('open-material-zone-definitions', path)
                deleted = _runtime('初中·初一·语文·作文.pdf')
                self.assertNotIn('另一合成定义', diagnostic_system(deleted, 'ontology'))

    def test_explicit_content_basis_uses_editable_meaning_but_uncertain_content_stays_blocked(self):
        q = marked_unit(); units = open_units({'error_questions': [q]}, 'notes')
        ontology = observation_ontology(); entry = ontology['zones']['zpd'].pop()
        entry.update(evidence_basis='content', rationale='组织方式仍可调整。')
        ontology['zones']['friction_zone'] = [entry]
        validate_note_ontology(ontology, units)
        q['verdict'] = 'uncertain'
        with self.assertRaises(ValueError): validate_note_ontology(ontology, open_units({'error_questions': [q]}, 'notes'))

    def test_plain_essay_and_question_material_prompts_and_legacy_reading(self):
        essay = _runtime('初中·初一·语文·作文.pdf')
        self.assertIn('handwritten_text_marked', system_prompt(essay, 'grade'))
        self.assertIn('printed_text_marked', system_prompt(essay, 'detect'))
        for kind in ('作业', '试卷'):
            runtime = _runtime(f'初中·初一·语文·{kind}.pdf')
            self.assertNotIn('printed_text_marked', system_prompt(runtime, 'detect'))
            self.assertNotIn('学·教·育视角', diagnostic_system(runtime, 'ontology'))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'sample_page1.json'; safe_json_dump(path, {'page': 1, 'questions': [{
                'id': '1', 'student_answer': '普通作文', 'verdict': 'correct', 'position': [1, 1, 200, 200]}]})
            before = path.read_bytes(); result = service._load_pass1_questions(str(path), 1)[0]
            self.assertEqual(result['student_answer'], '普通作文')
            self.assertNotIn('handwritten_text_marked', result)
            self.assertEqual(before, path.read_bytes())


if __name__ == '__main__':
    unittest.main()
