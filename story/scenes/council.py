"""多人对坐: several people sit in a ring; a light over each head grows to a different size
(believability weighting, idea meritocracy).  The hero sits nearest the camera.

params
  weights  how big each person's light grows, 0..1, hero first (default [0.6, 1.0, 0.35, 0.8, 0.5])
  link     true: thin lines join each light to the middle, thicker for bigger lights (weighing the views)
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, glow_dot, line, ramp
from . import _props

TITLE = "多人对坐"
MIN_S = 4.0


def camera(params):
    return {"lift": -0.22, "zoom": 1.0, "ease": 1.4}


def _seats(st, n):
    room = st.H * (0.82 if not st.portrait else 0.72) - st.horizon
    cx, cy = st.W * 0.5, st.horizon + room * 0.45
    rx, ry = min(st.W * 0.28, 420 * st.u), room * 0.28
    return [(cx + rx * math.sin(2 * math.pi * i / n), cy + ry * math.cos(2 * math.pi * i / n)) for i in range(n)], (cx, cy)


def hero(st, p, d, params):
    weights = params.get("weights", [0.6, 1.0, 0.35, 0.8, 0.5])
    x, y = _seats(st, len(weights))[0][0]
    return {"x": x, "y": y, "pose": H.pose("sit"), "light": 0.5, "scale": 0.75, "lamp": "ground"}


def draw(cr, st, p, d, a, params):
    weights = params.get("weights", [0.6, 1.0, 0.35, 0.8, 0.5])
    seats, (cx, cy) = _seats(st, len(weights))
    s = st.s * 0.75
    order = sorted(range(1, len(seats)), key=lambda i: seats[i][1])   # far ones first
    for i in order:
        x, y = seats[i]
        _props.person(cr, x, y, s * (0.85 + 0.15 * (y - cy) / max(1, cy)), a=a * 0.65, pose_name="sit",
                      facing=1 if x < cx else -1)
    tops = []
    for i, (x, y) in enumerate(seats):
        grow = ramp(p, 0.2 + 0.08 * i, 0.55 + 0.08 * i)
        top = (x, y - 260 * s)
        tops.append(top)
        glow_dot(cr, *top, (4 + 14 * weights[i] * grow) * s, GOLD, a=a * (0.4 + 0.6 * grow), rings=8,
                 spread=0.4 + 0.4 * weights[i])
    if params.get("link"):
        hub = (cx, cy - 330 * s)
        k = ramp(p, 0.6, 0.9)
        for i, top in enumerate(tops):
            line(cr, [top, (top[0] + (hub[0] - top[0]) * k, top[1] + (hub[1] - top[1]) * k)], (1 + 3 * weights[i]) * st.u,
                 GOLD, a=a * 0.6 * k)
        glow_dot(cr, *hub, 8 * st.u, GOLD, a=a * k, rings=10)
