"""Shared by the object scenes (书 book, 屏幕 screen, 对话框 chat, 导航 map, 曲线图 chart): where a big glowing
object floats in the sky beside the hero, how the hero looks at it, and how words are sized to fit."""
from __future__ import annotations

import cairo

from .. import hero as H
from ..stage import ramp, text_width
from .compare import HEAD_TOP


HERO_REACH = 120   # how far the hero's arms reach to the side, in hero units


def hero_x(st):
    return st.hx * 0.78 if not st.portrait else st.hx * 0.8


def moon(st):
    """Centre and glow radius of the moon (drawn by the stage), which the object must not cover."""
    return (st.W * (0.84 if not st.portrait else 0.78), st.H * (0.13 if not st.portrait else 0.16), 136 * st.u)


def region(st, aspect=1.0):
    """(centre x, centre y, max width, max height) of the space for an object about `aspect` (width / height)
    in shape.  Always clear of the moon's glow and above the ground.  Landscape: to the right of the hero (clear
    of its arms).  Portrait: either to the right of the hero, or across the full width over the hero's head,
    whichever lets an object of this shape be drawn larger (wide things go overhead, tall things beside)."""
    mx, my, mr = moon(st)
    bottom = st.horizon - 70 * st.u
    beside_left = hero_x(st) + HERO_REACH * st.s + 30 * st.u
    if not st.portrait:
        right = min(mx - mr * 0.55, st.W - 40 * st.u)
        top = st.H * 0.08
        return (beside_left + right) / 2, (top + bottom) / 2, right - beside_left, bottom - top
    top = my + mr * 0.85
    beside = ((beside_left + st.W - 50 * st.u) / 2, (top + bottom) / 2, st.W - 50 * st.u - beside_left, bottom - top)
    over_bottom = st.horizon - HEAD_TOP * st.s - 40 * st.u
    overhead = (st.W / 2, (top + over_bottom) / 2, st.W * 0.88, over_bottom - top)

    def drawn_width(r):
        return min(r[2], r[3] * aspect)
    return max((beside, overhead), key=drawn_width)


def hero_looking(st, p):
    """The hero stands a little to the left and looks up at the object."""
    return {"x": hero_x(st), "pose": H.blend(H.pose("stand"), H.pose("look_up"), 0.55 * ramp(p, 0.0, 0.2)), "light": 0.55}


def rrect(x0, y0, x1, y1, r, n=6):
    """A rounded rectangle as one closed polyline, starting at the top middle (so it draws itself on evenly)."""
    import math

    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    pts = [((x0 + x1) / 2, y0)]
    corners = [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]
    for cx, cy, start in corners:
        for i in range(n + 1):
            t = math.radians(start + 90 * i / n)
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
    pts.append(((x0 + x1) / 2, y0))
    return pts


def fit(cr, words, size, max_w, weight=cairo.FONT_WEIGHT_NORMAL):
    """The largest size up to `size` at which every one of `words` is at most `max_w` wide."""
    widest = max((text_width(cr, w, size, weight) for w in words if w), default=0)
    return size if widest <= max_w else size * max_w / widest
