"""成功前校验实际产物，避免缺页、坏JSON或空报告被当作可复用完成版本。"""
import json
from pathlib import Path

from PIL import Image


def _read_object(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('批改产物缺失或格式损坏：' + Path(path).name) from exc
    if not isinstance(data, dict):
        raise ValueError('批改产物不是有效对象：' + Path(path).name)
    return data


def validate_artifacts(paths, pages, manifest, target, *, expected_pages=None):
    numbers = [page['page'] for page in pages]
    if not numbers or len(set(numbers)) != len(numbers):
        raise ValueError('批改页面缺失或重复')
    if expected_pages is not None and set(numbers) != set(range(1, expected_pages + 1)):
        raise ValueError('批改页数与原PDF不一致，不能标记完成')
    warnings, questions = [], 0
    stage_dir = {'layout': 'annotated_layout', 'understanding': 'annotated_understanding', 'grading': 'annotated'}[target]
    for page in pages:
        stem = Path(page['clean_abs_path']).stem
        payload = _read_object(Path(paths['pass1_json']) / (stem + '.json'))
        items = payload.get('questions')
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError(f'第{page["page"]}页题目结构损坏')
        questions += len(items)
        for directory in ('raw', 'clean', stage_dir):
            path = Path(paths[directory]) / (stem + '.png')
            try:
                with Image.open(path) as image:
                    image.verify()
            except (OSError, ValueError, SyntaxError) as exc:
                raise ValueError(f'第{page["page"]}页原图或批改图缺失、损坏') from exc
        if not items:
            warnings.append(f'第{page["page"]}页未识别到题目，请核对原页是否为空白或非题目内容')
    if target == 'grading':
        if questions == 0:
            raise ValueError('整份材料未识别到题目，不能生成空批改成功；请核对原页')
        subject = manifest.get('subject') or 'unknown'
        group_id = str(manifest.get('group_id') or '')
        if group_id.startswith('homework_'):
            group_id = group_id[len('homework_'):]
        sample = group_id[:8] or 'sample'
        report = _read_object(Path(paths['pass2_report']) / f'{subject}_{sample}_report.json')
        if not report.get('diagnosis') and not report.get('zone_classification'):
            raise ValueError('材料已有题目但整篇报告为空，不能标记批改完成')
    return warnings


def mark_stage(paths, manifest, stage):
    from app_chat.ci.file_io import atomic_json
    manifest['processing_stage'] = stage
    atomic_json(paths['manifest'], manifest)


def record_failure(paths, error):
    from app_chat.ci.file_io import atomic_json
    manifest = _read_object(paths['manifest'])
    stage = manifest.get('processing_stage') or 'startup'
    manifest.update(status='failed', failure_stage=stage, error=str(error))
    atomic_json(paths['manifest'], manifest)
    return stage
