"""螺旋上升: a line circles upward, each turn higher than the last (pain + reflection = progress, evolving).

params
  turns    how many turns (default 4)
  labels   optional words placed along the climb, bottom to top, e.g. ["痛苦", "反思", "进步"]
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, WHITE, glow_dot, line, partial, ramp, text

TITLE = "螺旋上升"
MIN_S = 3.5


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return {"x": st.hx * (0.75 if not st.portrait else 0.9), "pose": H.pose("look_up"), "light": 0.6}


def _helix(st, turns):
    cx = st.W * (0.64 if not st.portrait else 0.58)
    bottom, top = st.horizon - 60 * st.u, st.H * (0.12 if not st.portrait else 0.18)
    r = min(st.W * 0.16, 190 * st.u)
    pts = []
    for i in range(int(turns * 60) + 1):
        th = i / 60 * 2 * math.pi
        k = i / (turns * 60)
        rr = r * (1 - 0.35 * k)                    # narrows as it climbs
        pts.append((cx + rr * math.cos(th), bottom - (bottom - top) * k + rr * 0.28 * math.sin(th), math.sin(th)))
    return pts


def draw(cr, st, p, d, a, params):
    turns = float(params.get("turns", 4))
    pts = _helix(st, turns)
    k = ramp(p, 0.05, 0.9)
    n = max(2, int(len(pts) * k))
    for i in range(1, n):                           # the back of each turn is dimmer: depth
        x0, y0, z0 = pts[i - 1]
        x1, y1, _ = pts[i]
        line(cr, [(x0, y0), (x1, y1)], 3 * st.u, GOLD, a=a * (0.35 if z0 < 0 else 1.0), glow=z0 >= 0)
    tip = pts[n - 1]
    glow_dot(cr, tip[0], tip[1], 6 * st.u, GOLD, a=a * (1 - ramp(p, 0.9, 1.0) * 0.5), rings=8)
    labels = params.get("labels", [])
    for j, word in enumerate(labels):
        at = (j + 0.5) / len(labels)
        q = pts[min(len(pts) - 1, int(at * (len(pts) - 1)))]
        text(cr, word, 40 * st.u, q[0] + 260 * st.u * (1 if not st.portrait else 0.7), q[1], WHITE,
             a=a * ramp(p, 0.05 + 0.85 * at, 0.15 + 0.85 * at))
