"""圆环相遇: a ring in the sky; from one point at its bottom two lights set off in opposite directions, trace
the ring and meet at the top in a flash (two opposite roads that end in the same place).

params
  labels   optional words for the two lights, [left, right], e.g. ["向前", "向后"]; `labels_en`
  meet     optional word that lights up where they meet, e.g. "同一个问题"; `meet_en`
  until    how far round they get, 0..1 (default 1: all the way to the top; 0.5: out to the sides)
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, WHITE, circle, glow_dot, line, partial, ramp, text, text_width

TITLE = "圆环相遇"
MIN_S = 4.5


def camera(params):
    return {"lift": 1.0, "zoom": 1.0, "ease": 2.0}


def hero(st, p, d, params):
    return {"x": st.hx, "pose": H.pose("look_up"), "light": 0.45 + 0.4 * ramp(p, 0.8, 1.0)}


def ring(st):
    """(x centre, y centre, radius)."""
    if st.portrait:
        return st.W * 0.5, st.H * 0.42, st.W * 0.30
    return st.W * 0.58, st.H * 0.53, st.H * 0.25


def heads(st, k):
    """Where the two lights are after going k of the way round (0: both at the bottom, 1: both at the top)."""
    cx, cy, r = ring(st)
    left, right = math.pi / 2 + k * math.pi, math.pi / 2 - k * math.pi
    return [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in (left, right)]


def label_size(cr, st, words):
    """Labels sit just outside the ring at its sides and shrink to stay on screen."""
    cx, _, r = ring(st)
    size = 44 * st.u
    room = min(cx - r, st.W - cx - r) - 24 * st.u
    widest = max([text_width(cr, w, size) for w in words] or [0])
    return size * min(1.0, room / widest) if widest else size


def draw(cr, st, p, d, a, params):
    cx, cy, r = ring(st)
    until = float(params.get("until", 1.0))
    circle(cr, cx, cy, r, 2 * st.u, WHITE, a=a * 0.22 * ramp(p, 0.0, 0.15))
    glow_dot(cr, cx, cy + r, 7 * st.u, WHITE, a=a * ramp(p, 0.0, 0.12), rings=6)
    k = until * ramp(p, 0.12, 0.8)
    steps = 48
    for side, col in ((1, GOLD), (-1, WHITE)):
        arc = [(cx + r * math.cos(math.pi / 2 + side * k * math.pi * i / steps),
                cy + r * math.sin(math.pi / 2 + side * k * math.pi * i / steps)) for i in range(steps + 1)]
        line(cr, arc, 3.4 * st.u, col, a=a * 0.9)
    for q, col in zip(heads(st, k), (GOLD, WHITE)):
        glow_dot(cr, *q, 9 * st.u, col, a=a * ramp(p, 0.1, 0.2), rings=8)
    labels = params.get("labels", [])
    if labels:
        size = label_size(cr, st, labels)
        for i, word in enumerate(labels[:2]):
            w = text_width(cr, word, size)
            x = cx - r - 24 * st.u - w / 2 if i == 0 else cx + r + 24 * st.u + w / 2
            text(cr, word, size, x, cy, GOLD if i == 0 else WHITE, a=a * ramp(p, 0.25, 0.45))
    if until >= 1.0:
        flash = ramp(p, 0.78, 0.92)
        glow_dot(cr, cx, cy - r, (10 + 26 * flash) * st.u, GOLD, a=a * flash * (1 - 0.4 * ramp(p, 0.92, 1.0)),
                 rings=12, spread=0.7)
        if params.get("meet"):
            text(cr, params["meet"], 52 * st.u, cx, cy - r - 70 * st.u, GOLD, a=a * ramp(p, 0.84, 0.98), weight=1,
                 glow=ramp(p, 0.84, 0.98))
