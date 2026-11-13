"""倒计时: a countdown ring drains in the sky and pressure words light up one by one; the hero hurries.

params
  labels   the words that light up (e.g. ["限时", "满减", "倒计时"]); `labels_en` for the English version
"""
from __future__ import annotations

import math

from .. import hero as H
from ..stage import GOLD, RED, WHITE, circle, glow_dot, line, ramp, text

TITLE = "倒计时"
MIN_S = 3.0


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def speed(p, d, params):
    return 1.6


def hero(st, p, d, params):
    pose = H.pose("walk", st.t * 1.6, stride=1.15)
    pose["lean"] = 14
    return {"x": st.hx * 0.85, "pose": pose, "light": 0.35}


def draw(cr, st, p, d, a, params):
    u = st.u
    cx = st.W * (0.68 if not st.portrait else 0.62)
    cy = st.H * (0.30 if not st.portrait else 0.30)
    r = min(130 * u, st.W * 0.18)
    left = 1 - ramp(p, 0.05, 1.0)
    circle(cr, cx, cy, r, 2 * u, WHITE, a=a * 0.25, glow=False)
    pts = [(cx + r * math.sin(2 * math.pi * k / 90 * left), cy - r * math.cos(2 * math.pi * k / 90 * left))
           for k in range(91)]
    hot = RED if left < 0.35 else GOLD
    line(cr, pts, 5 * u, hot, a=a)
    for k in range(12):                          # ticks
        ang = 2 * math.pi * k / 12
        line(cr, [(cx + r * 0.82 * math.sin(ang), cy - r * 0.82 * math.cos(ang)),
                  (cx + r * 0.9 * math.sin(ang), cy - r * 0.9 * math.cos(ang))], 2 * u, a=a * 0.6, glow=False)
    hand = 2 * math.pi * (st.t * 1.2 % 1)
    line(cr, [(cx, cy), (cx + r * 0.7 * math.sin(hand), cy - r * 0.7 * math.cos(hand))], 3 * u, a=a)
    glow_dot(cr, cx, cy, 5 * u, hot, a=a, rings=4)
    labels = params.get("labels", [])
    for i, word in enumerate(labels):
        k = ramp(p, 0.1 + 0.25 * i, 0.22 + 0.25 * i)
        pulse = 1 + 0.06 * math.sin(st.t * 9 + i)
        ly = cy + r + (70 + 62 * i) * u if st.portrait else cy - r * 0.6 + i * 80 * u
        lx = cx if st.portrait else cx - r - 210 * u
        text(cr, word, 50 * u * pulse, lx, ly, GOLD, a=a * k, weight=1, glow=k)
