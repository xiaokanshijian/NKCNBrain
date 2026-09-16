import os
from typing import Any, Callable, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app_chat.homework_grading.confidence_zones import (
    combined_recognition_understanding_confidence,
    confidence_box_bgr,
    confidence_dot_bgr,
    normalize_subject,
)
from app_chat.homework_grading.utils import normalize_position, safe_json_load


_UNICODE_FONT_CANDIDATES = [
    r'C:\Windows\Fonts\seguisym.ttf',
    r'C:\Windows\Fonts\arial.ttf',
    r'C:\Windows\Fonts\DejaVuSans.ttf',
]
_CJK_FONT_CANDIDATES = [
    r'C:\Windows\Fonts\msyh.ttc',
    r'C:\Windows\Fonts\simhei.ttf',
    r'C:\Windows\Fonts\simsun.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
]

_COLOR = {
    'correct': (0, 200, 0),
    'wrong': (0, 0, 220),
    'partial': (0, 140, 255),
    'unanswered': (130, 130, 130),
    'uncertain': (220, 80, 0),
}
_ALPHA = 0.18


def _get_unicode_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _UNICODE_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _get_cjk_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _CJK_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _denorm(value: Any, dim: int) -> int:
    try:
        return int(float(value) / 1000.0 * dim)
    except (TypeError, ValueError):
        return 0


def _draw_check(img, cx: int, cy: int, r: int, color, thick: int) -> None:
    cv2.line(img, (cx - r, cy), (cx - r // 3, cy + r), color, thick, cv2.LINE_AA)
    cv2.line(img, (cx - r // 3, cy + r), (cx + r, cy - r), color, thick, cv2.LINE_AA)


def _draw_cross(img, cx: int, cy: int, r: int, color, thick: int) -> None:
    cv2.line(img, (cx - r, cy - r), (cx + r, cy + r), color, thick, cv2.LINE_AA)
    cv2.line(img, (cx + r, cy - r), (cx - r, cy + r), color, thick, cv2.LINE_AA)


def _draw_partial(img, cx: int, cy: int, r: int, color, thick: int) -> None:
    _draw_check(img, cx, cy, r, color, thick)
    cv2.line(img, (cx, cy - r // 2), (cx + r, cy + r // 2), color, thick, cv2.LINE_AA)


def _draw_question(img, cx: int, cy: int, r: int, color, thick: int) -> None:
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = _get_unicode_font(max(18, r * 2))
    bbox = draw.textbbox((0, 0), '?', font=font)
    rgb = (int(color[2]), int(color[1]), int(color[0]))
    draw.text((cx - (bbox[2] - bbox[0]) // 2, cy - (bbox[3] - bbox[1]) // 2), '?', font=font, fill=rgb)
    np.copyto(img, cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR))


def _draw_dashed_rect(img, x1: int, y1: int, x2: int, y2: int, color, thick: int) -> None:
    dash = max(15, (x2 - x1 + y2 - y1) // 20)
    for ax, ay, bx, by in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)):
        length = int(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5)
        if length <= 0:
            continue
        steps = max(length // (dash * 2), 1)
        for index in range(steps):
            t0 = (2 * index) / (2 * steps)
            t1 = (2 * index + 1) / (2 * steps)
            p0 = (int(ax + t0 * (bx - ax)), int(ay + t0 * (by - ay)))
            p1 = (int(ax + t1 * (bx - ax)), int(ay + t1 * (by - ay)))
            cv2.line(img, p0, p1, color, thick, cv2.LINE_AA)


def _draw_confidence_dot(img, cx: int, cy: int, r: int, color) -> None:
    cv2.circle(img, (cx, cy), r, color, -1, cv2.LINE_AA)
    if sum(color) > 500:
        cv2.circle(img, (cx, cy), r, (180, 180, 180), 1, cv2.LINE_AA)


def _draw_qid_label(img, x1: int, y1: int, page_num: Any, qid: Any, height: int) -> None:
    qid_label = f'p{page_num}:{qid}'
    pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    label_size = max(10, height // 100)
    label_font = _get_unicode_font(label_size)
    draw.text((x1 + 2, y1 + 2), qid_label, font=label_font, fill=(120, 120, 120))
    np.copyto(img, cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR))


def _load_page_image(clean_path: str, session_label: Optional[str]) -> tuple:
    img = cv2.imdecode(np.fromfile(clean_path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f'无法读取清洁页: {clean_path}')
    height, width = img.shape[:2]
    if session_label:
        banner_h = max(36, height // 35)
        cv2.rectangle(img, (0, 0), (width, banner_h), (40, 40, 40), -1)
        pil_img = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)
        font_size = max(18, height // 70)
        font = _get_cjk_font(font_size)
        bbox = draw.textbbox((0, 0), session_label, font=font)
        tx = 12
        ty = max(2, (banner_h - (bbox[3] - bbox[1])) // 2)
        draw.text((tx, ty), session_label, font=font, fill=(255, 255, 255))
        np.copyto(img, cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR))
    return img, height, width


def _iter_question_boxes(data: dict, width: int, height: int):
    for question in data.get('questions', []):
        position = normalize_position(question.get('position'))
        if len(position) != 4:
            continue
        x1 = max(0, _denorm(position[0], width))
        y1 = max(0, _denorm(position[1], height))
        x2 = min(width - 1, _denorm(position[2], width))
        y2 = min(height - 1, _denorm(position[3], height))
        if x2 <= x1 or y2 <= y1:
            continue
        yield question, x1, y1, x2, y2


def _draw_confidence_box(img, x1: int, y1: int, x2: int, y2: int, color) -> None:
    overlay = img.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
    cv2.addWeighted(overlay, _ALPHA, img, 1 - _ALPHA, 0, img)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 1)


def _save_page_image(img, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        raise ValueError('批改图编码失败')
    buf.tofile(out_path)


def _page_subject(data: dict, json_path: str) -> str:
    sub = str(data.get('subject') or '').strip().lower()
    if sub in ('math', 'chinese', 'english'):
        return sub
    return normalize_subject(os.path.basename(json_path).split('_', 1)[0])


def render_page_confidence(
    json_path: str,
    clean_path: str,
    out_path: str,
    confidence_fn: Callable[[dict], Any],
    mode: str,
    session_label: Optional[str] = None,
) -> None:
    """无损版面/理解：仅按置信度着色框，不绘批改符号。"""
    data = safe_json_load(json_path)
    subject = _page_subject(data, json_path)
    img, height, width = _load_page_image(clean_path, session_label)
    page_num = data.get('page', '?')
    for question, x1, y1, x2, y2 in _iter_question_boxes(data, width, height):
        color = confidence_box_bgr(confidence_fn(question), mode, subject=subject)  # type: ignore[arg-type]
        _draw_confidence_box(img, x1, y1, x2, y2, color)
        _draw_qid_label(img, x1, y1, page_num, question.get('id', '?'), height)
    _save_page_image(img, out_path)


def render_page_layout(json_path: str, clean_path: str, out_path: str,
                       session_label: Optional[str] = None) -> None:
    render_page_confidence(
        json_path, clean_path, out_path,
        confidence_fn=lambda q: q.get('layout_confidence'),
        mode='layout',
        session_label=session_label,
    )


def render_page_understanding(json_path: str, clean_path: str, out_path: str,
                              session_label: Optional[str] = None) -> None:
    render_page_confidence(
        json_path, clean_path, out_path,
        confidence_fn=combined_recognition_understanding_confidence,
        mode='understanding',
        session_label=session_label,
    )


def render_page(json_path: str, clean_path: str, out_path: str,
                session_label: Optional[str] = None) -> None:
    """三区批改：保留 verdict 框与符号，旁侧增加置信度小圆。"""
    data = safe_json_load(json_path)
    subject = _page_subject(data, json_path)
    img, height, width = _load_page_image(clean_path, session_label)
    sym_r = max(20, height // 80)
    thick = max(2, height // 600)
    page_num = data.get('page', '?')

    for question, x1, y1, x2, y2 in _iter_question_boxes(data, width, height):
        verdict = str(question.get('verdict') or 'uncertain')
        color = _COLOR.get(verdict, _COLOR['uncertain'])
        overlay = img.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, _ALPHA, img, 1 - _ALPHA, 0, img)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, 1)
        sx = min(x2 + sym_r + 4, width - sym_r - 4)
        sy = max(y1 + sym_r + 4, sym_r + 4)
        if verdict == 'correct':
            _draw_check(img, sx, sy, sym_r, color, thick)
        elif verdict == 'wrong':
            _draw_cross(img, sx, sy, sym_r, color, thick)
        elif verdict == 'partial':
            _draw_partial(img, sx, sy, sym_r, color, thick)
        elif verdict in ('unanswered', 'uncertain'):
            if verdict == 'uncertain':
                _draw_dashed_rect(img, x1, y1, x2, y2, color, thick)
            _draw_question(img, sx, sy, sym_r, color, thick)

        dot_r = sym_r
        dot_gap = max(6, sym_r // 5)
        # 批改符号中心 (sx,sy)，右缘约 sx+sym_r；小圆紧贴其右侧，等大且不重叠
        dot_cx = min(sx + sym_r + dot_gap + dot_r, width - dot_r - 2)
        dot_cy = sy
        dot_color = confidence_dot_bgr(question.get('grading_confidence'), mode='grading', subject=subject)
        _draw_confidence_dot(img, dot_cx, dot_cy, dot_r, dot_color)

        _draw_qid_label(img, x1, y1, page_num, question.get('id', '?'), height)

    _save_page_image(img, out_path)


def render_all_page_modes(
    json_path: str,
    clean_path: str,
    annotated_dir: str,
    layout_dir: str,
    understanding_dir: str,
    session_label: Optional[str] = None,
) -> dict:
    """为单页生成三区批改、无损版面、无损理解三张 PNG。"""
    return render_page_selected_modes(
        json_path,
        clean_path,
        annotated_dir,
        layout_dir,
        understanding_dir,
        modes=('grading', 'layout', 'understanding'),
        session_label=session_label,
    )


def render_page_selected_modes(
    json_path: str,
    clean_path: str,
    annotated_dir: str,
    layout_dir: str,
    understanding_dir: str,
    modes: tuple = ('grading', 'layout', 'understanding'),
    session_label: Optional[str] = None,
) -> dict:
    """按 modes 子集渲染 PNG。modes 取值：grading / layout / understanding。"""
    name = os.path.basename(clean_path)
    paths = {
        'grading': os.path.join(annotated_dir, name),
        'layout': os.path.join(layout_dir, name),
        'understanding': os.path.join(understanding_dir, name),
    }
    selected = set(modes or ())
    if 'grading' in selected:
        render_page(json_path, clean_path, paths['grading'], session_label=session_label)
    if 'layout' in selected:
        render_page_layout(json_path, clean_path, paths['layout'], session_label=session_label)
    if 'understanding' in selected:
        render_page_understanding(json_path, clean_path, paths['understanding'], session_label=session_label)
    return paths
