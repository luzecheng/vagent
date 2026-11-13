"""反思之光: reflection as light.

params
  mode  "chest"  the hero bows; the light in the chest grows and spreads in soft rings
        "lamp"   the hero lifts the lamp; its light lays a bright stretch of road ahead
        "stone"  the hero comes back to the stone and, for the first time, sits down by it; a ring of light
                 rises round the stone and the chest light spreads
"""
from __future__ import annotations

import cairo

from .. import hero as H
from ..stage import GOLD, circle, ramp
from . import _props

TITLE = "反思之光"
MIN_S = 3.5
ROADSIDE = False     # mostly standing still: no lamps or benches behind the hero (scenery.py)


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.5}


def speed(p, d, params):
    return 1.0 - ramp(p, 0.1, 0.3) if params.get("mode") == "stone" else 0.0


def hero(st, p, d, params):
    mode = params.get("mode", "chest")
    if mode == "lamp":
        return {"x": st.hx, "pose": H.blend(H.pose("lamp_hold"), H.pose("lamp_up"), ramp(p, 0.05, 0.3)), "light": 0.6,
                "lamp_glow": 0.7 + 0.6 * ramp(p, 0.2, 0.5)}
    if mode == "stone":
        k = ramp(p, 0.2, 0.42)
        pose = H.blend(H.pose("walk", st.t), H.pose("stand"), ramp(p, 0.05, 0.2))
        pose = H.blend(pose, H.pose("sit"), k)
        return {"x": st.hx, "pose": pose, "light": 0.5 + 0.8 * ramp(p, 0.4, 0.9), "lamp": "ground"}
    return {"x": st.hx, "pose": H.blend(H.pose("stand"), H.pose("kneel"), ramp(p, 0.0, 0.3)),
            "light": 0.4 + 0.9 * ramp(p, 0.25, 0.8)}


def draw(cr, st, p, d, a, params):
    mode = params.get("mode", "chest")
    g, s = st.horizon, st.s
    if mode == "lamp":
        k = ramp(p, 0.25, 0.7)
        x0, x1 = st.hx - 40 * s, st.hx + (360 + 160 * k) * s
        grad = cairo.LinearGradient(x0, 0, x1, 0)
        grad.add_color_stop_rgba(0, GOLD[0], GOLD[1], GOLD[2], 0.0)
        grad.add_color_stop_rgba(0.25, GOLD[0], GOLD[1], GOLD[2], 0.45 * k * a)
        grad.add_color_stop_rgba(1, GOLD[0], GOLD[1], GOLD[2], 0.0)
        cr.set_source(grad)
        cr.rectangle(x0, g - 3 * s, x1 - x0, 7 * s)
        cr.fill()
    if mode == "stone":
        sx = st.hx + 120 * s
        _props.stone(cr, sx, g, s, a=a, glow=ramp(p, 0.45, 0.8))


def front(cr, st, p, d, a, params, joints):
    if not joints or params.get("mode", "chest") == "lamp":
        return
    start = 0.35 if params.get("mode") == "stone" else 0.3
    cx, cy = joints["chest"]
    for i in range(3):                   # rings leave the chest one after another and fade as they grow
        k = ramp(p, start + 0.15 * i, start + 0.15 * i + 0.45)
        if 0 < k < 1:
            circle(cr, cx, cy, (12 + 150 * k) * st.s, 2.2 * st.s, GOLD, a=a * (1 - k) * 0.8)
