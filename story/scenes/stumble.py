"""绊倒: the stone on the road trips the hero (pain, failure, hitting a problem).

params
  mode   "trip"   walk into the stone, fall, get up, walk on; `times` repeats it (the same stone again)
         "hurt"   crouched, rubbing the knee (red flash); fog drifts over the stone until it can't be seen
         "flower" a glowing flower grows by the stone; reaching for it, the hero trips again
  times  for "trip": how many times (default 2)
"""
from __future__ import annotations

from .. import hero as H
from ..stage import ramp
from . import _props

TITLE = "绊倒"
MIN_S = 4.0
FOOT = 66  # stone distance in front of the hero when the foot catches it, design px


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.0}


def _cycle(p, d, params):
    """For "trip": (cycle index, time in cycle, cycle length, trip time, resume time)."""
    times = int(params.get("times", 2))
    c = d / times
    t = min(p * d, d - 1e-6)
    i = int(t // c)
    return i, t - i * c, c, 0.34 * c, 0.74 * c


def speed(p, d, params):
    mode = params.get("mode", "trip")
    if mode == "trip":
        _, tau, c, trip, resume = _cycle(p, d, params)
        return 0.0 if trip <= tau < resume else 1.0
    return 0.0


def hero(st, p, d, params):
    mode = params.get("mode", "trip")
    walk, stand = H.pose("walk", st.t), H.pose("stand")
    if mode == "trip":
        _, tau, c, trip, resume = _cycle(p, d, params)
        if tau < trip:
            pose = walk
        elif tau < trip + 0.10 * c:
            pose = H.blend(walk, H.pose("trip"), ramp(tau, trip, trip + 0.06 * c))
        elif tau < 0.58 * c:
            pose = H.blend(H.pose("trip"), H.pose("fallen"), ramp(tau, trip + 0.06 * c, trip + 0.14 * c))
        elif tau < resume:
            pose = H.blend(H.pose("fallen"), stand, ramp(tau, 0.58 * c, resume))
        else:
            pose = H.blend(stand, walk, ramp(tau, resume, resume + 0.08 * c))
        return {"x": st.hx, "pose": pose, "light": 0.4}
    if mode == "hurt":
        return {"x": st.hx, "pose": H.pose("hurt"), "light": 0.3}
    # flower: step toward it, bend, trip, fall
    t = p
    x = st.hx + 50 * st.s * ramp(t, 0.30, 0.52)
    if t < 0.30:
        pose = stand
    elif t < 0.52:
        pose = H.pose("walk", st.t)
    elif t < 0.70:
        pose = H.blend(stand, H.pose("bend"), ramp(t, 0.52, 0.66))
    elif t < 0.78:
        pose = H.blend(H.pose("bend"), H.pose("trip"), ramp(t, 0.70, 0.76))
    else:
        pose = H.blend(H.pose("trip"), H.pose("fallen"), ramp(t, 0.76, 0.86))
    return {"x": x, "pose": pose, "light": 0.4}


def draw(cr, st, p, d, a, params):
    g, s = st.horizon, st.s
    mode = params.get("mode", "trip")
    if mode == "trip":
        _, tau, c, trip, resume = _cycle(p, d, params)
        if tau < trip:
            x = st.hx + FOOT * s + st.v * (trip - tau)
        elif tau < resume:
            x = st.hx + FOOT * s
        else:
            x = st.hx + FOOT * s - st.v * (tau - resume)
        fade = ramp(tau, 0, 0.12 * c) * (1 - ramp(tau, 0.9 * c, c))   # each pass: the same stone fades in again
        _props.stone(cr, x, g, s, a=a * fade)
    elif mode == "hurt":
        _props.stone(cr, st.hx + 150 * s, g, s, a=a, fog=ramp(p, 0.25, 0.8))
    else:
        sx = st.hx + 170 * s
        _props.stone(cr, sx, g, s, a=a)
        _props.flower(cr, sx - 58 * s, g, s, grow=ramp(p, 0.05, 0.3), a=a * (1 - 0.5 * ramp(p, 0.8, 1.0)))


def front(cr, st, p, d, a, params, joints):
    if not joints:
        return
    mode = params.get("mode", "trip")
    knee = joints["leg_f"][1]
    if mode == "trip":
        _, tau, c, trip, _ = _cycle(p, d, params)
        k = ramp(tau, trip + 0.04 * c, trip + 0.08 * c) * (1 - ramp(tau, trip + 0.12 * c, trip + 0.24 * c))
        _props.flash(cr, *knee, st.s, a=a * k)
    elif mode == "hurt":
        for t0 in (0.15, 0.55):
            k = ramp(p, t0, t0 + 0.05) * (1 - ramp(p, t0 + 0.08, t0 + 0.25))
            _props.flash(cr, *knee, st.s, a=a * k)
    else:
        k = ramp(p, 0.76, 0.80) * (1 - ramp(p, 0.84, 0.95))
        _props.flash(cr, *knee, st.s, a=a * k)
