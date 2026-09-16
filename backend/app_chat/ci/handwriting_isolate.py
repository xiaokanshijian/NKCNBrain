# -*- coding: utf-8 -*-
"""
handwriting_isolate.py — 手写字迹提取：去除一切干扰，字迹无损保留
================================================================

9 步流水线：
  s1  灰度化
  s2  纸张区域检测 — 去除桌面/黑边/翻折角，只保留纸张内部
  s3  CLOSING 背景建模 + 减法归一化 — 消除光照不均与纸色差异
  s4  多策略并集提取墨迹掩码 — 宁多勿少
  s5  方向腐蚀分离笔画 vs 直线 — 竖直腐蚀杀横线，水平腐蚀杀竖线
  s6  形态学方向核检测横线 / 竖线
  s7  笔画保护擦除 — 只删「纯线段」像素，交叉处保留
  s8  连通域过滤去噪
  s9  白底合成（灰度 + 二值两版）

核心原则：字迹零损失。所有擦除操作都以笔画保护区为前提，
         宁可残留少量线段，绝不抹掉任何一个笔画像素。

依赖：pip install opencv-python-headless numpy

用法：
  python handwriting_isolate.py <输入图片> [输出目录] [--no-split] [--debug]

示例：
  python handwriting_isolate.py notes.jpg ./output
  python handwriting_isolate.py notes.jpg ./output --debug
  python handwriting_isolate.py single.jpg ./output --no-split
"""

import cv2
import numpy as np
import os, sys, argparse


# ===================== 调试辅助 =====================

class Debugger:
    """保存中间结果，--debug 时启用"""
    def __init__(self, d=None):
        self.d = d
        if d: os.makedirs(d, exist_ok=True)
    def save(self, name, img):
        if self.d: cv2.imwrite(os.path.join(self.d, name), img)


# ===================== s2: 纸张区域检测 =====================

def detect_paper(gray, erode_px=20):
    """
    检测图中最大亮色区域（纸张），排除桌面/黑边/翻折。
    erode_px: 从检测到的纸张边界向内收缩的像素数，
              避免纸边的阴影、翻折、锯齿被当成墨迹。
    """
    blurred = cv2.GaussianBlur(gray, (51, 51), 0)
    _, bw = cv2.threshold(blurred, 0, 255,
                          cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # 填充内部
    bw = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, np.ones((50, 50), np.uint8))

    n, labels, stats, _ = cv2.connectedComponentsWithStats(bw, 8)
    if n <= 1:
        return np.ones_like(gray, np.uint8) * 255

    largest = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1
    mask = np.zeros_like(gray, np.uint8)
    mask[labels == largest] = 255

    # 向内收缩，排除边缘伪影
    if erode_px > 0:
        mask = cv2.erode(mask, np.ones((erode_px, erode_px), np.uint8),
                         iterations=1)
    return mask


# ===================== s3: 背景归一化 =====================

def normalize_lighting(gray, paper, ksize=51):
    """
    CLOSING 背景建模 + 减法归一化。
    结果：均匀白底，墨迹保持原有灰度深浅。
    """
    bg = cv2.morphologyEx(
        gray, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (ksize, ksize)))
    diff = cv2.subtract(bg, gray)
    mx = max(int(diff.max()), 1)
    norm = 255 - (diff.astype(np.float64) / mx * 255).astype(np.uint8)
    norm[paper == 0] = 255
    return norm


# ===================== s4: 墨迹掩码 =====================

def extract_ink(gray):
    """多参数自适应二值化 + Otsu 取并集，最大化召回率。"""
    masks = []
    for bs, C in [(31, 12), (21, 10), (15, 8), (11, 6)]:
        masks.append(cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, bs, C))
    _, otsu = cv2.threshold(gray, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    masks.append(otsu)
    out = masks[0]
    for m in masks[1:]:
        out = cv2.bitwise_or(out, m)
    return out


# ===================== s5: 方向腐蚀 =====================

def direction_erode_restore(mask, direction, size=7, cross_dilate=3):
    """
    用方向腐蚀消除与该方向平行的细线结构，保留笔画。

    原理（以 direction='v' 消除横线为例）：
      - 横格线只有 1~2px 高 → 竖直腐蚀 size=7 后消失
      - 手写笔画纵向厚度 > 3px → 被腐蚀后仍残留 → 膨胀恢复
      - 恢复后再在正交方向小幅膨胀，覆盖交叉处

    direction: 'v'=竖直腐蚀（杀横线）  'h'=水平腐蚀（杀竖线）
    返回：只含笔画的保护掩码
    """
    if direction == 'v':
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, size))
        cross_k = cv2.getStructuringElement(cv2.MORPH_RECT, (cross_dilate, 1))
    else:
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (size, 1))
        cross_k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, cross_dilate))

    eroded = cv2.erode(mask, k, iterations=1)
    restored = cv2.dilate(eroded, k, iterations=1)
    restored = cv2.dilate(restored, cross_k, iterations=1)
    return restored


# ===================== s6: 检测直线 =====================

def detect_lines(bin_inv, direction, ratio=0.25, minlen=40):
    """长条形态学 OPEN 提取纯直线。'h'=水平  'v'=垂直"""
    h, w = bin_inv.shape
    if direction == 'h':
        ll = max(int(w * ratio), minlen)
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (ll, 1))
        ck = cv2.getStructuringElement(cv2.MORPH_RECT, (ll // 3, 1))
    else:
        ll = max(int(h * ratio), minlen)
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (1, ll))
        ck = cv2.getStructuringElement(cv2.MORPH_RECT, (1, ll // 3))
    lines = cv2.morphologyEx(bin_inv, cv2.MORPH_OPEN, k)
    lines = cv2.morphologyEx(lines, cv2.MORPH_CLOSE, ck)
    return lines


# ===================== s7: 笔画保护擦除 =====================

def safe_erase(ink, gray, line_mask, stroke_protect, dilate_r=2):
    """
    安全擦除线条：只删保护区外的线像素。
    dilate_r: 保护区膨胀半径。越小擦除越多，越大保护越多。
              默认 2，在「多删线」和「保字」之间取平衡。
    """
    if cv2.countNonZero(line_mask) == 0:
        return ink, gray
    pk = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,
                                    (dilate_r * 2 + 1, dilate_r * 2 + 1))
    protected = cv2.dilate(stroke_protect, pk, iterations=1)
    erasable = cv2.bitwise_and(line_mask, cv2.bitwise_not(protected))
    ink_out = ink.copy();  ink_out[erasable > 0] = 0
    gray_out = gray.copy(); gray_out[erasable > 0] = 255
    return ink_out, gray_out


# ===================== s8: 去噪 =====================

def remove_small(mask, min_area=10):
    """过滤面积 < min_area 的连通域"""
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    out = np.zeros_like(mask)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= min_area:
            out[labels == i] = 255
    return out


# ===================== s9: 合成 =====================

def compose_gray(gray_norm, ink):
    out = np.full_like(gray_norm, 255)
    out[ink > 0] = gray_norm[ink > 0]
    return out

def compose_binary(ink):
    return cv2.bitwise_not(ink)


# ===================== 完整流水线 =====================

def isolate(img_bgr, debug_dir=None):
    D = Debugger(debug_dir)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    D.save("s1_gray.png", gray)

    # s2: 纸张检测
    paper = detect_paper(gray, erode_px=20)
    gray_p = gray.copy(); gray_p[paper == 0] = 255
    D.save("s2_paper.png", paper)
    D.save("s2_gray_paper.png", gray_p)

    # s3: 归一化
    norm = normalize_lighting(gray_p, paper)
    D.save("s3_norm.png", norm)

    # s4: 墨迹
    ink = extract_ink(gray_p)
    ink[paper == 0] = 0
    D.save("s4_ink.png", ink)

    # s5: 方向腐蚀
    stroke_v = direction_erode_restore(ink, 'v', size=7, cross_dilate=3)
    stroke_h = direction_erode_restore(ink, 'h', size=7, cross_dilate=3)
    D.save("s5_stroke_v.png", stroke_v)
    D.save("s5_stroke_h.png", stroke_h)

    # s6: 检测线
    hl = detect_lines(ink, 'h', 0.25)
    vl = detect_lines(ink, 'v', 0.20)
    D.save("s6_hlines.png", hl)
    D.save("s6_vlines.png", vl)

    # s7: 安全擦除
    ink2, gray2 = safe_erase(ink, norm, hl, stroke_v, dilate_r=2)
    ink3, gray3 = safe_erase(ink2, gray2, vl, stroke_h, dilate_r=2)
    D.save("s7_ink.png", ink3)
    D.save("s7_gray.png", gray3)

    # s8: 去噪
    ink_final = remove_small(ink3, min_area=8)
    D.save("s8_ink_clean.png", ink_final)

    # s9: 合成
    fg = compose_gray(gray3, ink_final)
    fb = compose_binary(ink_final)
    D.save("s9_gray.png", fg)
    D.save("s9_binary.png", fb)

    return fg, fb, ink_final


# ===================== 分页 =====================

def split_pages(img, no_split=False):
    if no_split:
        return {"page": img}
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    x0, x1 = int(w * 0.3), int(w * 0.7)
    cm = np.mean(gray[:, x0:x1], axis=0)
    win = 20
    if len(cm) < win:
        return {"page": img}
    sm = np.convolve(cm, np.ones(win) / win, mode='valid')
    pk = int(np.argmax(sm)) + x0 + win // 2
    if abs(pk - w // 2) < w * 0.25:
        return {"left": img[:, :pk], "right": img[:, pk:]}
    return {"page": img}


# ===================== 主函数 =====================

def main():
    ap = argparse.ArgumentParser(
        description="手写字迹提取：去除干扰，字迹无损保留")
    ap.add_argument("input", help="输入图片路径")
    ap.add_argument("output", nargs="?", default="./isolated_output",
                    help="输出目录")
    ap.add_argument("--no-split", action="store_true",
                    help="禁用自动左右分页")
    ap.add_argument("--debug", action="store_true",
                    help="保存中间结果")
    args = ap.parse_args()

    img = cv2.imread(args.input)
    if img is None:
        print(f"[错误] 无法读取: {args.input}"); sys.exit(1)

    h, w = img.shape[:2]
    os.makedirs(args.output, exist_ok=True)
    print(f"[输入] {args.input}  ({w}x{h})")

    pages = split_pages(img, args.no_split)
    print(f"[分页] {list(pages.keys())}")

    results = []
    for pn, pg in pages.items():
        ph, pw = pg.shape[:2]
        print(f"\n--- [{pn}] ({pw}x{ph}) ---")
        dd = os.path.join(args.output, f"debug_{pn}") if args.debug else None
        fg, fb, _ = isolate(pg, dd)

        cv2.imwrite(os.path.join(args.output, f"{pn}_gray.png"), fg)
        cv2.imwrite(os.path.join(args.output, f"{pn}_binary.png"), fb)
        print(f"  → {pn}_gray.png   (灰度)")
        print(f"  → {pn}_binary.png (黑白)")
        if dd: print(f"  → debug_{pn}/")
        results.append((pn, fg, fb))

    if len(results) > 1:
        mh = max(g.shape[0] for _, g, _ in results)
        gs, bs = [], []
        for _, g, b in results:
            dh = mh - g.shape[0]
            if dh > 0:
                p = np.full((dh, g.shape[1]), 255, np.uint8)
                g, b = np.vstack([g, p]), np.vstack([b, p])
            gs.append(g); bs.append(b)
        mg, mb = np.hstack(gs), np.hstack(bs)
        cv2.imwrite(os.path.join(args.output, "merged_gray.png"), mg)
        cv2.imwrite(os.path.join(args.output, "merged_binary.png"), mb)
        print(f"\n  → merged_gray.png  ({mg.shape[1]}x{mg.shape[0]})")
        print(f"  → merged_binary.png")

    print(f"\n[完成] {args.output}/")

if __name__ == "__main__":
    main()
