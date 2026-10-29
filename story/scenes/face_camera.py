"""转身: the hero stops, turns to face the camera, lamp alight (the closing question to the viewer)."""
from __future__ import annotations

from .. import hero as H
from ..stage import ramp

TITLE = "转身"
MIN_S = 3.0


def camera(params):
    return {"lift": 0.0, "zoom": params.get("zoom", 1.12), "ease": 2.5}


def speed(p, d, params):
    return 1.0 - ramp(p, 0.0, 0.2)


def hero(st, p, d, params):
    pose = H.blend(H.pose("walk", st.t), H.pose("lamp_hold"), ramp(p, 0.0, 0.2))
    front = dict(H.pose("front"))
    front.update(ua_f=40, la_f=86)     # keeps holding the lamp out while facing us
    return {"x": st.hx + (st.W * 0.5 - st.hx) * ramp(p, 0.0, 0.25), "pose": H.blend(pose, front, ramp(p, 0.2, 0.45)), "light": 0.7, "lamp_glow": 1.0}


def draw(cr, st, p, d, a, params):
    pass
