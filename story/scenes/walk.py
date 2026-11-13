"""夜行: the hero walks through the mountains at night (opening, bridges).

params
  stop       true: slow down and stand still (a pause in the journey)
  gap        true: a missing piece opens in the road ahead, like a lost step (implies stop)
  stone      true: the stone sits ahead; the hero walks past it on the near side
  path       true: a straight glowing road draws itself out toward the far mountains
  pull_back  true: the camera pulls back at the end
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, glow_dot, line, partial, ramp
from . import _props

TITLE = "夜行"
MIN_S = 2.5


def camera(params):
    return {"lift": 0.0, "zoom": 0.84 if params.get("pull_back") else 1.0, "ease": 4.0 if params.get("pull_back") else 1.2}


def _stopping(params):
    return params.get("stop") or params.get("gap")


def speed(p, d, params):
    return 1.0 - ramp(p, 0.15, 0.45) if _stopping(params) else 1.0


def hero(st, p, d, params):
    t = p * d
    walking = H.pose("walk", st.t)
    if _stopping(params):
        k = ramp(p, 0.2, 0.5)
        return {"x": st.hx, "pose": H.blend(walking, H.pose("stand"), k), "light": 0.5}
    return {"x": st.hx, "pose": walking, "light": 0.55}


def draw(cr, st, p, d, a, params):
    g, s = st.horizon, st.s
    if params.get("gap"):
        k = ramp(p, 0.45, 0.85)
        x0, x1 = st.hx + 120 * s, st.hx + 230 * s
        cr.set_source_rgba(0.04, 0.05, 0.09, 0.95 * a * k)
        cr.rectangle(x0, g - 1, x1 - x0, 46 * s * k)
        cr.fill()
        line(cr, [(x0, g), (x0, g + 46 * s * k), (x1, g + 46 * s * k), (x1, g)], 2.4 * s, a=a * k)
        dash = [(x0 + 10 * s, g - 30 * s), (x1 - 10 * s, g - 30 * s), (x1 - 10 * s, g - 4 * s), (x0 + 10 * s, g - 4 * s),
                (x0 + 10 * s, g - 30 * s)]
        line(cr, dash, 1.6 * s, GOLD, a=a * k * (0.35 + 0.25 * math.sin(st.t * 3)), glow=False)
    if params.get("stone"):
        sx = st.hx + 260 * s - st.local
        _props.stone(cr, sx, g, s, a=a)
    if params.get("path"):
        k = ramp(p, 0.25, 0.85)
        far = (st.W * 0.82, g - 6 * st.u)
        pts = [(st.hx + 40 * s + (far[0] - st.hx - 40 * s) * i / 40, g + 3 * s - (g + 3 * s - far[1]) * (i / 40) ** 1.4)
               for i in range(41)]
        line(cr, partial(pts, k), 3.2 * s, GOLD, a=a * 0.9)
        tip = partial(pts, k)[-1]
        glow_dot(cr, *tip, 4 * s, GOLD, a=a * k * (1 - ramp(p, 0.85, 1.0)))
