"""同伴淡出: a row of companions beside the hero fade out one by one, until the hero stands alone.

params
  count   how many companions (default 4)
"""
from __future__ import annotations

from .. import hero as H
from ..stage import WHITE, glow_dot, ramp
from . import _props

TITLE = "同伴淡出"
MIN_S = 3.0


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 2.0}


def hero(st, p, d, params):
    return {"x": st.hx, "pose": H.blend(H.pose("stand"), H.pose("kneel"), 0.15 * ramp(p, 0.6, 1.0)), "light": 0.4}


def draw(cr, st, p, d, a, params):
    n = int(params.get("count", 4))
    gap = (st.W - st.hx - 80 * st.s) / (n + 0.5)
    for i in range(n):
        x = st.hx + 110 * st.s + i * gap * 0.9
        start = 0.12 + 0.7 * i / n
        k = ramp(p, start, start + 0.16)
        _props.person(cr, x, st.horizon, st.s * 0.95, a=a * 0.55 * (1 - k), facing=-1 if i % 2 else 1)
        if 0 < k < 1:                   # each one leaves as a few rising specks of light
            for j in range(5):
                glow_dot(cr, x + (j - 2) * 12 * st.s, st.horizon - (120 + 140 * k + 20 * j) * st.s, 2.4 * st.s, WHITE,
                         a=a * (1 - k) * 0.8, rings=3)
