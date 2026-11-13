"""撞墙 / 断崖: the road ahead is blocked — a wall rises, or the ground breaks off into a cliff — and the hero
stops (pain, failure, a problem).

params
  kind   "wall" (default) or "cliff"
"""
from __future__ import annotations

from .. import hero as H
from ..stage import ramp, line

TITLE = "撞墙/断崖"
MIN_S = 3.0
ROADSIDE = False     # the hero stops at the wall: a bench there would lean on it (scenery.py)


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def speed(p, d, params):
    return 1.0 - ramp(p, 0.2, 0.45)


def hero(st, p, d, params):
    pose = H.blend(H.pose("walk", st.t), H.pose("stand"), ramp(p, 0.3, 0.5))
    pose = H.blend(pose, H.pose("kneel"), 0.45 * ramp(p, 0.6, 0.85))
    return {"x": st.hx, "pose": pose, "light": 0.5 - 0.3 * ramp(p, 0.5, 0.8)}


def draw(cr, st, p, d, a, params):
    g, s, u = st.horizon, st.s, st.u
    x = st.hx + 150 * s
    if params.get("kind", "wall") == "cliff":
        k = ramp(p, 0.15, 0.5)
        cr.set_source_rgba(0.03, 0.04, 0.08, a * k)
        cr.rectangle(x, g - 1, st.W, st.H)
        cr.fill()
        edge = [(x, g), (x - 6 * s, g + 40 * s), (x + 4 * s, g + 90 * s), (x - 10 * s, g + 160 * s)]
        line(cr, edge, 3 * s, a=a * k)
        return
    rise = ramp(p, 0.1, 0.45)
    h = 330 * s * rise
    rows = 6
    for r in range(rows):
        y0 = g - h * r / rows
        y1 = g - h * (r + 1) / rows
        line(cr, [(x, y1), (x + 120 * s, y1)], 2.4 * u, a=a * 0.8)
        mid = x + (40 if r % 2 else 80) * s
        line(cr, [(mid, y0), (mid, y1)], 2 * u, a=a * 0.5, glow=False)
    line(cr, [(x, g), (x, g - h), (x + 120 * s, g - h), (x + 120 * s, g)], 3.4 * u, a=a)
