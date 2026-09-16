#!/usr/bin/env python
"""Export focused-review crop images (margin-expanded + scaled) for debugging.

Saves PNG crops similar to Gemini 拼音写词局部复核输入；默认使用比线更 tighter 的外扩，
便于调参预览。确认满意后再同步改 grader_pass1_review 或环境变量。

Usage (from 本地backend):
  python -m app_chat.homework_grading.export_focused_review_crops \\
      --homework-root "F:\\NKCNBrain\\djangoProject\\received_dir\\user_raw_file\\marklee_pigai\\continuous_image_dmt\\homework_7965e9e9cd0a"

Optional:
  --output-subdir focused_review_crops   # under homework_grading/
  --apply-limit                        # cap per page like production (default: export all)
  --margin-px 80                       # base margin each side (production default 220)
  --extra-pad-ratio 0.25               # pinyin extra pad = max(box)*ratio (production 0.75)
  --scale 3                            # upscale after crop (production default 3)
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from app_chat.homework_grading.grader_pass1_review import (  # noqa: E402
    _crop_question_image,
    _focused_visual_review_limit,
    _needs_focused_chinese_visual_review,
    focused_chinese_visual_review_enabled,
)
from app_chat.homework_grading.utils import (  # noqa: E402
    parse_page_num,
    safe_json_dump,
    safe_json_load,
    sorted_json_pages,
)

DEFAULT_HOMEWORK_ROOT = (
    r'F:\NKCNBrain\djangoProject\received_dir\user_raw_file\marklee_pigai'
    r'\continuous_image_dmt\homework_7965e9e9cd0a'
)

# Tighter than production (220px + 0.75*box) for preview; tune via CLI.
EXPORT_DEFAULT_MARGIN_PX = 80
EXPORT_DEFAULT_EXTRA_PAD_RATIO = 0.25
EXPORT_DEFAULT_SCALE = 3


def _safe_qid(qid: str) -> str:
    return re.sub(r'[^0-9A-Za-z_-]+', '_', qid or 'unknown')


def _find_page_image(grading_dir: str, page_num: int) -> str:
    for sub in ('clean', 'raw'):
        subdir = os.path.join(grading_dir, sub)
        if not os.path.isdir(subdir):
            continue
        for name in sorted(os.listdir(subdir)):
            if not name.lower().endswith('.png'):
                continue
            if parse_page_num(name) == page_num:
                path = os.path.join(subdir, name)
                if os.path.isfile(path):
                    return path
    return ''


def _save_crop_to(
    image_path: str,
    question: Dict[str, Any],
    dest_path: str,
) -> Dict[str, Any]:
    crop_path, cleanup_path = _crop_question_image(image_path, question)
    try:
        if crop_path == image_path or not os.path.isfile(crop_path):
            return {'saved': False, 'error': 'crop_failed'}
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(crop_path, dest_path)
        size = None
        try:
            from PIL import Image  # noqa: PLC0415

            with Image.open(dest_path) as img:
                size = {'width': img.width, 'height': img.height}
        except Exception:
            pass
        return {'saved': True, 'crop_size': size}
    finally:
        if cleanup_path and cleanup_path != image_path:
            try:
                os.remove(cleanup_path)
            except OSError:
                pass


def _configure_crop_env(margin_px: int, extra_pad_ratio: float, scale: int) -> None:
    os.environ['HOMEWORK_PASS1_FOCUSED_REVIEW_MARGIN_PX'] = str(margin_px)
    os.environ['HOMEWORK_PASS1_FOCUSED_REVIEW_EXTRA_PAD_RATIO'] = str(extra_pad_ratio)
    os.environ['HOMEWORK_PASS1_FOCUSED_REVIEW_SCALE'] = str(scale)


def export_focused_review_crops(
    homework_root: str,
    output_subdir: str = 'focused_review_crops',
    apply_limit: bool = False,
    margin_px: int = EXPORT_DEFAULT_MARGIN_PX,
    extra_pad_ratio: float = EXPORT_DEFAULT_EXTRA_PAD_RATIO,
    scale: int = EXPORT_DEFAULT_SCALE,
) -> Dict[str, Any]:
    _configure_crop_env(margin_px, extra_pad_ratio, scale)
    grading_dir = os.path.join(homework_root, 'homework_grading')
    pass1_dir = os.path.join(grading_dir, 'pass1_json')
    if not os.path.isdir(pass1_dir):
        raise FileNotFoundError(f'pass1_json not found: {pass1_dir}')

    out_dir = os.path.join(grading_dir, output_subdir)
    os.makedirs(out_dir, exist_ok=True)

    per_page_limit = _focused_visual_review_limit() if apply_limit else None
    items: List[Dict[str, Any]] = []
    stats = {
        'pages_scanned': 0,
        'pages_with_image': 0,
        'candidates': 0,
        'exported': 0,
        'skipped_no_image': 0,
        'skipped_crop_failed': 0,
    }

    for json_path in sorted_json_pages(pass1_dir):
        page_data = safe_json_load(json_path)
        page_num = int(page_data.get('page') or parse_page_num(os.path.basename(json_path)) or 0)
        stats['pages_scanned'] += 1

        image_path = _find_page_image(grading_dir, page_num)
        if not image_path:
            stats['skipped_no_image'] += 1
            continue
        stats['pages_with_image'] += 1

        candidates = [
            q for q in page_data.get('questions') or []
            if isinstance(q, dict) and _needs_focused_chinese_visual_review(q)
        ]
        if per_page_limit is not None:
            candidates = candidates[:per_page_limit]
        stats['candidates'] += len(candidates)

        for question in candidates:
            qid = str(question.get('id') or '').strip()
            filename = f'page{page_num}_{_safe_qid(qid)}.png'
            dest_path = os.path.join(out_dir, filename)
            result = _save_crop_to(image_path, question, dest_path)
            entry: Dict[str, Any] = {
                'page': page_num,
                'id': qid,
                'filename': filename,
                'source_image': image_path,
                'position': question.get('position'),
                'verdict': question.get('verdict'),
                'student_answer': question.get('student_answer'),
                'correct_answer': question.get('correct_answer'),
                'stem_excerpt': question.get('stem_excerpt'),
                'parent_stem_excerpt': question.get('parent_stem_excerpt'),
            }
            if result.get('saved'):
                entry['crop_size'] = result.get('crop_size')
                stats['exported'] += 1
            else:
                entry['error'] = result.get('error') or 'unknown'
                stats['skipped_crop_failed'] += 1
            items.append(entry)

    manifest = {
        'homework_root': os.path.abspath(homework_root),
        'output_dir': os.path.abspath(out_dir),
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'focused_review_enabled': focused_chinese_visual_review_enabled(),
        'apply_per_page_limit': apply_limit,
        'per_page_limit': per_page_limit,
        'margin_px': margin_px,
        'extra_pad_ratio': extra_pad_ratio,
        'scale': scale,
        'production_defaults': {
            'margin_px': 220,
            'extra_pad_ratio': 0.75,
            'scale': 3,
        },
        'stats': stats,
        'items': items,
    }
    manifest_path = os.path.join(out_dir, 'manifest.json')
    safe_json_dump(manifest_path, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description='Export focused-review crop images for homework grading.')
    parser.add_argument(
        '--homework-root',
        default=DEFAULT_HOMEWORK_ROOT,
        help='Homework directory (contains homework_grading/)',
    )
    parser.add_argument(
        '--output-subdir',
        default='focused_review_crops',
        help='Subdirectory under homework_grading/ for exported PNGs',
    )
    parser.add_argument(
        '--apply-limit',
        action='store_true',
        help='Apply the same per-page cap as production review (default: export all candidates)',
    )
    parser.add_argument(
        '--margin-px',
        type=int,
        default=EXPORT_DEFAULT_MARGIN_PX,
        help=f'Base pixel margin on each side (default {EXPORT_DEFAULT_MARGIN_PX}, production 220)',
    )
    parser.add_argument(
        '--extra-pad-ratio',
        type=float,
        default=EXPORT_DEFAULT_EXTRA_PAD_RATIO,
        help=(
            f'Extra pad for pinyin-write = max(box)*ratio per side '
            f'(default {EXPORT_DEFAULT_EXTRA_PAD_RATIO}, production 0.75)'
        ),
    )
    parser.add_argument(
        '--scale',
        type=int,
        default=EXPORT_DEFAULT_SCALE,
        help=f'Upscale factor after crop (default {EXPORT_DEFAULT_SCALE})',
    )
    args = parser.parse_args()

    homework_root = os.path.abspath(args.homework_root)
    if not os.path.isdir(homework_root):
        print(f'ERROR: homework root not found: {homework_root}', file=sys.stderr)
        return 1

    manifest = export_focused_review_crops(
        homework_root,
        output_subdir=args.output_subdir,
        apply_limit=args.apply_limit,
        margin_px=args.margin_px,
        extra_pad_ratio=args.extra_pad_ratio,
        scale=args.scale,
    )
    stats = manifest['stats']
    print(f"Done. Exported {stats['exported']} / {stats['candidates']} crops "
          f"({stats['pages_with_image']} pages with images).")
    print(f"Crop params: margin_px={manifest['margin_px']}, "
          f"extra_pad_ratio={manifest['extra_pad_ratio']}, scale={manifest['scale']}")
    print(f"Output: {manifest['output_dir']}")
    print(f"Manifest: {os.path.join(manifest['output_dir'], 'manifest.json')}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
