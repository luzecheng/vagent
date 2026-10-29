"""两条岔路: the road splits in two.  One is bright near the hero and dark far away, the other the opposite
(first-order vs second-order consequences).

params
  labels   optional words for the two roads, e.g. ["一阶后果", "二阶后果"]
  choose   0 or 1: after both are shown, the hero turns onto that road (default: none)
"""
from __future__ import annotations

from .. import hero as H
from ..stage import GOLD, WHITE, lerp, line, ramp, text

TITLE = "两条岔路"
MIN_S = 4.0


def camera(params):
    return {"lift": -0.22, "zoom": 1.0, "ease": 1.4}


def hero(st, p, d, params):
    choose = params.get("choose")
    if choose is None:
        return {"x": st.W * 0.2, "pose": H.pose("stand"), "light": 0.5, "scale": 0.85}
    go = ramp(p, 0.65, 1.0)
    end = _roads(st)[int(choose)][-1]
    walking = H.pose("walk", st.t) if 0 < go < 1 else H.pose("stand")
    return {"x": lerp(st.W * 0.2, lerp(st.W * 0.2, end[0], 0.35), go), "pose": walking, "light": 0.5, "scale": 0.85,
            "y": lerp(st.horizon + _drop(st), lerp(st.horizon + _drop(st), end[1], 0.35), go)}


def _drop(st):
    return (st.H * (0.82 if not st.portrait else 0.72) - st.horizon) * 0.55


def _roads(st):
    x0, y0 = st.W * 0.2 + 60 * st.u, st.horizon + _drop(st)
    up = [(lerp(x0, st.W * 0.9, k / 30), lerp(y0, st.horizon + 8 * st.u, (k / 30) ** 0.8) - 40 * st.u * (k / 30))
          for k in range(31)]
    down = [(lerp(x0, st.W * 0.92, k / 30), lerp(y0, st.horizon + _drop(st) * 1.25, (k / 30) ** 1.2)) for k in range(31)]
    return up, down


def _road(cr, pts, near_bright, a, u, k):
    n = max(2, int(len(pts) * k))
    for i in range(1, n):
        f = i / (len(pts) - 1)
        bright = (1 - f) if near_bright else f
        col = GOLD if bright > 0.5 else WHITE
        line(cr, [pts[i - 1], pts[i]], (2 + 3 * bright) * u, col, a=a * (0.2 + 0.8 * bright), glow=bright > 0.5)


def draw(cr, st, p, d, a, params):
    u = st.u
    up, down = _roads(st)
    _road(cr, up, True, a, u, ramp(p, 0.05, 0.4))
    _road(cr, down, False, a, u, ramp(p, 0.25, 0.6))
    labels = params.get("labels", [])
    for i, (pts, word) in enumerate(zip((up, down), labels)):
        q = pts[len(pts) // 2]
        text(cr, word, 38 * u, q[0], q[1] + (-50 if i == 0 else 50) * u, WHITE, a=a * ramp(p, 0.4 + 0.1 * i, 0.55 + 0.1 * i))
