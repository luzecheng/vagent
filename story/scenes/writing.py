"""写字: the hero kneels over a sheet of paper; lines of writing appear stroke by stroke."""
from __future__ import annotations

from .. import hero as H
from ..stage import ramp
from . import _props

TITLE = "写字"
MIN_S = 3.5


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return {"x": st.hx, "pose": H.blend(H.pose("stand"), H.pose("write"), ramp(p, 0.0, 0.2)), "light": 0.55,
            "lamp": "ground"}


def draw(cr, st, p, d, a, params):
    _props.paper(cr, st.hx + 130 * st.s, st.horizon, st.s, a=a, written=ramp(p, 0.2, 0.95))
