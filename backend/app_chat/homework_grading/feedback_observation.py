"""有限时长的本地内容观察；只建议，不修改声明或冻结指纹。"""
import hashlib
import json
from pathlib import Path
import re
import time

from .feedback_metadata import resolve_feedback_metadata

FIELD_LABELS = {'education_level': '学段', 'grade': '年级', 'subject': '课程', 'material_type': '材料类型'}
PATTERNS = {
    'education_level': r'(?:学段|教育阶段)\s*[:：]\s*(小学|初中|高中|大学|研究生)',
    'grade': r'(?:年级\s*[:：]\s*)?([一二三四五六七八九1-9]年级|初[一二三123]|高[一二三123]|大[一二三四1234])',
    'subject': r'(?:科目|学科|课程名称|课程)\s*[:：]\s*([^\s，,；;。]{1,30})',
    'material_type': r'(?:材料类型)\s*[:：]\s*(作业|试卷|笔记|作文|日志)',
}


def observe_records(records, context, *, expected_pages=None, reason=None):
    evidence, values, covered = [], {}, set()
    for record in records:
        text = record.get('text', '')
        if not isinstance(text, str) or not text.strip():
            continue
        page_number = record.get('page')
        if (type(page_number) is not int or page_number < 1
                or (expected_pages is not None and page_number > expected_pages)):
            page_number = None
        if page_number is not None:
            covered.add(page_number)
        matches = []
        for field, pattern in PATTERNS.items():
            matches.extend((field, match.group(1), match) for match in re.finditer(pattern, text))
        for match in re.finditer(r'(小学|初中|高中|大学)\s*([一二三四五六七八九1-9]年级|初[一二三]|高[一二三]|大[一二三四])', text):
            matches.append(('education_level', match.group(1), match))
        for field, value, match in matches:
            values.setdefault(field, set()).add(value)
            evidence.append({'field': field, 'value': value, 'page': page_number,
                'source': record.get('source'), 'source_sha256': record.get('source_sha256'),
                'excerpt': text[max(0, match.start()-20):match.end()+30]})
    suggestions = {key: next(iter(items)) for key, items in values.items() if len(items) == 1}
    # 规范化建议只用于比较，不把冻结声明注入观察，也不反向补全冻结值。
    normalized = resolve_feedback_metadata('content-observation.pdf', suggestions)
    conflicts = [key for key, items in values.items() if len(items) > 1]
    for field, keys in {'education_level': ('education_level',), 'grade': ('grade_global', 'grade_in_level'),
                        'subject': ('subject_key',), 'material_type': ('material_type',)}.items():
        if field not in suggestions:
            continue
        for key in keys:
            observed, declared = normalized.get(key), context.get(key)
            if observed not in (None, 'unknown') and declared not in (None, 'unknown') and observed != declared:
                conflicts.append(field)
                break
    conflicts = sorted(set(conflicts))
    warnings = ['内容中的' + FIELD_LABELS[key] + '与本次材料设置不一致或出现多个值；请核对，采纳修改需完整新跑' for key in conflicts]
    if reason:
        warnings.append(reason)
    return {'schema_version': 'feedback-observation-v1',
        'status': 'conflict' if conflicts else ('consistent' if evidence and not reason else 'inconclusive'),
        'suggestions': suggestions, 'evidence': evidence, 'conflict_fields': conflicts,
        'coverage': {'pages': sorted(covered), 'expected_pages': expected_pages,
                     'complete': expected_pages is not None and covered == set(range(1, expected_pages+1))},
        'warnings': warnings, 'frozen_context_changed': False}


def collect_observation(pdf_path, context, *, pass1_dir=None, expected_pages=None, budget_seconds=0.25):
    from .sessions import _find_ocr_markdown, _split_ocr_pages
    from .utils import parse_page_num
    deadline = time.monotonic() + budget_seconds
    records, reason = [], None
    def read(path):
        if time.monotonic() >= deadline:
            raise TimeoutError('内容观察达到时限，已保留当前证据，批改可继续')
        with Path(path).open('rb') as handle:
            data = handle.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('已有识别文件超出本次观察范围，材料信息仍需人工核对')
        return data.decode('utf-8'), hashlib.sha256(data).hexdigest()
    try:
        ocr = _find_ocr_markdown(str(pdf_path))
        if ocr:
            text, digest = read(ocr)
            pages = _split_ocr_pages(text)
            for number, page in enumerate(pages, 1):
                records.append({'page': number if len(pages) == expected_pages else None,
                    'text': '\n'.join(page.splitlines()[:12]), 'source': 'existing_ocr', 'source_sha256': digest})
        if pass1_dir and Path(pass1_dir).is_dir():
            for path in sorted(Path(pass1_dir).glob('*.detect.json')):
                text, digest = read(path)
                page = json.loads(text)
                records.append({'page': parse_page_num(path.name.replace('.detect.json', '.json')), 'text': page.get('page_header', ''),
                                'source': 'page_header', 'source_sha256': digest})
    except (OSError, ValueError, TimeoutError, TypeError, AttributeError) as exc:
        reason = str(exc) if isinstance(exc, TimeoutError) else '已有识别证据暂不可完整读取，批改可继续'
    return observe_records(records, context, expected_pages=expected_pages, reason=reason)


def update_runtime_observation(task_id, paths, manifest, pdf_path, runtime, page_count):
    if runtime is None:
        return
    from app_chat.ci._utils import _update_task
    from .utils import safe_json_dump
    observation = collect_observation(pdf_path, runtime.context, pass1_dir=paths['pass1_json'], expected_pages=page_count)
    manifest['content_validation'] = observation
    previous = manifest.get('warnings', [])
    manifest['warnings'] = list(dict.fromkeys(previous + observation['warnings']))
    safe_json_dump(paths['manifest'], manifest)
    _update_task(task_id, content_validation=observation, warnings=manifest['warnings'])
