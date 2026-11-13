"""问号: two question marks over the hero; the first cracks and falls apart, the second lights up gold
("Am I right?" gives way to "How do I know I'm right?")."""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, WHITE, line, partial, ramp

TITLE = "问号"
MIN_S = 3.5


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return {"x": st.hx, "pose": H.blend(H.pose("lamp_hold"), H.pose("look_up"), 0.5), "light": 0.5 + 0.4 * ramp(p, 0.6, 0.9)}


def _mark(cx, cy, size):
    arc = [(cx + size * 0.45 * math.cos(t), cy - size * 0.45 + size * 0.45 * math.sin(t))
           for t in [math.pi * (1.0 + 1.3 * i / 24) for i in range(25)]]
    return [arc + [(cx, cy + size * 0.2)], [(cx, cy + size * 0.55), (cx, cy + size * 0.6)]]


def draw(cr, st, p, d, a, params):
    size = 120 * st.u
    y = st.horizon - (st.H * 0.30 if not st.portrait else st.H * 0.22)
    x1 = st.W * (0.45 if not st.portrait else 0.32)
    x2 = st.W * (0.68 if not st.portrait else 0.70)
    appear = ramp(p, 0.0, 0.25)
    breaks = ramp(p, 0.35, 0.75)
    for k, poly in enumerate(_mark(x1, y, size)):
        if breaks <= 0:
            line(cr, partial(poly, appear), 4 * st.u, WHITE, a=a)
            continue
        for i in range(0, len(poly) - 1, 3):
            seg = poly[i:i + 4]
            dy = breaks ** 1.5 * (160 + 40 * (i % 2)) * st.u
            dx = breaks * (i - len(poly) / 2) * 3 * st.u
            line(cr, [(x + dx, yy + dy) for x, yy in seg], 4 * st.u, WHITE, a=a * (1 - breaks))
    second = ramp(p, 0.4, 0.75)
    for poly in _mark(x2, y, size * 1.1):
        line(cr, partial(poly, second), 4.4 * st.u, GOLD if p > 0.6 else WHITE, a=a)
