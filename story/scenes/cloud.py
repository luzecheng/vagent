"""乌云: blaming the outside — the hero points back at a dark cloud; the cloud drifts away, the stone stays."""
from __future__ import annotations

from .. import hero as H
from ..stage import GOLD, circle, ramp
from . import _props

TITLE = "乌云"
MIN_S = 3.0


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    k = ramp(p, 0.05, 0.25) * (1 - ramp(p, 0.75, 0.95))
    return {"x": st.hx, "pose": H.blend(H.pose("stand"), H.pose("point_back"), k), "light": 0.35}


def draw(cr, st, p, d, a, params):
    s = st.s
    gather = ramp(p, 0.0, 0.3)
    drift = ramp(p, 0.5, 1.0)
    cx = st.hx - 40 * s - drift * st.W * 0.35
    cy = st.horizon - 300 * s
    _props.cloud(cr, cx, cy, s * (0.8 + 0.2 * gather), a=a * gather * (1 - drift * 0.8), dark=1.0)
    sx = st.hx + 150 * s
    _props.stone(cr, sx, st.horizon, s, a=a)
    still_there = ramp(p, 0.75, 0.95)
    circle(cr, sx, st.horizon - 12 * s, 70 * s, 2 * s, GOLD, a=a * still_there * 0.6)
