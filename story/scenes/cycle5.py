"""五步循环: five points of light in a ring light up one by one and join (goals → problems → diagnosis → design
→ doing it), drawn in the sky while the hero looks up at it.

params
  labels   the five steps (default 目标 问题 诊断 设计 执行)
  loops    how many times the light runs round the ring after it is complete (default 1)
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, WHITE, circle, glow_dot, line, partial, ramp, text

TITLE = "五步循环"
MIN_S = 5.0
DEFAULT = ["目标", "问题", "诊断", "设计", "执行"]


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return {"x": st.hx * (0.7 if not st.portrait else 0.9), "pose": H.pose("look_up"), "light": 0.6}


def draw(cr, st, p, d, a, params):
    labels = params.get("labels", DEFAULT)
    n = len(labels)
    cx = st.W * (0.62 if not st.portrait else 0.5)
    cy = st.H * (0.36 if not st.portrait else 0.34)
    r = min(st.H * 0.22, st.W * 0.3)
    pts = [(cx + r * math.sin(2 * math.pi * i / n), cy - r * math.cos(2 * math.pi * i / n)) for i in range(n)]
    build = 0.75
    for i, (x, y) in enumerate(pts):
        on = ramp(p, build * i / n, build * i / n + 0.08)
        circle(cr, x, y, 16 * st.u, 2 * st.u, WHITE, a=a * 0.35)
        glow_dot(cr, x, y, 9 * st.u, GOLD, a=a * on, rings=8)
        dx, dy = (x - cx) / r, (y - cy) / r
        text(cr, labels[i], 38 * st.u, x + dx * 70 * st.u, y + dy * 52 * st.u, WHITE, a=a * on)
        if i > 0 or p > build:
            j = (i + 1) % n
            seg_start = build * (i + 0.5) / n if i < n - 1 else build
            arc = _arc(cx, cy, r, i, j, n)
            line(cr, partial(arc, ramp(p, seg_start, seg_start + 0.6 / n)), 2.4 * st.u, GOLD, a=a * 0.8)
    loops = float(params.get("loops", 1))
    if p > build:                               # a bright point runs round the finished ring
        k = (ramp(p, build, 1.0) * loops) % 1.0
        ang = 2 * math.pi * k
        glow_dot(cr, cx + r * math.sin(ang), cy - r * math.cos(ang), 6 * st.u, GOLD, a=a, rings=10, spread=0.9)


def _arc(cx, cy, r, i, j, n):
    a0 = 2 * math.pi * i / n + 0.22
    a1 = 2 * math.pi * (i + 1) / n - 0.22
    return [(cx + r * math.sin(a0 + (a1 - a0) * k / 20), cy - r * math.cos(a0 + (a1 - a0) * k / 20)) for k in range(21)]
