"""抬头: the hero stops and looks up; the camera tilts up into the stars (leads into a thought)."""
from __future__ import annotations

from .. import hero as H
from ..stage import ramp

TITLE = "抬头"
MIN_S = 3.0


def camera(params):
    return {"lift": params.get("lift", 1.0), "zoom": 1.0, "ease": params.get("ease", 3.2)}


def speed(p, d, params):
    return 1.0 - ramp(p, 0.0, 0.25)


def hero(st, p, d, params):
    k = ramp(p, 0.1, 0.4)
    return {"x": st.hx, "pose": H.blend(H.pose("walk", st.t), H.pose("look_up"), k), "light": 0.6}


def draw(cr, st, p, d, a, params):
    pass
