"""Panel detection for Guided view.

Recursive XY-cut on the gutter mask: split the page along full-width/height
gutter runs (rows first, then columns), alternating until no gutter remains.
Works well for typical manga/comic layouts with clean white or black gutters;
falls back to the whole page when the layout is borderless or noisy.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

FULL = [{"x": 0.0, "y": 0.0, "w": 1.0, "h": 1.0}]


def _segments(full: np.ndarray, min_gap: int):
    """Content segments separated by gutter runs of at least min_gap."""
    segs, start, last, gap = [], None, None, 0
    for i, v in enumerate(full.tolist()):
        if v:
            gap += 1
            continue
        if start is None:
            start = i
        elif gap >= min_gap:
            segs.append((start, last + 1))
            start = i
        last, gap = i, 0
    if start is not None:
        segs.append((start, last + 1))
    return segs


def _edge_connected(light: np.ndarray, max_iter: int = 4000) -> np.ndarray:
    """Gutter = background pixels reachable from the page edge (flood fill by
    iterative dilation). White areas *inside* a framed panel stay excluded."""
    seed = np.zeros_like(light)
    seed[0, :], seed[-1, :], seed[:, 0], seed[:, -1] = light[0, :], light[-1, :], light[:, 0], light[:, -1]
    cur = seed
    for _ in range(max_iter):
        nxt = cur.copy()
        nxt[1:, :] |= cur[:-1, :]
        nxt[:-1, :] |= cur[1:, :]
        nxt[:, 1:] |= cur[:, :-1]
        nxt[:, :-1] |= cur[:, 1:]
        nxt &= light
        if np.array_equal(nxt, cur):
            break
        cur = nxt
    return cur


def detect_panels(img: Image.Image, rtl: bool = False, max_panels: int = 16, tol: float = 0.97):
    w0, h0 = img.size
    if w0 < 50 or h0 < 50:
        return FULL
    g = img.convert("L")
    scale = 400 / w0 if w0 > 400 else 1.0
    g = g.resize((max(1, round(w0 * scale)), max(1, round(h0 * scale))), Image.BILINEAR)
    a = np.asarray(g)
    h, w = a.shape

    border = np.concatenate([a[0, :], a[-1, :], a[:, 0], a[:, -1]])
    bg = float(np.median(border))
    if bg >= 170:
        light = a >= max(215, bg - 20)
    elif bg <= 70:
        light = a <= min(45, bg + 20)
    else:
        return FULL
    mask = _edge_connected(light)

    min_gap = max(2, round(min(w, h) * 0.006))
    boxes: list[tuple[int, int, int, int]] = []

    def cut(x0, y0, x1, y1, depth=0):
        sub = mask[y0:y1, x0:x1]
        if sub.size == 0:
            return
        rf = sub.mean(axis=1) >= tol
        cf = sub.mean(axis=0) >= tol
        ys, xs = np.where(~rf)[0], np.where(~cf)[0]
        if len(ys) == 0 or len(xs) == 0:
            return
        ny0, ny1, nx0, nx1 = y0 + ys[0], y0 + ys[-1] + 1, x0 + xs[0], x0 + xs[-1] + 1
        if (ny0, ny1, nx0, nx1) != (y0, y1, x0, x1):
            return cut(nx0, ny0, nx1, ny1, depth)
        if depth > 14:
            boxes.append((x0, y0, x1, y1))
            return
        segs = _segments(rf, min_gap)
        if len(segs) > 1:
            for s, e in segs:
                cut(x0, y0 + s, x1, y0 + e, depth + 1)
            return
        segs = _segments(cf, min_gap)
        if len(segs) > 1:
            for s, e in (segs[::-1] if rtl else segs):
                cut(x0 + s, y0, x0 + e, y1, depth + 1)
            return
        boxes.append((x0, y0, x1, y1))

    cut(0, 0, w, h)

    area = w * h
    keep = [b for b in boxes
            if (b[2] - b[0]) * (b[3] - b[1]) >= 0.012 * area
            and min(b[2] - b[0], b[3] - b[1]) >= 0.06 * min(w, h)]
    if not keep or len(keep) > max_panels:
        return FULL
    pad = 0.004
    out = []
    for x0, y0, x1, y1 in keep:
        x, y = max(0.0, x0 / w - pad), max(0.0, y0 / h - pad)
        out.append({"x": round(float(x), 4), "y": round(float(y), 4),
                    "w": round(float(min(1.0, x1 / w + pad) - x), 4), "h": round(float(min(1.0, y1 / h + pad) - y), 4)})
    return out
