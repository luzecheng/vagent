"""购物车: the hero pulls a small cart; glowing boxes are the things we buy.

params
  mode  "fill"   walking, boxes drop into the cart one by one
        "glow"   the boxes pulse gold: the thrill of buying
        "heavy"  the load grows heavy, a bill floats down onto it, the hero strains and slows
        "dust"   the boxes sit in a corner, grey and dusty; the hero looks at them and kneels (regret)
        "count"  one box in front of the hero; tally marks appear over it, then a question mark
        "wait"   the hero sits by the cart while time passes (the moon draws an arc across the sky)
        "pull"   walking lightly with a single bright box: bought with thought
  boxes  how many boxes (default 5; "pull" uses 1)
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, WHITE, glow_dot, hexc, line, partial, ramp, text

TITLE = "购物车"
MIN_S = 3.0
GREY = hexc("b4b8c4")


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def speed(p, d, params):
    mode = params.get("mode", "fill")
    if mode in ("fill", "glow", "pull"):
        return 1.0
    if mode == "heavy":
        return 1.0 - 0.75 * ramp(p, 0.2, 0.7)
    return 0.0


def _pulling(st, slow=0.0):
    """Walking with the back hand reaching behind to the cart's handle."""
    pose = H.pose("walk", st.t * (1 - 0.5 * slow), stride=1 - 0.5 * slow)
    pose.update(ua_b=-48, la_b=-62, lean=5 + 25 * slow)
    return pose


def hero(st, p, d, params):
    mode = params.get("mode", "fill")
    if mode in ("fill", "glow", "pull"):
        return {"x": st.hx + 60 * st.s, "pose": _pulling(st), "light": 0.6 if mode != "glow" else 0.4}
    if mode == "heavy":
        return {"x": st.hx + 60 * st.s, "pose": _pulling(st, ramp(p, 0.2, 0.7)), "light": 0.35}
    if mode == "dust":
        pose = H.blend(H.pose("stand"), H.pose("kneel"), ramp(p, 0.45, 0.75))
        return {"x": st.hx, "pose": pose, "light": 0.5 - 0.3 * ramp(p, 0.45, 0.8)}
    if mode == "count":
        return {"x": st.hx, "pose": H.pose("stand"), "light": 0.55}
    return {"x": st.hx, "pose": H.blend(H.pose("stand"), H.pose("sit"), ramp(p, 0.0, 0.2)), "light": 0.5}


def _cart_x(st, mode):
    return st.hx + 160 * st.s if mode == "wait" else st.hx - 90 * st.s


def _box(cr, x, y, size, col, a, glow=0.0):
    if a <= 0:
        return
    pts = [(x - size, y), (x + size, y), (x + size, y - 2 * size), (x - size, y - 2 * size), (x - size, y)]
    cr.set_source_rgba(col[0], col[1], col[2], (0.18 + 0.3 * glow) * a)
    cr.rectangle(x - size, y - 2 * size, 2 * size, 2 * size)
    cr.fill()
    line(cr, pts, 2.4 * size / 14, col, a=a, glow=glow > 0)
    line(cr, [(x, y - 2 * size), (x, y)], 1.6 * size / 14, col, a=a * 0.6, glow=False)   # the tape
    if glow > 0:
        glow_dot(cr, x, y - size, size * 0.5, GOLD, a=a * glow * 0.6, rings=6, spread=0.9)


def _slots(n):
    """Box positions inside the cart, bottom row first: (dx, row)."""
    order = [(-1, 0), (0, 0), (1, 0), (-0.5, 1), (0.5, 1), (0, 2)]
    return order[:n]


def _cart(cr, st, x, a, boxes, col, glow, drop=None, grow=1.0):
    s, g = st.s, st.horizon
    wheel = 11 * s
    top, bottom = g - 2 * wheel - 46 * s, g - 2 * wheel
    body = [(x - 62 * s, top), (x - 54 * s, bottom), (x + 54 * s, bottom), (x + 62 * s, top)]
    line(cr, body, 3 * s, a=a)
    for wx in (x - 34 * s, x + 34 * s):
        cr.set_source_rgba(1, 1, 1, 0.9 * a)
        cr.set_line_width(2.6 * s)
        cr.new_sub_path()
        cr.arc(wx, g - wheel, wheel, 0, 2 * math.pi)
        cr.stroke()
    size = 14 * s * grow
    for i, (dx, row) in enumerate(_slots(boxes)):
        bx, by = x + dx * 2.1 * size, bottom - 4 * s - row * 2 * size
        k = 1.0 if drop is None else ramp(drop, i / boxes, (i + 0.8) / boxes)
        fall = (1 - k) * 260 * s
        _box(cr, bx, by - fall, size, col, a * min(1.0, k * 3), glow)
    return (x + 62 * s, top)       # the handle's corner, toward the hero


def draw(cr, st, p, d, a, params):
    mode = params.get("mode", "fill")
    s, g = st.s, st.horizon
    n = int(params.get("boxes", 1 if mode in ("pull", "count") else 5))
    x = _cart_x(st, mode)
    if mode == "fill":
        _cart(cr, st, x, a, n, GOLD, 0.4, drop=ramp(p, 0.05, 0.9))
    elif mode == "glow":
        _cart(cr, st, x, a, n, GOLD, 0.6 + 0.4 * math.sin(st.t * 5) ** 2)
        for k in range(6):                       # sparkles over the load
            ang = st.t * 1.5 + k
            glow_dot(cr, x + 70 * s * math.cos(ang), g - 120 * s + 30 * s * math.sin(ang * 1.3), 2.5 * s, GOLD,
                     a=a * (0.5 + 0.5 * math.sin(st.t * 4 + k)), rings=3)
    elif mode == "heavy":
        grow = 1 + 0.35 * ramp(p, 0.1, 0.6)
        col = tuple(GOLD[i] + (GREY[i] - GOLD[i]) * ramp(p, 0.2, 0.8) for i in range(3)) + (1.0,)
        _cart(cr, st, x, a, n, col, 0.3 * (1 - ramp(p, 0.2, 0.7)), grow=grow)
        k = ramp(p, 0.25, 0.75)                  # the bill drifts down onto the load
        bx, by = x + 40 * s * math.sin(p * 6) * (1 - k), g - 420 * s + 230 * s * k
        sheet = [(bx - 22 * s, by - 28 * s), (bx + 22 * s, by - 28 * s), (bx + 22 * s, by + 28 * s),
                 (bx - 22 * s, by + 28 * s), (bx - 22 * s, by - 28 * s)]
        line(cr, sheet, 2.2 * s, a=a * ramp(p, 0.2, 0.3))
        for r in range(3):
            line(cr, [(bx - 14 * s, by - 14 * s + r * 12 * s), (bx + 14 * s, by - 14 * s + r * 12 * s)], 1.6 * s,
                 a=a * ramp(p, 0.2, 0.3) * 0.7, glow=False)
    elif mode == "dust":
        cx = st.hx + 190 * s
        for i, (dx, row) in enumerate(_slots(n)):
            _box(cr, cx + dx * 30 * s, g - row * 28 * s, 14 * s, GREY, a)
        for k in range(14):                      # dust drifting down
            fy = (st.t * 12 + k * 37) % 120
            glow_dot(cr, cx - 60 * s + (k * 23 % 120) * s, g - 150 * s + fy * s, 1.6 * s, WHITE, a=a * 0.35, rings=2)
        web = [(cx + 46 * s, g - 90 * s), (cx + 70 * s, g - 70 * s), (cx + 60 * s, g - 50 * s)]
        line(cr, partial(web, ramp(p, 0.3, 0.7)), 1.2 * s, a=a * 0.45, glow=False)
    elif mode == "count":
        bx = st.hx + 140 * s
        _box(cr, bx, g, 22 * s, GOLD, a, 0.3)
        for k in range(2):                       # tally marks, then a question
            kk = ramp(p, 0.15 + 0.2 * k, 0.3 + 0.2 * k)
            line(cr, partial([(bx - 14 * s + k * 16 * s, g - 110 * s), (bx - 14 * s + k * 16 * s, g - 70 * s)], kk),
                 3 * s, a=a)
        text(cr, "?", 64 * s, bx + 40 * s, g - 92 * s, GOLD, a=a * ramp(p, 0.6, 0.75), weight=1, glow=0.6)
    elif mode == "wait":
        _cart(cr, st, x, a, max(1, n - 3), GOLD, 0.25)
        arc = [(st.W * (0.15 + 0.7 * i / 40), st.H * (0.42 - 0.26 * math.sin(math.pi * i / 40))) for i in range(41)]
        k = ramp(p, 0.1, 0.95)
        line(cr, partial(arc, k), 1.6 * st.u, GOLD, a=a * 0.5, glow=False)
        tip = partial(arc, k)[-1]
        glow_dot(cr, *tip, 14 * st.u, hexc("efe9dc"), a=a * 0.9, rings=5)
    else:  # pull
        _cart(cr, st, x, a, 1, GOLD, 0.8)


def front(cr, st, p, d, a, params, joints):
    mode = params.get("mode", "fill")
    if not joints or mode not in ("fill", "glow", "heavy", "pull"):
        return
    s, g = st.s, st.horizon
    corner = (_cart_x(st, mode) + 62 * s, g - 22 * s - 46 * s)
    line(cr, [corner, joints["arm_b"][-1]], 3 * s, a=a)
