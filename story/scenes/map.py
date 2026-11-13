"""导航: a map in the sky; a gold route draws itself along the streets and a light moves along it ("跟着导航").
With `off` the navigation switches off halfway: the route and the destination fade, the streets dim, and the
light stops at a junction, blinking ("导航一关，下个路口往哪走？").  The hero looks up at it.

params
  off   true: the route disappears partway
"""
from __future__ import annotations

import math

from ..stage import GOLD, WHITE, circle, glow_dot, line, partial, ramp
from . import _objects as O

TITLE = "导航"
MIN_S = 4.0
ROWS = (0.22, 0.52, 0.80)
COLS = (0.14, 0.40, 0.64, 0.88)
ROUTE = [(0.14, 0.80), (0.40, 0.80), (0.40, 0.52), (0.64, 0.52), (0.64, 0.22), (0.88, 0.22)]


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return O.hero_looking(st, p)


def layout(cr, st, params):
    cx, cy, max_w, max_h = O.region(st, aspect=1.5)
    w = min(max_w, max_h * 1.5)
    h = w / 1.5
    box = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    return {"box": box, "texts": []}


def _at(pts, frac):
    """The point `frac` (0..1) of the way along a polyline."""
    part = partial(pts, frac)
    return part[-1]


def draw(cr, st, p, d, a, params):
    L, u = layout(cr, st, params), st.u
    x0, y0, x1, y1 = L["box"]
    w, h = x1 - x0, y1 - y0
    pt = lambda fx, fy: (x0 + fx * w, y0 + fy * h)
    appear = ramp(p, 0.0, 0.2)
    off = ramp(p, 0.50, 0.62) if params.get("off") else 0.0
    line(cr, partial(O.rrect(x0, y0, x1, y1, 18 * u), appear), 3 * u, WHITE, a=a * (1 - 0.4 * off))
    streets = a * ramp(p, 0.08, 0.25) * (0.45 - 0.25 * off)
    for fy in ROWS:
        line(cr, [pt(0.04, fy + 0.02 * math.sin(fy * 9)), pt(0.96, fy - 0.02 * math.sin(fy * 7))], 2 * u, WHITE,
             a=streets, glow=False)
    for fx in COLS:
        line(cr, [pt(fx, 0.06), pt(fx + 0.01, 0.94)], 2 * u, WHITE, a=streets, glow=False)
    route = [pt(*q) for q in ROUTE]
    drawn = ramp(p, 0.15, 0.35)
    line(cr, partial(route, drawn), 6 * u, GOLD, a=a * (1 - off))
    ex, ey = route[-1]                                   # the destination pin
    pin = a * ramp(p, 0.3, 0.4) * (1 - off)
    circle(cr, ex, ey - 34 * u, 16 * u, 3.4 * u, GOLD, a=pin)
    line(cr, [(ex - 14 * u, ey - 26 * u), (ex, ey), (ex + 14 * u, ey - 26 * u)], 3.4 * u, GOLD, a=pin)
    stop = 0.40 if params.get("off") else 1.0            # how far the light gets: to the second junction when off
    move = ramp(p, 0.30, 0.90 if not params.get("off") else 0.50) * stop
    dx, dy = _at(route, move) if move > 0 else route[0]
    blink = 0.5 + 0.5 * math.sin(st.t * 6) if off > 0 else 1.0
    glow_dot(cr, dx, dy, 8 * u, WHITE if off > 0 else GOLD, a=a * ramp(p, 0.12, 0.3) * blink, rings=8)
