"""「一笔」: the protagonist, a figure drawn in glowing white lines with a gold point of light in the chest.

A pose is a dict of angles in degrees.  Limb angles are absolute and measured from straight down; positive
points forward (the way the hero faces), 90 is horizontal-forward, 180 straight up:
  lean          torso tilt from upright (positive = leaning forward)
  head          extra head tilt on top of the torso (positive = bowing, negative = looking up)
  ua_f la_f     front arm: upper arm, forearm         ua_b la_b   back arm
  th_f sh_f     front leg: thigh, shin                th_b sh_b   back leg
  turn          0 = side view, 1 = facing the camera (the back limbs swing to the other side)
`solve` puts the lowest point of the body on the ground, so kneeling, sitting and falling need no extra
offsets.  Poses blend by interpolating the angles, which is how one shot's pose flows into the next.
"""
from __future__ import annotations

import math

from .stage import GOLD, WHITE, circle, glow_dot, line, lerp

THIGH, SHIN, TORSO, UPPER, FORE, HEAD_R, NECK = 46, 46, 72, 36, 33, 18, 9
KEYS = ("lean", "head", "ua_f", "la_f", "ua_b", "la_b", "th_f", "sh_f", "th_b", "sh_b", "turn")

POSES = {
    "stand":      dict(lean=2, head=0, ua_f=8, la_f=14, ua_b=-6, la_b=0, th_f=4, sh_f=2, th_b=-4, sh_b=-6),
    "look_up":    dict(lean=-6, head=-38, ua_f=6, la_f=10, ua_b=-8, la_b=-4, th_f=4, sh_f=2, th_b=-4, sh_b=-6),
    "kneel":      dict(lean=14, head=30, ua_f=28, la_f=80, ua_b=-4, la_b=8, th_f=86, sh_f=0, th_b=12, sh_b=-86),
    "sit":        dict(lean=10, head=18, ua_f=58, la_f=96, ua_b=44, la_b=86, th_f=96, sh_f=18, th_b=88, sh_b=10),
    "hurt":       dict(lean=36, head=22, ua_f=62, la_f=34, ua_b=10, la_b=20, th_f=82, sh_f=-4, th_b=18, sh_b=-82),
    "trip":       dict(lean=42, head=-10, ua_f=118, la_f=124, ua_b=96, la_b=112, th_f=34, sh_f=12, th_b=-44, sh_b=-64),
    "fallen":     dict(lean=74, head=-14, ua_f=2, la_f=-4, ua_b=-4, la_b=-8, th_f=24, sh_f=-82, th_b=10, sh_b=-86),
    "bend":       dict(lean=62, head=18, ua_f=34, la_f=24, ua_b=4, la_b=8, th_f=14, sh_f=-4, th_b=-10, sh_b=-14),
    "point_back": dict(lean=-4, head=-22, ua_f=10, la_f=16, ua_b=-148, la_b=-154, th_f=6, sh_f=2, th_b=-6, sh_b=-8),
    "lamp_up":    dict(lean=0, head=-12, ua_f=128, la_f=138, ua_b=-6, la_b=0, th_f=6, sh_f=2, th_b=-6, sh_b=-8),
    "lamp_hold":  dict(lean=2, head=4, ua_f=42, la_f=86, ua_b=-6, la_b=0, th_f=4, sh_f=2, th_b=-4, sh_b=-6),
    "receive":    dict(lean=6, head=6, ua_f=72, la_f=84, ua_b=-6, la_b=0, th_f=4, sh_f=2, th_b=-4, sh_b=-6),
    "write":      dict(lean=40, head=32, ua_f=52, la_f=20, ua_b=30, la_b=10, th_f=86, sh_f=0, th_b=12, sh_b=-86),
    "plant":      dict(lean=22, head=14, ua_f=66, la_f=14, ua_b=74, la_b=24, th_f=30, sh_f=18, th_b=-26, sh_b=-26),
    "front":      dict(lean=0, head=0, ua_f=10, la_f=6, ua_b=10, la_b=6, th_f=5, sh_f=2, th_b=5, sh_b=2, turn=1),
}


def pose(name: str, t: float = 0.0, stride: float = 1.0) -> dict:
    """Angles for a named pose; "walk" is a cycle driven by time."""
    if name == "walk":
        ph = t * 2 * math.pi * 0.9
        s = math.sin(ph)
        return dict(lean=5, head=0, turn=0,
                    th_f=26 * s * stride, sh_f=26 * s * stride - 10 - 22 * max(0.0, math.cos(ph)) * stride,
                    th_b=-26 * s * stride, sh_b=-26 * s * stride - 10 - 22 * max(0.0, -math.cos(ph)) * stride,
                    ua_f=-22 * s * stride, la_f=-22 * s * stride + 18, ua_b=22 * s * stride, la_b=22 * s * stride + 18)
    out = dict(turn=0)
    out.update(POSES[name])
    return out


def blend(a: dict, b: dict, k: float) -> dict:
    return {key: lerp(a.get(key, 0.0), b.get(key, 0.0), k) for key in KEYS}


def _chain(x, y, segs):
    pts = [(x, y)]
    for length, ang in segs:
        r = math.radians(ang)
        x += length * math.sin(r)
        y += length * math.cos(r)
        pts.append((x, y))
    return pts


def solve(p: dict) -> dict:
    """Joint positions in design units, x forward, ground at y = 0."""
    lean = math.radians(p["lean"])
    neck = (TORSO * math.sin(lean), -TORSO * math.cos(lean))
    hd = math.radians(p["lean"] + p["head"])
    head = (neck[0] + (NECK + HEAD_R) * math.sin(hd), neck[1] - (NECK + HEAD_R) * math.cos(hd))
    shoulder = (neck[0] - 8 * math.sin(lean), neck[1] + 8 * math.cos(lean))
    chest = (lerp(neck[0], 0, 0.38), lerp(neck[1], 0, 0.38))
    mirror = 1 - 2 * p.get("turn", 0.0)           # back limbs swing across as the hero turns to face us

    def back(pts, origin):
        return [(origin[0] + (x - origin[0]) * mirror, y) for x, y in pts]
    arm_f = _chain(*shoulder, [(UPPER, p["ua_f"]), (FORE, p["la_f"])])
    arm_b = back(_chain(*shoulder, [(UPPER, p["ua_b"]), (FORE, p["la_b"])]), shoulder)
    leg_f = _chain(0, 0, [(THIGH, p["th_f"]), (SHIN, p["sh_f"])])
    leg_b = back(_chain(0, 0, [(THIGH, p["th_b"]), (SHIN, p["sh_b"])]), (0, 0))
    lowest = max(y for y in (*[q[1] for q in (*leg_f, *leg_b, *arm_f, *arm_b)], head[1] + HEAD_R))
    move = lambda q: (q[0], q[1] - lowest)
    return {"hip": move((0, 0)), "neck": move(neck), "head": move(head), "chest": move(chest),
            "arm_f": [move(q) for q in arm_f], "arm_b": [move(q) for q in arm_b],
            "leg_f": [move(q) for q in leg_f], "leg_b": [move(q) for q in leg_b]}


def draw(cr, x: float, ground: float, p: dict, scale: float, facing: int = 1, light: float = 0.6,
         alpha: float = 1.0) -> dict:
    """Draw the hero with feet on `ground`; returns joint positions in screen space (for props)."""
    j = solve(p)
    to = lambda q: (x + q[0] * scale * facing, ground + q[1] * scale)
    sj = {k: (to(v) if isinstance(v, tuple) else [to(q) for q in v]) for k, v in j.items()}
    w = 5.2 * scale
    back_a = alpha * (0.55 + 0.45 * p.get("turn", 0.0))  # far-side limbs a little dimmer: reads as depth
    line(cr, sj["leg_b"], w, a=back_a)
    line(cr, sj["arm_b"], w, a=back_a)
    line(cr, [sj["hip"], sj["neck"]], w, a=alpha)
    line(cr, sj["leg_f"], w, a=alpha)
    line(cr, sj["arm_f"], w, a=alpha)
    circle(cr, *sj["head"], HEAD_R * scale, w, a=alpha)
    if light > 0:
        glow_dot(cr, *sj["chest"], (3.5 + 2.5 * light) * scale, GOLD, a=alpha * min(1.0, 0.45 + light), rings=8,
                 spread=0.3 + 0.35 * light)
    return sj


def lamp(cr, hand: tuple[float, float], scale: float, glow: float = 1.0, alpha: float = 1.0) -> tuple[float, float]:
    """A small lantern hanging from the hand; returns its centre (where its light comes from)."""
    hx, hy = hand
    top = hy + 14 * scale
    line(cr, [(hx, hy), (hx, top)], 2.4 * scale, a=alpha)
    cx, cy = hx, top + 15 * scale
    if glow > 0:
        glow_dot(cr, cx, cy, 9 * scale, GOLD, a=alpha * glow, rings=12, spread=0.9)
    w, h = 13 * scale, 17 * scale
    line(cr, [(cx - w, cy - h), (cx + w, cy - h), (cx + w, cy + h), (cx - w, cy + h), (cx - w, cy - h)],
         2.6 * scale, WHITE, a=alpha)
    return cx, cy
