"""作文／笔记的标记事实；不改写纯转写，不从颜色推断身份或掌握。"""
import copy
import re

from .feedback_material_kinds import is_open_material


MARKING_FIELDS = ('printed_text_marked', 'handwritten_text_marked', 'annotation_links', 'marking_warnings')
_TAG = re.compile(r'<(/?)([^<>]{1,60})>')
_NAME = re.compile(r'(?:(?:红|橙|黄|绿|蓝|紫|粉|黑|灰|棕|白|青)色|颜色不明)(?:荧光笔涂画|笔|下划线|圈画)')


def open_material_runtime(runtime):
    return runtime is not None and is_open_material(runtime.context.get('material_type'))


def unmark(text):
    """只接受闭合的已知文字标签，返回纯文本和是否存在有效标记。"""
    if not isinstance(text, str):
        raise ValueError('标记文本必须为字符串')
    stack, found = [], False
    for tag in _TAG.finditer(text):
        closing, name = tag.groups()
        if not _NAME.fullmatch(name):
            raise ValueError('包含不支持的颜色标签')
        if closing:
            if not stack or stack.pop() != name:
                raise ValueError('颜色标签未正确配对')
        else:
            stack.append(name)
            found = True
    if stack:
        raise ValueError('颜色标签未闭合')
    return _TAG.sub('', text), found


def normalize_markings(question, *, layout=False):
    warnings = question.get('marking_warnings')
    warnings = [s for s in warnings if isinstance(s, str)] if isinstance(warnings, list) else []
    for field in ('printed_text_marked', 'handwritten_text_marked'):
        if field not in question:
            continue
        value = question[field]
        try:
            plain, marked = unmark(value)
            if not marked or not plain.strip():
                question.pop(field, None)
                continue
            if field == 'handwritten_text_marked' and not layout:
                if plain.strip() != str(question.get('student_answer') or '').strip():
                    raise ValueError('去除标签后的文字与手写转写不一致，已保留原转写')
            question[field] = value.strip()
        except ValueError as exc:
            question.pop(field, None)
            warnings.append(('手写笔色：' if field.startswith('handwritten') else '印刷标记：') + str(exc))
    if 'annotation_links' in question:
        links = question['annotation_links']
        question['annotation_links'] = [
            {key: str(item.get(key) or '').strip() for key in ('marked_text', 'annotation_text', 'relation')}
            for item in (links if isinstance(links, list) else []) if isinstance(item, dict)
        ][:20]
        if not layout and 'student_answer' in question:
            retained = []
            for link in question['annotation_links']:
                if link['annotation_text'] and link['annotation_text'] not in str(question.get('student_answer') or ''):
                    warnings.append('标注关系：旁批文字与当前手写转写不对应，已移除失效关联')
                else:
                    retained.append(link)
            question['annotation_links'] = retained
    if warnings:
        question['marking_warnings'] = list(dict.fromkeys(warnings))
    return question


def observation_eligible(question):
    q = normalize_markings(copy.deepcopy(question))
    printed = unmark(q.get('printed_text_marked', ''))[0]
    handwritten = str(q.get('student_answer') or '').strip()
    if q.get('printed_text_marked') or q.get('handwritten_text_marked'):
        return True
    for link in q.get('annotation_links') or []:
        marked, annotation = link['marked_text'], link['annotation_text']
        if (link['relation'] and (marked or annotation)
                and (not marked or marked in (printed or str(q.get('stem_excerpt') or '')))
                and (not annotation or annotation in handwritten)):
            return True
    return q.get('note_role') in ('annotation', 'self_question') and bool(handwritten)


def open_units(memory, material_type):
    from .note_evidence import normalize_note_fields
    units = []
    for raw in memory.get('error_questions') or []:
        q = normalize_markings(copy.deepcopy(raw))
        if material_type == 'notes':
            normalize_note_fields(q)
        else:
            q['diagnostic_eligible'] = bool(
                str(q.get('student_answer') or '').strip()
                and q.get('verdict') in ('correct', 'partial', 'wrong')
                and q.get('note_role') not in ('source_excerpt', 'self_question', 'teaching_prompt', 'reading_prompt')
                and not (q.get('material_check') or {}).get('blocks_assessment'))
        q['observation_eligible'] = observation_eligible(q)
        units.append(q)
    return units


def normalize_markings_dir(pass1_dir, *, feedback_runtime, page_nums=None):
    from .utils import safe_json_load, safe_json_dump, sorted_json_pages
    from .feedback_runtime import stamp_feedback
    if not open_material_runtime(feedback_runtime):
        return
    for path in sorted_json_pages(pass1_dir):
        page = safe_json_load(path)
        if page_nums is not None and page.get('page') not in page_nums:
            continue
        for q in page.get('questions') or []:
            normalize_markings(q)
        safe_json_dump(path, stamp_feedback(page, feedback_runtime, 'markings'))
