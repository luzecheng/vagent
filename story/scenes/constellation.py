"""星座连线: scattered stars join into shapes (seeing the pattern in reality).

params
  figures   list of shapes drawn left to right, each from stars:
            "crack" (pain), "lamp" (reflection), "spiral" (progress), "+", "=", "?", or any short text
            shown as a star-traced label
  spiral_up true: the spiral climbs as it draws (each turn higher)
"""
from __future__ import annotations

import math

from ..stage import GOLD, WHITE, glow_dot, line, partial, ramp, text

TITLE = "星座连线"
MIN_S = 3.0


def camera(params):
    return {"lift": 1.0, "zoom": 1.0, "ease": 2.0}


def hero(st, p, d, params):
    return {"x": st.hx, "pose": None}


def _shape(name):
    """Polylines in a unit box (-1..1)."""
    if name == "crack":
        return [[(-0.15, -1), (0.2, -0.45), (-0.25, -0.05), (0.25, 0.4), (-0.05, 1)], [(0.2, -0.45), (0.6, -0.3)],
                [(-0.25, -0.05), (-0.6, 0.15)]]
    if name == "lamp":
        return [[(0, -1), (0, -0.65)], [(-0.45, -0.65), (0.45, -0.65), (0.45, 0.6), (-0.45, 0.6), (-0.45, -0.65)],
                [(-0.3, 0.6), (-0.3, 0.8), (0.3, 0.8), (0.3, 0.6)]]
    if name == "spiral":
        pts = []
        for i in range(90):
            k = i / 89
            ang = k * 3.2 * 2 * math.pi
            r = 0.25 + 0.6 * k
            pts.append((r * math.cos(ang), 0.95 - 1.9 * k + 0.25 * r * math.sin(ang)))
        return [pts]
    if name == "+":
        return [[(-0.5, 0), (0.5, 0)], [(0, -0.5), (0, 0.5)]]
    if name == "=":
        return [[(-0.5, -0.2), (0.5, -0.2)], [(-0.5, 0.2), (0.5, 0.2)]]
    if name == "?":
        pts = [(0.45 * math.cos(a), -0.45 + 0.45 * math.sin(a)) for a in [math.pi * (1.0 + 1.25 * i / 20) for i in range(21)]]
        return [pts + [(0, 0.25)], [(0, 0.62), (0, 0.66)]]
    return []


def draw(cr, st, p, d, a, params):
    figures = params.get("figures", ["crack", "+", "lamp", "=", "spiral"])
    n = len(figures)
    small_sign = lambda f: f in ("+", "=")
    slots = [1.2 if small_sign(f) else 2.2 for f in figures]          # widths in units of `size`
    size = min(st.W * 0.92 / sum(slots), 150 * st.u)
    cy = st.H * (0.42 if not st.portrait else 0.40)
    left = st.W / 2 - sum(slots) * size / 2
    for i, name in enumerate(figures):
        cx = left + (sum(slots[:i]) + slots[i] / 2) * size
        start, end = 0.05 + 0.75 * i / n, 0.05 + 0.75 * (i + 1) / n
        k = ramp(p, start, end)
        small = name in ("+", "=")
        col = GOLD if name == "spiral" else WHITE
        polys = _shape(name)
        if not polys:
            text(cr, name, size * 0.9, cx, cy, WHITE, a=a * k)
            continue
        scale = size * (0.6 if small else 1.0)
        for poly in polys:
            pts = [(cx + x * scale, cy + y * scale) for x, y in poly]
            line(cr, partial(pts, k), 2.4 * st.u, col, a=a * 0.85)
            step = max(1, len(pts) // 8)
            for j, q in enumerate(pts[::step] + [pts[-1]]):
                dot_k = ramp(p, start + (end - start) * j / (len(pts[::step]) + 1), end)
                glow_dot(cr, *q, 3.2 * st.u, col, a=a * dot_k, rings=4, spread=0.8)
