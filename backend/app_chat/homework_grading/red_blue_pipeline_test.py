import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from unittest import mock

from app_chat.homework_grading import service
from app_chat.homework_grading import staged_pipeline as pipeline


class RedBluePipelineTest(unittest.TestCase):
    def _workspace(self, root):
        base = os.path.join(root, 'homework_grading')
        paths = {
            'root': root,
            'base': base,
            'raw': os.path.join(base, 'raw'),
            'clean': os.path.join(base, 'clean'),
            'pass1_json': os.path.join(base, 'pass1_json'),
            'pass2_report': os.path.join(base, 'pass2_report'),
            'annotated': os.path.join(base, 'annotated'),
            'annotated_layout': os.path.join(base, 'annotated_layout'),
            'annotated_understanding': os.path.join(base, 'annotated_understanding'),
            'manifest': os.path.join(root, 'manifest.json'),
        }
        for path in paths.values():
            if path.endswith('.json'):
                continue
            os.makedirs(path, exist_ok=True)
        with open(paths['manifest'], 'w', encoding='utf-8') as file:
            json.dump({
                'analysis_type': 'homework_grading',
                'group_id': 'homework_fixture',
                'subject': 'math',
                'subject_label': '数学',
                'status': 'partial',
                'stages': {
                    'layout': 'done',
                    'understanding': 'done',
                    'grading': 'pending',
                },
            }, file)
        return paths

    def _base_patches(self, stack, pages):
        stack.enter_context(mock.patch.object(
            pipeline, 'load_homework_clean_pages', return_value=pages,
        ))
        stack.enter_context(mock.patch.object(
            pipeline, '_resolve_user_file_path', return_value='',
        ))
        stack.enter_context(mock.patch.object(
            pipeline, 'resolve_source_document_sha256', return_value='',
        ))
        stack.enter_context(mock.patch.object(pipeline, 'write_sample_meta'))
        stack.enter_context(mock.patch.object(
            pipeline, 'pass1_two_stage_enabled', return_value=True,
        ))
        stack.enter_context(mock.patch.object(
            pipeline,
            'prepare_fixed_sample_crossout_images',
            return_value={'enabled': False},
        ))
        stack.enter_context(mock.patch.object(pipeline, '_update_task'))
        stack.enter_context(mock.patch.object(pipeline.CIIndexManager, 'update_status'))

    def test_layout_or_understanding_completion_does_not_score(self):
        with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
            paths = self._workspace(root)
            pages = [{'page': 1, 'clean_abs_path': os.path.join(paths['clean'], 'page1.png')}]
            self._base_patches(stack, pages)
            stack.enter_context(mock.patch.object(
                pipeline, '_stages_needed_for_target', return_value=[],
            ))
            scorer = stack.enter_context(mock.patch.object(
                pipeline, 'evaluate_homework_red_blue',
            ))

            pipeline.execute_staged_homework_grading(
                task_id='task',
                username='user',
                filename='fixture.pdf',
                analysis_id='homework_fixture',
                paths=paths,
                homework_attrs={'homework_subject': 'math', 'homework_grade': 4},
                target_stage='understanding',
                build_page_units_fn=lambda *_args: [],
            )

            scorer.assert_not_called()
            with open(paths['manifest'], 'r', encoding='utf-8') as file:
                manifest = json.load(file)
            self.assertEqual(manifest['status'], 'partial')

    def test_grading_renders_then_scores_and_soft_failure_retains_partial_delivery(self):
        with tempfile.TemporaryDirectory() as root, ExitStack() as stack:
            paths = self._workspace(root)
            pages = [{'page': 1, 'clean_abs_path': os.path.join(paths['clean'], 'page1.png')}]
            self._base_patches(stack, pages)
            stack.enter_context(mock.patch.object(
                pipeline, '_stages_needed_for_target', return_value=['grading'],
            ))
            stack.enter_context(mock.patch.object(
                pipeline,
                'infer_homework_stage_status',
                return_value={'layout': 'done', 'understanding': 'done', 'grading': 'pending'},
            ))
            stack.enter_context(mock.patch.object(pipeline, 'resolve_cross_pages', return_value=[]))
            stack.enter_context(mock.patch.object(pipeline, 'pass1_5_enabled', return_value=False))
            stack.enter_context(mock.patch.object(pipeline, 'review_pass1_dir', return_value={}))
            stack.enter_context(mock.patch.object(pipeline, 'verify_pass1_dir', return_value={}))
            stack.enter_context(mock.patch.object(pipeline, 'verify_answer_statements', return_value={}))
            stack.enter_context(mock.patch.object(
                pipeline, '_reapply_slot_presence_guards_for_pages', return_value=0,
            ))
            stack.enter_context(mock.patch.object(
                pipeline, '_reapply_fixed_english_choice_guards_for_pages', return_value=0,
            ))
            stack.enter_context(mock.patch.object(pipeline, 'slot_presence_mode', return_value='off'))
            stack.enter_context(mock.patch.object(
                pipeline, 'build_memory', return_value={'error_questions': []},
            ))
            stack.enter_context(mock.patch.object(pipeline, 'save_memory'))
            stack.enter_context(mock.patch.object(
                pipeline, 'build_all_session_memories', return_value=[],
            ))
            stack.enter_context(mock.patch.object(pipeline, 'build_student_profile', return_value=None))
            stack.enter_context(mock.patch.object(
                pipeline, 'load_sample_meta', return_value={'subject': 'math', 'grade': 4, 'stage': 2},
            ))
            stack.enter_context(mock.patch.object(pipeline, 'build_ontology', return_value={}))
            def write_report(*args, **kwargs):
                from .utils import safe_json_dump
                safe_json_dump(args[3], {'diagnosis': {}, 'zone_classification': {}, 'per_question_feedback': []})
            stack.enter_context(mock.patch.object(pipeline, 'analyze_pass2', side_effect=write_report))
            stack.enter_context(mock.patch.object(
                pipeline, 'run_hallucination_filter', return_value={},
            ))
            stack.enter_context(mock.patch.object(pipeline.traceback, 'print_exc'))
            events = []
            stack.enter_context(mock.patch.object(
                pipeline, '_render_pages', side_effect=lambda *_args, **_kwargs: events.append('render'),
            ))
            def fail_review(*_args, **_kwargs):
                events.append('score')
                raise RuntimeError('temporary Kimi failure')

            stack.enter_context(mock.patch.object(
                pipeline,
                'evaluate_homework_red_blue',
                side_effect=fail_review,
            ))

            pipeline.execute_staged_homework_grading(
                task_id='task',
                username='user',
                filename='fixture.pdf',
                analysis_id='homework_fixture',
                paths=paths,
                homework_attrs={'homework_subject': 'math', 'homework_grade': 4},
                target_stage='grading',
                build_page_units_fn=lambda *_args: [],
            )

            self.assertEqual(events, ['render', 'score'])
            with open(paths['manifest'], 'r', encoding='utf-8') as file:
                manifest = json.load(file)
            self.assertEqual(manifest['status'], 'partial')
            self.assertEqual(manifest['completion']['status'], 'incomplete')
            self.assertEqual(manifest['stages']['grading'], 'done')
            self.assertEqual(manifest['red_blue_review']['status'], 'failed')

    def test_retry_task_only_calls_red_blue_scorer(self):
        with tempfile.TemporaryDirectory() as root:
            paths = self._workspace(root)
            with mock.patch.object(service, 'prepare_homework_workspace', return_value=paths), \
                 mock.patch.object(service, 'saved_report_ready', return_value=True), \
                 mock.patch.object(
                     service,
                     'infer_homework_stage_status',
                     return_value={'layout': 'done', 'understanding': 'done', 'grading': 'done'},
                 ), \
                 mock.patch.object(service, 'load_homework_clean_pages', return_value=[]), \
                 mock.patch.object(
                     service,
                     'evaluate_homework_red_blue',
                     return_value={'status': 'ready', 'score': 4.4, 'color': 'purple'},
                 ) as scorer, \
                 mock.patch.object(service, 'execute_staged_homework_grading') as grading, \
                 mock.patch.object(service, '_update_task'), \
                 mock.patch.object(service.CIIndexManager, 'update_status'):
                service.run_homework_red_blue_review('task', 'user', 'homework_fixture')

            scorer.assert_called_once()
            grading.assert_not_called()
            with open(paths['manifest'], 'r', encoding='utf-8') as file:
                manifest = json.load(file)
            self.assertEqual(manifest['red_blue_review']['score'], 4.4)


if __name__ == '__main__':
    unittest.main()
