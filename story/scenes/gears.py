"""齿轮机器: a few gears mesh and turn (seeing life as a machine).

params
  labels   optional words, one per gear, e.g. ["目标", "人", "结果"]
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, WHITE, glow_dot, line, ramp, text

TITLE = "齿轮机器"
MIN_S = 3.5


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return {"x": st.hx * (0.7 if not st.portrait else 0.9), "pose": H.pose("look_up"), "light": 0.6}


def _gear(cr, x, y, r, teeth, angle, w, col, a):
    pts = []
    for i in range(teeth * 4 + 1):
        k = i / 4
        th = angle + 2 * math.pi * k / teeth
        rr = r * (1.0 if i % 4 in (1, 2) else 0.84)
        pts.append((x + rr * math.cos(th), y + rr * math.sin(th)))
    line(cr, pts, w, col, a=a)
    line(cr, [(x + r * 0.3 * math.cos(angle + t * math.pi / 10), y + r * 0.3 * math.sin(angle + t * math.pi / 10))
              for t in range(21)], w * 0.8, col, a=a)


def draw(cr, st, p, d, a, params):
    u = st.u
    base_x = st.W * (0.62 if not st.portrait else 0.55)
    base_y = st.H * (0.36 if not st.portrait else 0.34)
    big = min(150 * u, st.W * 0.14)
    gears = [(base_x, base_y, big, 12, 1), (base_x + big * 1.78, base_y - big * 0.55, big * 0.62, 8, -12 / 8),
             (base_x - big * 1.5, base_y + big * 0.8, big * 0.62, 8, -12 / 8)]
    spin = st.t * 0.6 * ramp(p, 0.1, 0.35)
    labels = params.get("labels", [])
    for i, (x, y, r, teeth, ratio) in enumerate(gears):
        appear = ramp(p, 0.05 + 0.1 * i, 0.25 + 0.1 * i)
        offset = math.pi / teeth if i else 0.0
        _gear(cr, x, y, r, teeth, spin * ratio + offset, 3 * u, GOLD if i == 0 else WHITE, a * appear)
        glow_dot(cr, x, y, 5 * u, GOLD, a=a * appear, rings=5)
        if i < len(labels):
            text(cr, labels[i], 36 * u, x, y + r + 40 * u, WHITE, a=a * ramp(p, 0.35 + 0.1 * i, 0.5 + 0.1 * i))
