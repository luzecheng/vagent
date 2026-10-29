"""插路牌: by the stone, the hero plants a signpost — a rule for next time — and it lights up."""
from __future__ import annotations

from .. import hero as H
from ..stage import ramp
from . import _props

TITLE = "插路牌"
MIN_S = 3.5


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    k = ramp(p, 0.0, 0.2) * (1 - ramp(p, 0.65, 0.85))
    return {"x": st.hx, "pose": H.blend(H.pose("stand"), H.pose("plant"), k), "light": 0.6, "lamp": "ground"}


def draw(cr, st, p, d, a, params):
    s = st.s
    _props.stone(cr, st.hx + 230 * s, st.horizon, s, a=a)
    _props.signpost(cr, st.hx + 105 * s, st.horizon, s, rise=ramp(p, 0.15, 0.55), glow=ramp(p, 0.6, 0.85), a=a)
