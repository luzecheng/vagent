"""镜子 / 水面倒影: the hero stands at still water and sees their reflection (knowing yourself, ego and
blind spots).

params
  differ   true: the reflection is not quite the same — it kneels with its head bowed while the hero stands
           proudly, showing what the hero does not see in themselves
"""
from __future__ import annotations

import math

import cairo

from .. import hero as H
from ..stage import GOLD, glow_dot, line, ramp

TITLE = "镜子倒影"
MIN_S = 3.5


def camera(params):
    return {"lift": -0.2, "zoom": 1.0, "ease": 1.4}


def hero(st, p, d, params):
    return {"x": st.W * 0.5, "pose": H.blend(H.pose("stand"), H.pose("kneel"), 0.35 * ramp(p, 0.1, 0.4)), "light": 0.55}


def draw(cr, st, p, d, a, params):
    g, u = st.horizon, st.u
    water = cairo.LinearGradient(0, g, 0, st.H)
    water.add_color_stop_rgba(0, 0.30, 0.38, 0.55, 0.45 * a)
    water.add_color_stop_rgba(1, 0.10, 0.12, 0.20, 0.2 * a)
    cr.set_source(water)
    cr.rectangle(0, g + 2 * u, st.W, st.H - g)
    cr.fill()
    for i in range(9):                              # slow ripples
        y = g + (14 + i * 22) * u
        x0 = st.W * (0.1 + 0.05 * math.sin(st.t * 0.6 + i))
        line(cr, [(x0, y), (x0 + st.W * (0.25 + 0.1 * (i % 3)), y)], 1.6 * u, a=a * 0.18, glow=False)
    pose = H.pose("kneel") if params.get("differ") else H.blend(H.pose("stand"), H.pose("kneel"), 0.35 * ramp(p, 0.1, 0.4))
    show = ramp(p, 0.15, 0.5)
    cr.save()                                        # the reflection: the hero mirrored below the waterline
    cr.translate(0, 2 * g)
    cr.scale(1, -1)
    j = H.draw(cr, st.W * 0.5, g, pose, st.s, light=0.0, alpha=a * show * 0.45)
    cr.restore()
    if params.get("differ"):
        cx, cy = j["chest"]
        glow_dot(cr, cx, 2 * g - cy, 6 * st.s, GOLD, a=a * show * (0.5 + 0.5 * math.sin(st.t * 2) ** 2), rings=10)
