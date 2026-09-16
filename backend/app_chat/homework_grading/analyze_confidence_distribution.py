#!/usr/bin/env python
"""统计 pass1_json 置信度分布；按学科汇总白/深灰/中灰/浅灰/黑区占比。

Usage (在 本地backend 目录):
  python -m app_chat.homework_grading.analyze_confidence_distribution --docs-dir docs
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app_chat.homework_grading.confidence_zones import (  # noqa: E402
    GRAY_SHADE_KEYS,
    SHADE_DISPLAY,
    SHADE_ORDER,
    SUBJECT_LABELS,
    combined_recognition_understanding_confidence,
    get_thresholds,
    gray_shade_confidence_range,
    shade_distribution_pct,
    shade_distribution_pct_mixed,
)

MODE_LABELS = {
    'layout': '无损版面',
    'understanding': '无损理解',
    'grading': '三区批改',
}

SUBJECT_ORDER = ('math', 'chinese', 'english')


def _subject_from_filename(path: str) -> str:
    name = os.path.basename(path)
    return name.split('_', 1)[0].lower()


def _collect(docs_dir: str, skip: str | None) -> tuple[dict, dict, dict]:
    by_subject: dict[str, dict[str, list[int]]] = {}
    mixed: dict[str, list[tuple[int, str]]] = {
        'layout': [],
        'understanding': [],
        'grading': [],
    }
    for hw in sorted(os.listdir(docs_dir)):
        if not hw.startswith('homework_') or (skip and hw == skip):
            continue
        p1 = os.path.join(docs_dir, hw, 'homework_grading', 'pass1_json')
        if not os.path.isdir(p1):
            continue
        for path in glob.glob(os.path.join(p1, '*.json')):
            if '.detect.' in path or '.grade.' in path:
                continue
            subject = _subject_from_filename(path)
            if subject not in SUBJECT_ORDER:
                continue
            by_subject.setdefault(subject, {'layout': [], 'understanding': [], 'grading': []})
            data = json.load(open(path, encoding='utf-8'))
            for q in data.get('questions') or []:
                if not isinstance(q, dict):
                    continue
                if q.get('layout_confidence') is not None:
                    val = int(q['layout_confidence'])
                    by_subject[subject]['layout'].append(val)
                    mixed['layout'].append((val, subject))
                comb = combined_recognition_understanding_confidence(q)
                if comb is not None:
                    by_subject[subject]['understanding'].append(comb)
                    mixed['understanding'].append((comb, subject))
                if q.get('grading_confidence') is not None:
                    val = int(q['grading_confidence'])
                    by_subject[subject]['grading'].append(val)
                    mixed['grading'].append((val, subject))
    return by_subject, mixed


def _print_threshold_table() -> None:
    print('当前分学科阈值（black 三科共用：layout<75 / understanding<82 / grading<83）')
    print(f'{"学科":<6} {"模式":<10} {"白区>=":>8} {"黑区<":>8}')
    print('-' * 40)
    for subject in SUBJECT_ORDER:
        label = SUBJECT_LABELS[subject]
        for mode in ('layout', 'understanding', 'grading'):
            w, b = get_thresholds(mode, subject=subject)  # type: ignore[arg-type]
            print(f'{label:<6} {MODE_LABELS[mode]:<10} {w:>8} {b:>8}')
        if subject != SUBJECT_ORDER[-1]:
            print('-' * 40)


def _shade_header() -> str:
    parts = [f'{SHADE_DISPLAY[k]}%' for k in SHADE_ORDER]
    return f'{"学科":<6} {"n":>6} ' + ' '.join(f'{p:>7}' for p in parts)


def _shade_row(label: str, arr: list[int], mode: str, subject: str) -> str:
    if not arr:
        return f'{label:<6} {"—":>6} ' + ' '.join(f'{"—":>7}' for _ in SHADE_ORDER)
    pct = shade_distribution_pct(arr, mode, subject=subject)  # type: ignore[arg-type]
    cells = ' '.join(f'{pct[k]:>6.1f}%' for k in SHADE_ORDER)
    return f'{label:<6} {len(arr):>6} {cells}'


def _shade_row_mixed(label: str, records: list[tuple[int, str]], mode: str) -> str:
    if not records:
        return f'{label:<6} {"—":>6} ' + ' '.join(f'{"—":>7}' for _ in SHADE_ORDER)
    pct = shade_distribution_pct_mixed(records, mode)  # type: ignore[arg-type]
    cells = ' '.join(f'{pct[k]:>6.1f}%' for k in SHADE_ORDER)
    return f'{label:<6} {len(records):>6} {cells}'


def _print_gray_ranges(mode: str, subject: str) -> None:
    white_th, black_th = get_thresholds(mode, subject=subject)  # type: ignore[arg-type]
    label = SUBJECT_LABELS.get(subject, subject)
    print(f'  [{label}] white>={white_th} black<{black_th}  灰区 {black_th}–{white_th - 1}')
    for shade in GRAY_SHADE_KEYS:
        rng = gray_shade_confidence_range(mode, shade, subject=subject)  # type: ignore[arg-type]
        print(f'      {SHADE_DISPLAY[shade]}: {rng}')


def _print_summary_line(pct: dict[str, float]) -> None:
    gray_total = pct['gray_deep'] + pct['gray_mid'] + pct['gray_light']
    print(f'  汇总: 白 {pct["white"]:.1f}% | 灰 {gray_total:.1f}%'
          f'（深 {pct["gray_deep"]:.1f}% + 中 {pct["gray_mid"]:.1f}% + 浅 {pct["gray_light"]:.1f}%）'
          f' | 黑 {pct["black"]:.1f}%')


def _report_overall(mode: str, mixed_records: list[tuple[int, str]]) -> None:
    if not mixed_records:
        print(f'\n{MODE_LABELS[mode]}: (无数据)')
        return
    values = [v for v, _ in mixed_records]
    arr_sorted = sorted(values)
    n = len(arr_sorted)
    print(f'\n=== {MODE_LABELS[mode]} (全量 n={n}，按题所属学科阈值) ===')
    print(f'  min={arr_sorted[0]} med={arr_sorted[n // 2]} max={arr_sorted[-1]}')
    print(_shade_header())
    print('-' * 62)
    print(_shade_row_mixed('合计', mixed_records, mode))
    pct = shade_distribution_pct_mixed(mixed_records, mode)  # type: ignore[arg-type]
    _print_summary_line(pct)


def _report_by_subject(by_subject: dict) -> None:
    print('\n' + '=' * 72)
    print('按学科统计（各科使用各自阈值）')
    print('=' * 72)
    for mode in ('layout', 'understanding', 'grading'):
        print(f'\n【{MODE_LABELS[mode]}】')
        for subject in SUBJECT_ORDER:
            _print_gray_ranges(mode, subject)
        print(_shade_header())
        print('-' * 62)
        for subject in SUBJECT_ORDER:
            arr = by_subject.get(subject, {}).get(mode, [])
            label = SUBJECT_LABELS.get(subject, subject)
            print(_shade_row(label, arr, mode, subject))
        all_records: list[tuple[int, str]] = []
        for subject in SUBJECT_ORDER:
            for val in by_subject.get(subject, {}).get(mode, []):
                all_records.append((val, subject))
        if all_records:
            print('-' * 62)
            print(_shade_row_mixed('合计', all_records, mode))
            _print_summary_line(shade_distribution_pct_mixed(all_records, mode))  # type: ignore[arg-type]

        # 三科白区占比排序（检验 understanding ≥ grading ≥ layout 等）
        white_pcts = []
        for subject in SUBJECT_ORDER:
            arr = by_subject.get(subject, {}).get(mode, [])
            if not arr:
                continue
            pct = shade_distribution_pct(arr, mode, subject=subject)  # type: ignore[arg-type]
            white_pcts.append((SUBJECT_LABELS[subject], pct['white']))
        if white_pcts:
            order = ' > '.join(f'{name} {wp:.1f}%' for name, wp in sorted(white_pcts, key=lambda x: -x[1]))
            print(f'  白区排序: {order}')


def main() -> None:
    parser = argparse.ArgumentParser(description='分析置信度分布：白/深灰/中灰/浅灰/黑区（分学科阈值）')
    parser.add_argument('--docs-dir', default='docs')
    parser.add_argument('--skip', default='', help='跳过的 homework_xxx')
    parser.add_argument('--by-subject', action='store_true', help='仅输出按学科统计')
    args = parser.parse_args()
    docs = args.docs_dir
    if not os.path.isabs(docs):
        docs = os.path.join(_BACKEND_ROOT, docs)

    by_subject, mixed = _collect(docs, args.skip or None)
    if args.by_subject:
        _print_threshold_table()
        _report_by_subject(by_subject)
        return

    print('置信度分布分析（白 / 深灰 / 中灰 / 浅灰 / 黑）')
    _print_threshold_table()
    print('  说明: 语文=基准 | 数学白门槛-2 | 英语白门槛+2 | 合计行按每题所属学科阈值统计')

    for mode in ('layout', 'understanding', 'grading'):
        _report_overall(mode, mixed[mode])

    _report_by_subject(by_subject)
    print('\n修改阈值后请重新执行:')
    print('  python -m app_chat.homework_grading.pass1_confidence_fields_backfill --docs-dir docs --render-only')


if __name__ == '__main__':
    main()
