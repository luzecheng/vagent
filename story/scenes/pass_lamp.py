"""递灯: an older figure walks in from far away and puts a small lamp in the hero's hand.

After this shot the hero keeps the lamp (later shots can set "lamp": false or "ground").
"""
from __future__ import annotations

from .. import hero as H
from ..stage import ramp
from . import _props

TITLE = "递灯"
MIN_S = 4.0


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def _elder_x(st, p):
    return st.W + 80 * st.s - (st.W + 80 * st.s - (st.hx + 120 * st.s)) * ramp(p, 0.0, 0.55)


def hero(st, p, d, params):
    reach = ramp(p, 0.45, 0.62) * (1 - ramp(p, 0.75, 0.9))
    pose = H.blend(H.blend(H.pose("stand"), H.pose("receive"), reach), H.pose("lamp_hold"), ramp(p, 0.75, 0.92))
    return {"x": st.hx, "pose": pose, "light": 0.45, "lamp": p >= 0.7}


def draw(cr, st, p, d, a, params):
    pass


def front(cr, st, p, d, a, params, joints):
    x = _elder_x(st, p)
    walking = p < 0.55
    pose = "walk" if walking else "receive"
    leave = ramp(p, 0.78, 1.0)
    j = _props.person(cr, x, st.horizon, st.s * 0.95, a=a * 0.6 * (1 - leave), pose_name=pose, facing=-1, t=st.t)
    if j and p < 0.7:
        from ..hero import lamp
        hand = j["arm_f"][-1]
        if joints and p > 0.55:          # the lamp slides from the elder's hand to the hero's
            k = ramp(p, 0.55, 0.7)
            hand = (hand[0] + (joints["arm_f"][-1][0] - hand[0]) * k, hand[1] + (joints["arm_f"][-1][1] - hand[1]) * k)
        lamp(cr, hand, st.s, glow=0.6 + 0.4 * ramp(p, 0.4, 0.7), alpha=a)
