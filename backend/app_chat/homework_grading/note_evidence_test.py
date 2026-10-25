"""笔记真实验收问题的合成回归；不读取业务结果或调用真实模型。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from . import cross_page, grader_pass1, grader_pass1_review, grader_pass2, ontology_builder, prompts
from .feedback_runtime import freeze_feedback_runtime, stamp_feedback
from .feedback_skills_test import runtime_fixture
from .memory import build_memory
from .note_evidence import note_units, validate_note_ontology, validate_note_feedback, validate_note_temporal_text
from .note_page_links import backfill_note_detect_dir, candidate_note_page_pairs
from .sessions import build_pre_pass1_session_map, build_all_session_memories
from .utils import safe_json_dump, safe_json_load


def unit(qid, verdict='correct', role='note', text='可见笔记文字'):
    page, local = qid.split(':')
    return {'id': local, 'page': int(page[1:]), 'qid_global': qid, 'note_role': role,
            'student_answer': text, 'understanding': '依据原页观察', 'knowledge_point': '数轴',
            'verdict': verdict, 'error_type': '前提条件错误' if verdict == 'wrong' else ''}


def zone(refs, **extra):
    return {'knowledge_point': '数轴', 'evidence': refs, 'error_clusters': [],
            'trend': None, 'stability': None, 'first_session': None, 'last_session': None,
            'rationale': '依据可见书写内容核对。', **extra}


def note_ontology(refs):
    return {'zones': {'blind_spot': [zone(refs)] if refs else [], 'friction_zone': [], 'zpd': []},
            'mastery_trajectory': [], 'evolution_narrative': '本份笔记有可定位的内容观察。'}


def page(number, printed, *, kind='workbook', title='同一册练习册', before=False, after=False):
    return {'page': number, 'page_origin': {'source_kind': kind, 'source_title': title,
            'printed_page_number': printed}, 'boundary': {'continues_from_prev': before,
            'continues_to_next': after}, 'questions': [dict(unit(f'p{number}:1'), cross_page=True)]}


class NoteEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.runtime = runtime_fixture('初中·初一·数学·笔记.pdf')

    def test_uncertain_and_prompts_never_enter_error_statistics(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = {'page': 1, 'questions': [unit('p1:1', 'uncertain'),
                    unit('p1:2', 'unanswered', 'reading_prompt', ''),
                    unit('p1:3', 'wrong'), unit('p1:4')]}
            safe_json_dump(Path(tmp) / 'sample_page1.json', stamp_feedback(data, self.runtime))
            memory = build_memory(tmp, 'math', 'sample', feedback_runtime=self.runtime)
        self.assertIsNone(memory['accuracy']['overall'])
        self.assertEqual(memory['accuracy']['by_page'], {})
        self.assertEqual(memory['knowledge_point_frequency'][0]['total_count'], 2)
        self.assertEqual(memory['knowledge_point_frequency'][0]['error_count'], 1)
        self.assertEqual(len(memory['error_questions']), 4)
        self.assertEqual([q['assessment_status'] for q in memory['error_questions']],
                         ['unconfirmed', 'not_assessed', 'observed', 'observed'])
        pack = ontology_builder.assemble_evidence_pack('math', 'sample', {}, [memory],
                {'stable_blind_spots': ['旧正确率盲区']}, feedback_runtime=self.runtime)
        self.assertNotIn('accuracy', pack['session_timeline'][0])
        self.assertEqual(pack['rule_baseline_profile']['stable_blind_spots'], [])
        self.assertEqual(ontology_builder._valid_qids_from_pack(pack), {'p1:3', 'p1:4'})

    def test_one_document_observation_and_no_time_trajectory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clean = root / 'clean'; clean.mkdir()
            out = root / 'report'; out.mkdir()
            pages = root / 'pass1'; pages.mkdir()
            for number in range(1, 5):
                (clean / f'sample_page{number}.png').write_bytes(b'synthetic')
                safe_json_dump(pages / f'sample_page{number}.json', stamp_feedback(
                    {'page': number, 'questions': [unit(f'p{number}:1')]}, self.runtime))
            with patch('app_chat.homework_grading.sessions._resolve_sessions', side_effect=AssertionError('no LLM split')):
                path = build_pre_pass1_session_map('math', 'sample', str(root / 'sample.pdf'),
                        str(clean), str(out), feedback_runtime=self.runtime)
            doc = safe_json_load(path)
            memories = build_all_session_memories(str(pages), str(out), 'math', 'sample',
                        sessions_json_path=path, feedback_runtime=self.runtime)
        self.assertEqual(doc['session_count'], 1)
        self.assertEqual(doc['sessions'][0]['page_end'], 4)
        self.assertNotIn('chronological', doc['temporal_assumption'])
        self.assertEqual(memories[0]['kp_trend'], {})
        self.assertEqual(memories[0]['erase_candidates'], [])

    def test_ontology_rejects_unconfirmed_correct_and_teaching_prompt_as_errors(self):
        units = note_units({'error_questions': [unit('p1:1', 'uncertain'), unit('p1:2'),
                           unit('p1:3', 'wrong', 'teaching_prompt'), unit('p1:4', 'wrong')]})
        for ref in ('p1:1', 'p1:2', 'p1:3', 'p99:1'):
            with self.assertRaises(ValueError):
                validate_note_ontology(note_ontology([ref]), units)
        validate_note_ontology(note_ontology(['p1:4']), units)
        for mutation in ({'trend': 'improving'}, {'stability': 'persistent'}, {'first_session': 1}):
            invalid = note_ontology(['p1:4']); invalid['zones']['blind_spot'][0].update(mutation)
            with self.assertRaises(ValueError):
                validate_note_ontology(invalid, units)

    def test_feedback_rejects_invented_zone_and_review_boilerplate(self):
        memory = {'error_questions': [unit('p1:1')]}
        for change in ({'zone': 'blind_spot'}, {'comment': '正确，但未列入三区，建议人工复核。'},
                       {'comment': '相比前页进步明显。'}):
            item = {'qid_global': 'p1:1', 'zone': '', 'comment': '数轴三要素已记录。', **change}
            with self.assertRaises(ValueError):
                validate_note_feedback({'per_question_feedback': [item]}, memory, note_ontology([]))
        validate_note_feedback({'per_question_feedback': [{'qid_global': 'p1:1', 'zone': '',
            'comment': '数轴三要素已记录。'}]}, memory, note_ontology([]))

    def test_protective_negation_is_not_an_assertion_of_inability(self):
        memory = {'error_questions': [unit('p6:1', 'unanswered', 'reading_prompt', '')]}
        for comment in (
            '读地图活动题下方未见手写作答；这是未观察到作答，不能据此推断学生不会。',
            '缺少原材料，无法判定学生是否未掌握。',
            '未见作答不代表学生不会。',
            '这里不是盲区，而是缺少观察证据。',
            '不能据此判定要点不全，也不能据此认定学生未掌握。',
            '题干旁没有看到你的手写作答；当前无法确认你是未答还是答在别处，不据此判不会。',
            '题干被截断，本页没有你的手写作答；需结合下一页才能判断是否作答，当前不作不会处理。',
            '没有观察到答案，暂不判定你未掌握。',
            '这段记录尚不视为盲区。',
            '当前不按未掌握处理。',
            '不将空白直接当成能力问题，不据此认定“不会”。',
        ):
            with self.subTest(comment=comment):
                validate_note_feedback({'per_question_feedback': [
                    {'qid_global': 'p6:1', 'zone': '', 'comment': comment}
                ]}, memory, note_ontology([]))

    def test_negation_does_not_exempt_another_affirmative_defect(self):
        memory = {'error_questions': [unit('p6:1', 'uncertain')]}
        for comment in (
            '学生不会。', '学生未掌握。', '这是盲区，必须补答。',
            '不能据此推断学生不会，但学生未掌握。',
            '不能据此推断学生不会，学生仍然要点不全。',
            '这里不是盲区。另一部分存在失分。',
            '并非不能判定学生不会。',
            '不据此判不会，但学生未掌握。',
            '当前不作不会处理；另一部分要点不全。',
            '不据此判不会，学生还是不会。',
            '当前不作不会处理，实际上学生不会。',
            '不是不据此判不会。',
            '不能不判学生不会。',
            '不得不判定学生未掌握。',
        ):
            with self.subTest(comment=comment), self.assertRaises(ValueError):
                validate_note_feedback({'per_question_feedback': [
                    {'qid_global': 'p6:1', 'zone': '', 'comment': comment}
                ]}, memory, note_ontology([]))

    def test_negated_progress_is_not_a_fabricated_trajectory(self):
        validate_note_temporal_text({'summary': '仅有笔记页序，不能据此判定明显进步。'})
        with self.assertRaises(ValueError):
            validate_note_temporal_text({'summary': '不能据此判定明显进步，但后页进步明显。'})

    def test_same_negation_scope_applies_to_annotation_mastery_claims(self):
        memory = {'error_questions': [unit('p1:1', 'correct', 'annotation', '学习要点')]}
        ontology = note_ontology([])
        ontology['zones']['zpd'] = [{'knowledge_point': '笔记整理', 'evidence_basis': 'annotation',
            'evidence': ['p1:1'], 'error_clusters': [], 'rationale': '观察到一条旁批。'}]
        for comment in ('仅有旁批，不据此判已掌握。', '当前不作未掌握处理。'):
            validate_note_feedback({'per_question_feedback': [
                {'qid_global': 'p1:1', 'zone': 'zpd', 'comment': comment}
            ]}, memory, ontology)
        for comment in ('不据此判已掌握，但学生未掌握。', '不能不判学生已掌握。'):
            with self.assertRaises(ValueError):
                validate_note_feedback({'per_question_feedback': [
                    {'qid_global': 'p1:1', 'zone': 'zpd', 'comment': comment}
                ]}, memory, ontology)

    def test_origin_and_annotation_survive_detect_grade_merge(self):
        detect = page(3, 61, kind='textbook')
        detect['questions'][0].update(note_role='annotation', id='1')
        grade = {'questions': [dict(unit('p3:1', role='annotation', text='体裁'),
            annotation_links=[{'marked_text': '编年体通史', 'annotation_text': '体裁', 'relation': '标签概括正文'}])]}
        merged = grader_pass1._merge_detect_and_grade(detect, grade, 'math', 3, feedback_runtime=self.runtime)
        self.assertEqual(merged['page_origin']['printed_page_number'], 61)
        self.assertEqual(merged['questions'][0]['student_answer'], '体裁')
        self.assertEqual(merged['questions'][0]['annotation_links'][0]['marked_text'], '编年体通史')
        prompt = prompts.pass2_feedback_user({'error_questions': merged['questions']}, {}, feedback_runtime=self.runtime)
        self.assertIn('marked_text', prompt)

    def test_notes_do_not_become_correct_because_adjacent_page_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / f'sample_page{i}.json' for i in (1, 2)]
            data = page(1, None, kind='handwritten', after=True)
            data['questions'][0].update(verdict='uncertain', error_type='跨页截断，无法核对')
            safe_json_dump(paths[0], stamp_feedback(data, self.runtime))
            safe_json_dump(paths[1], stamp_feedback(page(2, 3, kind='textbook', before=True), self.runtime))
            count = grader_pass1_review._reconcile_open_material_boundary_errors(
                list(map(str, paths)), feedback_runtime=self.runtime)
            self.assertEqual(count, 0)
            self.assertEqual(safe_json_load(paths[0])['questions'][0]['verdict'], 'uncertain')

    def test_feedback_retries_conflicting_evidence_then_aligns_recommendations(self):
        memory = stamp_feedback({'error_questions': [unit('p1:1')]}, self.runtime)
        ontology = stamp_feedback(note_ontology([]), self.runtime)
        valid = {'open_material_overview': {'subject_and_layout': '一页独立笔记。',
                 'content_review': '记录了数轴三要素。', 'next_steps': ['结合原页核对一个例子。']},
                 'per_question_feedback': [dict(page=1, id='1', qid_global='p1:1', zone='', comment='三要素记录清楚。')]}
        bad = copy.deepcopy(valid); bad['per_question_feedback'][0]['zone'] = 'blind_spot'
        responses = [bad, valid]
        calls = []
        def create(**kwargs):
            calls.append(kwargs['messages'])
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(responses.pop(0), ensure_ascii=False), reasoning_content=''))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with tempfile.TemporaryDirectory() as tmp, patch.object(grader_pass2, '_deepseek_client', return_value=client), \
             patch('app_chat.homework_grading.feedback_model.runtime_client', side_effect=lambda c, *_: c):
            report = grader_pass2.analyze_pass2(memory, 'math', 'sample', str(Path(tmp) / 'report.json'),
                str(Path(tmp) / 'thinking.txt'), ontology=ontology, feedback_runtime=self.runtime)
        self.assertEqual(responses, [])
        self.assertIn('证据校验', calls[1][-1]['content'])
        self.assertNotIn('不是合法 JSON', calls[1][-1]['content'])
        self.assertEqual(report['diagnosis']['next_actions'], valid['open_material_overview']['next_steps'])

    def test_note_prompts_do_not_load_homework_time_or_empty_zone_instructions(self):
        text = prompts.ontology_system('math', None, feedback_runtime=self.runtime)
        self.assertNotIn('必须基于时序', text)
        self.assertNotIn('按 session 顺序排列', text)
        self.assertIn('diagnostic_eligible', text)
        feedback = prompts.pass2_feedback_system('math', feedback_runtime=self.runtime)
        self.assertNotIn('也不要把"已正确"的题目纳入', feedback)
        self.assertNotIn('comment` 写"信息不足，建议人工复核"', feedback)

    def test_diagnostic_retry_rejects_uncertain_evidence_and_can_recover(self):
        units = note_units({'error_questions': [unit('p1:1', 'uncertain')]})
        pack = {'sample_meta': {}, 'evidence_mode': 'notes', 'note_observations': units}
        responses = [note_ontology(['p1:1']), note_ontology([])]
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content=json.dumps(responses.pop(0), ensure_ascii=False), reasoning_content=''))]))))
        with patch.object(ontology_builder, '_deepseek_client', return_value=client), \
             patch('app_chat.homework_grading.feedback_model.runtime_client', side_effect=lambda c, *_: c):
            result = ontology_builder._call_l5(pack, 'math', '', feedback_runtime=self.runtime)
        self.assertEqual(responses, [])
        self.assertEqual(result['zones']['blind_spot'], [])

    def test_unresolved_written_answer_never_becomes_definite_error(self):
        q = dict(unit('p4:1', 'partial', 'written_answer'), cross_page=True, cross_page_resolved=False)
        units = note_units({'error_questions': [q]})
        with self.assertRaises(ValueError):
            validate_note_ontology(note_ontology(['p4:1']), units)
        q['cross_page_resolved'] = True
        validate_note_ontology(note_ontology(['p4:1']), note_units({'error_questions': [q]}))

    def test_invalid_diagnosis_fails_explicitly_without_success_report(self):
        memory = stamp_feedback({'evidence_mode': 'notes', 'error_questions': [unit('p1:1', 'uncertain')]}, self.runtime)
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            ontology_builder, '_call_l5', return_value=note_ontology(['p1:1']),
        ):
            ontology = ontology_builder.build_ontology('math', 'sample', tmp, tmp, {}, [memory], feedback_runtime=self.runtime)
            self.assertEqual(ontology['status'], 'failed')
            target = Path(tmp) / 'report.json'
            with self.assertRaisesRegex(ValueError, '前序诊断失败'):
                grader_pass2.analyze_pass2(memory, 'math', 'sample', str(target),
                    str(Path(tmp) / 'thinking.txt'), ontology=ontology, feedback_runtime=self.runtime)
            self.assertFalse(target.exists())


class NotePageLinkTest(unittest.TestCase):
    def setUp(self):
        self.runtime = runtime_fixture('初中·初一·历史·笔记.pdf')
        self.pages = {1: page(1, 47, after=True), 2: page(2, 45, after=True),
                      3: page(3, None, kind='textbook'), 4: page(4, 48, before=True),
                      5: page(5, 46, before=True)}

    def test_interleaved_pages_match_original_numbers_without_rewriting_qids(self):
        self.assertEqual(candidate_note_page_pairs(self.pages), [[1, 4], [2, 5]])
        with tempfile.TemporaryDirectory() as tmp:
            for n, data in self.pages.items():
                safe_json_dump(Path(tmp) / f'sample_page{n}.detect.json', data)
            result = backfill_note_detect_dir(tmp)
            third = safe_json_load(Path(tmp) / 'sample_page3.detect.json')
        self.assertEqual(result['candidate_pairs'], [[1, 4], [2, 5]])
        self.assertEqual(third['questions'][0]['id'], '1')
        self.assertEqual(third['note_page_link_candidates'], [])

    def test_printed_page_cannot_replace_pdf_identity_through_memory_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); detect_dir = root / 'detect'; detect_dir.mkdir(); final_dir = root / 'final'; final_dir.mkdir()
            for number, data in self.pages.items():
                raw = copy.deepcopy(data)
                if number in (1, 5):
                    raw['page'] = raw['page_origin']['printed_page_number']
                detected = grader_pass1._normalize_detect_result(raw, 'history', number)
                safe_json_dump(detect_dir / f'sample_page{number}.detect.json', detected)
                merged = grader_pass1._merge_detect_and_grade(detected, {'questions': [unit(f'p{number}:1')]},
                    'history', number, feedback_runtime=self.runtime)
                safe_json_dump(final_dir / f'sample_page{number}.json', stamp_feedback(merged, self.runtime))
            linked = backfill_note_detect_dir(str(detect_dir))
            memory = build_memory(str(final_dir), 'history', 'sample', feedback_runtime=self.runtime)
        self.assertEqual(linked['candidate_pairs'], [[1, 4], [2, 5]])
        self.assertEqual([q['qid_global'] for q in memory['error_questions']],
                         ['p1:1', 'p2:1', 'p3:1', 'p4:1', 'p5:1'])

    def test_single_stage_model_page_is_also_overridden_by_server_page(self):
        result = grader_pass1._normalize_pass1_result(
            {'page': 46, 'page_origin': {'printed_page_number': 46}, 'questions': [unit('p5:1')]}, 'history', 5)
        self.assertEqual(result['page'], 5)
        self.assertEqual(result['page_origin']['printed_page_number'], 46)

    def test_unknown_conflicting_or_duplicate_source_is_not_linked(self):
        for mutation in ({'printed_page_number': None}, {'source_title': '另一册练习册'}, {'source_kind': 'textbook'}):
            pages = copy.deepcopy(self.pages); pages[4]['page_origin'].update(mutation)
            self.assertNotIn([1, 4], candidate_note_page_pairs(pages))
        pages = copy.deepcopy(self.pages); pages[6] = copy.deepcopy(pages[4]); pages[6]['page'] = 6
        self.assertNotIn([1, 4], candidate_note_page_pairs(pages))

    def test_scope_and_supporting_evidence_guard_cross_page_corrections(self):
        pages = copy.deepcopy(self.pages)
        for data in pages.values():
            data['questions'][0]['verdict'] = 'uncertain'
        good = dict(page=4, id='1', verdict='correct', cross_page_resolved=True,
                    supporting_qids=['p4:1', 'p1:1'], understanding='两页题干与作答对应',
                    material_status='resolved', reason='合成材料对应', correct_answer='合成依据', error_type='',
                    material_evidence=[{'qid_global': 'p1:1', 'material_label': '',
                                        'quote': '合成原文', 'relation': '对应本问'}])
        for mutation in ({'supporting_qids': ['p4:1', 'p2:1']}, {'supporting_qids': ['p4:1']},
                         {'cross_page_resolved': False}, {'verdict': 'invented'}):
            self.assertEqual(cross_page.merge_corrections(pages, {'corrections': [{**good, **mutation}]},
                feedback_runtime=self.runtime, group=[1, 4]), [])
        self.assertEqual(cross_page.merge_corrections(pages, {'corrections': [good]},
            feedback_runtime=self.runtime, group=[1, 4], scope_page_nums={1}), [])
        applied = cross_page.merge_corrections(pages, {'corrections': [good]},
            feedback_runtime=self.runtime, group=[1, 4], scope_page_nums={4})
        self.assertEqual(len(applied), 1)
        self.assertEqual(pages[1]['questions'][0]['verdict'], 'uncertain')
        self.assertTrue(pages[4]['questions'][0]['cross_page_resolved'])

    def test_notes_default_enabled_explicit_disable_and_question_default_unchanged(self):
        self.assertTrue(cross_page.pass1_5_enabled(feedback_runtime=self.runtime))
        deps = self.runtime.dependencies
        deps['preprocessing']['environment'] = {'HOMEWORK_PASS1_5_ENABLED': '0'}
        disabled = freeze_feedback_runtime(self.runtime.context, **deps)
        self.assertFalse(cross_page.pass1_5_enabled(feedback_runtime=disabled))
        self.assertFalse(cross_page.pass1_5_enabled(feedback_runtime=runtime_fixture()))

    def test_cross_page_model_failure_keeps_pending_and_audit_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pass1 = root / 'pass1'; pass1.mkdir(); clean = root / 'clean'; clean.mkdir()
            for n in (1, 4):
                data = copy.deepcopy(self.pages[n]); data['questions'][0]['verdict'] = 'uncertain'
                safe_json_dump(pass1 / f'sample_page{n}.json', stamp_feedback(data, self.runtime))
                (clean / f'sample_page{n}.png').write_bytes(b'synthetic')
            with patch.object(cross_page, 'grade_cross_page_group', side_effect=TimeoutError('synthetic timeout')):
                applied = cross_page.resolve_cross_pages(str(pass1), str(clean), 'history', 'sample', feedback_runtime=self.runtime)
            self.assertEqual(applied, [])
            self.assertEqual(safe_json_load(root / 'feedback_cross_page_audit.json')['status'], 'completed_with_warnings')
            self.assertEqual(safe_json_load(pass1 / 'sample_page4.json')['questions'][0]['verdict'], 'uncertain')


class NoteReliabilityTest(unittest.TestCase):
    """最小合成协议夹具，不代表历史材料标准答案。"""
    def setUp(self):
        self.runtime = runtime_fixture('初中·初一·历史·笔记.pdf')
        self.pages = {1: page(1, 47, after=True), 4: page(4, 48, before=True)}
        self.pages[1]['questions'] = [dict(unit('p1:source', role='source_excerpt', text=''),
                                          stem_excerpt='材料一 合成材料中记录产量变化。')]
        self.pages[4]['questions'] = [dict(unit('p4:a', 'partial', 'written_answer', '产量变化'),
                                          stem_excerpt='根据材料一回答问题', cross_page=False,
                                          error_type='旧的漏点结论', correct_answer='旧参考内容'),
                                      dict(unit('p4:b', 'correct', 'written_answer', 'B'),
                                           stem_excerpt='本页完整的独立选择题', cross_page=False),
                                      dict(unit('p4:c', 'correct', 'self_question', '旁批自问'), cross_page=False)]

    def resolved(self):
        return dict(page=4, id='a', material_status='resolved', reason='按材料一核对',
                    verdict='correct', error_type='', correct_answer='产量变化',
                    understanding='作答与对应材料一致', cross_page_resolved=True,
                    supporting_qids=['p4:a', 'p1:source'], material_evidence=[{
                        'qid_global': 'p1:source', 'material_label': '材料一',
                        'quote': '合成材料中记录产量变化。', 'relation': '本问指定材料一'}])

    def independent(self):
        return dict(page=4, id='b', material_status='not_required', reason='本页题干和选项完整',
                    verdict='correct', error_type='', correct_answer='B', understanding='本页可核对')

    def run_cross(self, root, response=None, failure=None, missing_image=False, scope=None):
        pass1 = root / 'pass1'; pass1.mkdir(); clean = root / 'clean'; clean.mkdir()
        for n, data in self.pages.items():
            safe_json_dump(pass1 / f'sample_page{n}.json', stamp_feedback(data, self.runtime))
            if not missing_image:
                (clean / f'sample_page{n}.png').write_bytes(b'synthetic')
        with patch.object(cross_page, 'grade_cross_page_group', return_value=response or {},
                          side_effect=failure) as model:
            result = cross_page.resolve_cross_pages(str(pass1), str(clean), 'history', 'sample',
                                                    feedback_runtime=self.runtime, scope_page_nums=scope)
        return result, model, safe_json_load(pass1 / 'sample_page4.json'), safe_json_load(root / 'feedback_cross_page_audit.json')

    def test_missing_question_flag_is_checked_and_repair_reaches_memory_and_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _, model, data, audit = self.run_cross(root, {'corrections': [self.resolved(), self.independent()]})
            self.assertEqual(model.call_count, 1)
            model_input = json.dumps(model.call_args.kwargs['pending_questions'], ensure_ascii=False)
            self.assertNotIn('旧参考内容', model_input)
            self.assertNotIn('旧的漏点结论', model_input)
            self.assertEqual(audit['status'], 'completed')
            self.assertEqual(data['questions'][0]['verdict'], 'correct')
            self.assertEqual(data['questions'][0]['error_type'], '')
            self.assertEqual(data['questions'][1]['assessment_status'], 'observed')
            self.assertNotIn('material_check', data['questions'][2])
            memory = build_memory(str(root / 'pass1'), 'history', 'sample', feedback_runtime=self.runtime)
            q = next(q for q in memory['error_questions'] if q['id'] == 'a')
            self.assertEqual(q['material_check']['evidence'][0]['material_label'], '材料一')
            prompt = prompts.pass2_feedback_user(memory, {}, feedback_runtime=self.runtime)
            self.assertIn('合成材料中记录产量变化', prompt)
            self.assertNotIn('旧的漏点结论', prompt)
            self.assertNotIn('旧参考内容', prompt)

    def test_missing_image_timeout_and_empty_result_do_not_erase_independent_answers(self):
        cases = [(True, None), (False, TimeoutError('synthetic')), (False, None)]
        for missing, failure in cases:
            with self.subTest(missing=missing, failure=failure), tempfile.TemporaryDirectory() as tmp:
                _, _, data, audit = self.run_cross(Path(tmp), failure=failure, missing_image=missing)
                dependent, independent = data['questions'][:2]
                self.assertEqual(dependent['assessment_status'], 'unconfirmed')
                self.assertIsNone(dependent['correct_answer'])
                self.assertEqual(dependent['error_type'], '')
                self.assertEqual(independent['verdict'], 'correct')
                self.assertTrue(independent['diagnostic_eligible'])
                self.assertEqual(audit['status'], 'completed_with_warnings')
                self.assertEqual(len(audit['groups'][0]['units']), 2)

    def test_omitted_unit_is_not_a_completed_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, data, audit = self.run_cross(Path(tmp), {'corrections': [self.independent()]})
            self.assertEqual(audit['groups'][0]['status'], 'unresolved')
            self.assertFalse(data['questions'][0]['diagnostic_eligible'])
            self.assertTrue(data['questions'][1]['diagnostic_eligible'])

    def test_wrong_material_invalid_ref_and_duplicate_response_rejected(self):
        bad_material = self.resolved()
        bad_material['material_evidence'][0]['material_label'] = '材料二'
        bad_ref = self.resolved(); bad_ref['supporting_qids'] = ['p4:a', 'p99:source']
        false_independent = self.independent(); false_independent['id'] = 'a'
        for items in ([bad_material], [bad_ref], [false_independent], [self.resolved(), self.resolved()]):
            with self.subTest(items=items):
                pages = copy.deepcopy(self.pages)
                applied, checks = cross_page._merge_note_checks(pages, {'corrections': items}, [1, 4])
                self.assertEqual(applied, [])
                self.assertEqual(checks[0]['status'], 'unresolved')
                self.assertEqual(pages[4]['questions'][0]['verdict'], 'uncertain')

    def test_local_rerun_preserves_unselected_page_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = copy.deepcopy(self.pages[1])
            self.run_cross(root, {'corrections': [self.resolved(), self.independent()]}, scope={4})
            self.assertEqual(safe_json_load(root / 'pass1/sample_page1.json'), stamp_feedback(original, self.runtime))

    def test_review_changed_text_requires_complete_new_assessment(self):
        for verdict in ('partial', 'uncertain'):
            with self.subTest(verdict=verdict):
                q = dict(unit('p1:a', verdict), student_answer='旧转写', error_type='由旧转写得出的错误',
                         correct_answer='旧答案', understanding='旧诊断')
                data = {'page': 1, 'questions': [q]}
                grader_pass1_review.apply_review_to_page(data, {'items': [{'id': 'a', 'ok': False,
                    'reason': '纠正可见字形', 'fix': {'student_answer': '新转写'}}]}, feedback_runtime=self.runtime)
                self.assertEqual(q['student_answer'], '新转写')
                self.assertEqual(q['verdict'], 'uncertain')
                self.assertEqual(q['error_type'], '')
                self.assertIsNone(q['correct_answer'])
                self.assertNotIn('旧诊断', q['understanding'])
                self.assertEqual(q['self_review']['assessment_reconciliation']['before']['student_answer'], '旧转写')

    def test_review_retains_real_problem_when_complete_new_assessment_given(self):
        q = dict(unit('p1:a', 'partial'), student_answer='旧转写', error_type='旧字形错因')
        grader_pass1_review.apply_review_to_page({'page': 1, 'questions': [q]}, {'items': [{
            'id': 'a', 'ok': False, 'reason': '字形已确认，仍缺少适用条件',
            'fix': {'student_answer': '新转写', 'verdict': 'partial', 'correct_answer': '需要适用条件',
                    'error_type': '适用条件不足'}}]}, feedback_runtime=self.runtime)
        self.assertEqual(q['verdict'], 'partial')
        self.assertEqual(q['error_type'], '适用条件不足')
        self.assertTrue(q['diagnostic_eligible'])
        self.assertNotIn('旧字形', q['understanding'])

    def test_uncertain_review_cannot_restore_old_error_or_answer(self):
        from .note_evidence import normalize_note_fields
        confirmed = normalize_note_fields(dict(unit('p1:c'), error_type='已判对却残留的错因'))
        self.assertEqual(confirmed['error_type'], '')
        self.assertTrue(confirmed['diagnostic_eligible'])
        q = dict(unit('p1:a', 'uncertain'), correct_answer='旧答案', error_type='旧错因')
        grader_pass1_review.apply_review_to_page({'page': 1, 'questions': [q]}, {'items': [{
            'id': 'a', 'ok': False, 'reason': '待确认', 'fix': {'correct_answer': '新猜测', 'error_type': '旧错因'}}]},
            feedback_runtime=self.runtime)
        self.assertIsNone(q['correct_answer'])
        self.assertEqual(q['error_type'], '')
        for role in ('teaching_prompt', 'self_question', 'reading_prompt', 'source_excerpt'):
            candidate = dict(unit('p1:a', role=role), correct_answer='不应代答')
            normalize_note_fields(candidate)
            self.assertIsNone(candidate['correct_answer'])
            self.assertEqual(candidate['assessment_status'], 'not_assessed')

    def test_review_snapshot_carries_source_and_non_notes_keep_previous_behavior(self):
        q = dict(unit('p1:a', 'partial'), correct_answer='已有参考', material_check={'status': 'resolved',
            'evidence': [{'quote': '合成材料依据'}]}, error_type='原错因')
        snapshot = grader_pass1_review._build_review_snapshot({'page': 1, 'questions': [q]})
        self.assertIn('合成材料依据', json.dumps(snapshot, ensure_ascii=False))
        for name in ('初中·初一·数学·作业.pdf', '初中·初一·语文·作文.pdf', '初中·初一·数学·试卷.pdf'):
            candidate = copy.deepcopy(q)
            grader_pass1_review.apply_review_to_page({'page': 1, 'questions': [candidate]}, {'items': [{
                'id': 'a', 'ok': False, 'fix': {'student_answer': '另一个转写'}}]}, feedback_runtime=runtime_fixture(name))
            self.assertEqual(candidate['verdict'], 'partial')
            self.assertEqual(candidate['correct_answer'], '已有参考')

    def test_note_staged_pipeline_resanitizes_final_pages_and_saved_memory(self):
        from contextlib import ExitStack
        from unittest.mock import Mock
        from . import staged_pipeline as pipeline
        from .feedback_snapshot_test import snapshot_arguments
        from .feedback_snapshot import prepare_feedback_snapshot
        from .note_evidence import normalize_note_fields
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            args = snapshot_arguments(tmp)
            args.update(context=self.runtime.context, **self.runtime.dependencies)
            root = Path(tmp) / 'run'; prepare_feedback_snapshot(root, **args)
            base = root / 'homework_grading'; base.mkdir()
            paths = {'base': str(base), 'root': str(root), 'manifest': str(root / 'manifest.json')}
            for name in ('raw', 'clean', 'pass1_json', 'pass2_report', 'annotated',
                         'annotated_layout', 'annotated_understanding'):
                directory = base / name; directory.mkdir(); paths[name] = str(directory)
            page_file = Path(paths['pass1_json']) / 'sample_page1.json'
            q = normalize_note_fields(dict(unit('p1:a', role='self_question'), correct_answer='旧的自动答案'))
            safe_json_dump(page_file, stamp_feedback({'page': 1, 'questions': [q]}, self.runtime))
            pages = [{'page': 1, 'clean_abs_path': str(base / 'clean/sample_page1.png')}]
            replacements = {
                '_resolve_user_file_path': args['source_path'],
                'resolve_source_document_sha256': args['expected_source_sha256'],
                'load_homework_clean_pages': [], 'preprocess_pdf': pages,
                'build_pre_pass1_session_map': None, '_update_task': None,
                '_run_detect_all_pages': None, '_merge_all_pages_from_detect': None,
                '_run_pass1_grade_all_pages': 2, '_render_pages': None,
                'infer_homework_stage_status': {'understanding': 'done'},
                '_stages_needed_for_target': ['layout', 'understanding', 'grading'],
                'resolve_cross_pages': [], 'review_pass1_dir': {},
                'verify_pass1_dir': {}, 'verify_answer_statements': {},
                'build_all_session_memories': [], 'build_student_profile': {},
                'evaluate_homework_red_blue': {'status': 'ready'},
            }
            for name, value in replacements.items():
                stack.enter_context(patch.object(pipeline, name, return_value=value))
            def ontology(*args, **kwargs):
                value = stamp_feedback(note_ontology([]), self.runtime)
                safe_json_dump(base / 'student_ontology.json', value)
                return value
            def report(*args, **kwargs):
                value = {'open_material_overview': {'next_steps': ['保留自问']}, 'diagnosis': {},
                         'per_question_feedback': [{'page': 1, 'id': 'a', 'qid_global': 'p1:a',
                                                    'zone': '', 'comment': '保留自问，供后续探究。'}]}
                # 正式编排的report_path由其调用参数取得。
                safe_json_dump(args[3], stamp_feedback(value, self.runtime))
            def final_filter(*args, **kwargs):
                value = safe_json_load(page_file)
                value['questions'][0]['correct_answer'] = '下游意外恢复的自动答案'
                value['questions'][0]['error_type'] = '下游意外恢复的错因'
                safe_json_dump(page_file, value)
                return {}
            stack.enter_context(patch.object(pipeline, 'build_ontology', side_effect=ontology))
            stack.enter_context(patch.object(pipeline, 'analyze_pass2', side_effect=report))
            stack.enter_context(patch.object(pipeline, 'run_hallucination_filter', side_effect=final_filter))
            stack.enter_context(patch.object(pipeline.CIIndexManager, 'update_status'))
            stack.enter_context(patch('app_chat.homework_grading.feedback_artifacts.validate_artifacts', return_value=[]))
            pipeline.execute_staged_homework_grading('synthetic-task', 'synthetic-user',
                'synthetic-source.pdf', args['analysis_id'], paths,
                {'homework_subject': 'history', 'homework_grade': 7}, 'grading',
                Mock(return_value=[]), feedback_runtime=self.runtime)
            final = safe_json_load(page_file)['questions'][0]
            self.assertIsNone(final['correct_answer'])
            self.assertEqual(final['error_type'], '')
            saved = list(Path(paths['pass2_report']).glob('*_memory.json'))
            self.assertTrue(saved)
            for file in saved:
                self.assertIsNone(safe_json_load(file)['error_questions'][0]['correct_answer'])


if __name__ == '__main__':
    unittest.main()
