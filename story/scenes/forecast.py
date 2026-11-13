"""预测线: a forecast drawn in the stars, then what really happened (a costly wrong call).

params
  label   big white text over the lines, e.g. "1982"
  stage   "predict"  the label appears and the forecast line dives down
          "split"    the real line climbs from the same start; the forecast line breaks and falls away
"""
from __future__ import annotations

import math

from ..stage import GOLD, WHITE, glow_dot, line, partial, ramp, text

TITLE = "预测线"
MIN_S = 2.5


def camera(params):
    return {"lift": 1.0, "zoom": 1.0, "ease": 1.5}


def hero(st, p, d, params):
    return {"x": st.hx, "pose": None}


def _geometry(st):
    x0, y0 = st.W * (0.16 if not st.portrait else 0.10), st.H * (0.52 if not st.portrait else 0.48)
    x1 = st.W * (0.84 if not st.portrait else 0.90)
    span = x1 - x0
    forecast = [(x0 + span * i / 40, y0 - 30 * st.u * math.sin(math.pi * min(1, i / 16)) +
                 (0 if i < 18 else (i - 18) ** 1.6 * 9 * st.u)) for i in range(41)]
    actual = [(x0 + span * i / 40, y0 - (i / 40) ** 1.3 * st.H * 0.30 + 10 * st.u * math.sin(i * 0.9)) for i in range(41)]
    return (x0, y0), forecast, actual


def draw(cr, st, p, d, a, params):
    split = params.get("stage", "predict") == "split"
    start, forecast, actual = _geometry(st)
    label = params.get("label", "")
    if label:
        text(cr, label, 150 * st.u, st.W / 2, st.H * (0.24 if not st.portrait else 0.26), WHITE,
             a=a * (1.0 if split else ramp(p, 0.0, 0.25)), weight=1)
    glow_dot(cr, *start, 6 * st.u, WHITE, a=a, rings=5)
    if not split:
        line(cr, partial(forecast, ramp(p, 0.2, 0.95)), 3 * st.u, WHITE, a=a * 0.9)
        return
    crack = ramp(p, 0.45, 0.6)
    fall = ramp(p, 0.55, 1.0)
    if crack < 1:
        line(cr, forecast, 3 * st.u, WHITE, a=a * 0.9)
    else:
        for i in range(0, 40, 4):        # the broken forecast: short pieces tumbling down and fading
            seg = forecast[i:i + 4]
            dy = fall * (120 + 30 * (i % 3)) * st.u
            rot = fall * (0.4 if i % 8 else -0.5)
            mx, my = seg[0]
            pts = [(mx + (x - mx) * math.cos(rot) - (y - my) * math.sin(rot),
                    my + dy + (x - mx) * math.sin(rot) + (y - my) * math.cos(rot)) for x, y in seg]
            line(cr, pts, 3 * st.u, WHITE, a=a * 0.9 * (1 - fall))
    line(cr, partial(actual, ramp(p, 0.0, 0.5)), 3.4 * st.u, GOLD, a=a)
