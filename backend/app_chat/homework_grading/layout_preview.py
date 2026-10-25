# -*- coding: utf-8 -*-
"""批改标注图的缩略预览（.preview_w{width}_{stem}.jpg）。"""
from __future__ import annotations

import os
from typing import Iterable, Sequence, Tuple

# 与 views_continuous_image._CI_LAYOUT_PREVIEW_WIDTHS 保持一致
DEFAULT_PREVIEW_WIDTHS: Tuple[int, ...] = (800, 1200, 1600, 2000)


def preview_path(abs_path: str, max_w: int) -> str:
    parent = os.path.dirname(abs_path)
    stem = os.path.splitext(os.path.basename(abs_path))[0]
    return os.path.join(parent, f'.preview_w{max_w}_{stem}.jpg')


def invalidate_previews(src_path: str) -> None:
    """删掉同页全部 .preview_w*.jpg。"""
    parent = os.path.dirname(src_path)
    stem = os.path.splitext(os.path.basename(src_path))[0]
    if not parent or not stem or not os.path.isdir(parent):
        return
    prefix = '.preview_w'
    suffix = f'_{stem}.jpg'
    try:
        for name in os.listdir(parent):
            if name.startswith(prefix) and name.endswith(suffix):
                try:
                    os.remove(os.path.join(parent, name))
                except OSError:
                    pass
    except OSError:
        pass


def ensure_preview(abs_path: str, max_w: int, *, force: bool = False) -> Tuple[str, str]:
    """生成/复用预览 JPEG；失败则回退原图路径。返回 (serve_path, mime)。"""
    import mimetypes

    preview = preview_path(abs_path, max_w)
    try:
        src_stat = os.stat(abs_path)
        if (not force) and os.path.isfile(preview):
            prv_stat = os.stat(preview)
            if prv_stat.st_mtime >= src_stat.st_mtime and prv_stat.st_size > 0:
                return preview, 'image/jpeg'
        from PIL import Image
        with Image.open(abs_path) as img:
            img = img.convert('RGB') if img.mode not in ('RGB', 'L') else img
            if img.mode == 'L':
                img = img.convert('RGB')
            w, h = img.size
            if w > max_w:
                new_h = max(1, int(round(h * (max_w / float(w)))))
                try:
                    resample = Image.Resampling.LANCZOS
                except AttributeError:
                    resample = Image.LANCZOS
                img = img.resize((max_w, new_h), resample)
            os.makedirs(os.path.dirname(preview) or '.', exist_ok=True)
            img.save(preview, format='JPEG', quality=82, optimize=True)
        return preview, 'image/jpeg'
    except Exception as exc:
        print(f'[layout_preview] 预览生成失败，回退原图: {abs_path} w={max_w} err={exc}', flush=True)
        mime_type, _ = mimetypes.guess_type(abs_path)
        return abs_path, (mime_type or 'application/octet-stream')


def refresh_previews(
    src_path: str,
    widths: Sequence[int] | Iterable[int] | None = None,
) -> None:
    """PNG 重画后：删旧预览并立刻重压常用宽度（默认含前端用的 1600）。"""
    if not src_path or not os.path.isfile(src_path):
        return
    invalidate_previews(src_path)
    for w in (widths or DEFAULT_PREVIEW_WIDTHS):
        try:
            ww = int(w)
        except (TypeError, ValueError):
            continue
        if ww <= 0:
            continue
        ensure_preview(src_path, ww, force=True)
