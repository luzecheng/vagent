"""绕圈脚印: the road bends round and joins itself; footprints pile up lap on lap (going in circles).

params
  laps        how many laps of old footprints (default 3)
  light_old   true: the hero stands still and the old footprints light up gold, joining into one circle
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, line, partial, ramp
from . import _props

TITLE = "绕圈脚印"
MIN_S = 3.0


def camera(params):
    return {"lift": -0.28, "zoom": 1.0, "ease": 1.4}


def _ring(st, lap=0):
    room = st.H * (0.82 if not st.portrait else 0.72) - st.horizon   # ground visible above the subtitles
    cx, cy = st.W * 0.5, st.horizon + room * 0.5
    rx, ry = (st.W * (0.30 if not st.portrait else 0.36)) + lap * 14 * st.u, room * 0.30 + lap * 4 * st.u
    return cx, cy, rx, ry


def _point(st, theta, lap=0):
    cx, cy, rx, ry = _ring(st, lap)
    return cx + rx * math.cos(theta), cy + ry * math.sin(theta)


def hero(st, p, d, params):
    if params.get("light_old"):
        x, y = _point(st, math.pi * 0.5)
        return {"x": x, "y": y, "pose": H.pose("stand"), "light": 0.5 + 0.4 * ramp(p, 0.5, 1.0), "scale": 0.8}
    theta = math.pi * 0.5 - p * 2 * math.pi * 1.0   # one lap across the shot, walking to the right at the front
    x, y = _point(st, theta)
    facing = 1 if math.sin(theta) > 0 else -1
    return {"x": x, "y": y, "pose": H.pose("walk", st.t), "facing": facing, "light": 0.5, "scale": 0.8}


def draw(cr, st, p, d, a, params):
    laps = int(params.get("laps", 3))
    s = st.s * 0.8
    lit = params.get("light_old")
    for lap in range(laps):
        steps = 26
        pts = [_point(st, math.pi * 0.5 - 2 * math.pi * i / steps, lap) for i in range(steps)]
        glow = ramp(p, 0.1 + 0.18 * lap, 0.35 + 0.18 * lap) if lit else 0.0
        count = steps if lit else int(steps * min(1.0, 0.35 + 0.3 * lap + p * 0.6))
        _props.footprints(cr, pts, s, a=a * (0.55 + 0.15 * lap), glow=glow, count=count)
    ring = [_point(st, 2 * math.pi * i / 80, 1) for i in range(81)]
    if lit:
        line(cr, partial(ring, ramp(p, 0.55, 0.95)), 2.6 * st.u, GOLD, a=a * 0.85)
    else:
        line(cr, ring, 1.4 * st.u, a=a * 0.25, glow=False)
