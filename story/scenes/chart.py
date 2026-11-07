"""曲线图: axes appear in the sky and a curve draws itself across them (growth, decline, ups and downs).  The
hero looks up at it.  Numbers never appear unless the script gives them (put them in `labels`).

params
  trend    "up" (default), "down", "wave", "up_down" or "down_up": the shape of the curve
  values   optional numbers that shape the curve instead (only numbers taken from the script)
  labels   optional [left, right] words under the two ends of the curve, e.g. ["2018", "2021"] (+ `labels_en`)
  color    "gold" (default), "red" or "white"
"""
from __future__ import annotations

from ..stage import GOLD, RED, WHITE, glow_dot, line, partial, ramp, text
from . import _objects as O

TITLE = "曲线图"
MIN_S = 3.5
SHAPES = {
    "up": [1.0, 1.4, 1.2, 1.9, 2.3, 2.1, 2.9, 3.6],
    "down": [3.6, 3.2, 3.4, 2.6, 2.2, 2.4, 1.6, 1.0],
    "wave": [2.0, 3.0, 1.6, 2.8, 1.4, 2.6, 1.8, 2.4],
    "up_down": [1.0, 1.8, 2.6, 3.4, 3.6, 2.8, 1.8, 1.2],
    "down_up": [3.4, 2.6, 1.8, 1.2, 1.0, 1.8, 2.8, 3.6],
}
COLORS = {"gold": GOLD, "red": RED, "white": WHITE}


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return O.hero_looking(st, p)


def layout(cr, st, params):
    cx, cy, max_w, max_h = O.region(st, aspect=1.45)
    labels = list(params.get("labels", []))[:2]
    label_room = 64 * st.u if labels else 0
    w = min(max_w, (max_h - label_room) * 1.6)
    h = w / 1.6
    top = cy - (h + label_room) / 2
    plot = (cx - w / 2, top, cx + w / 2, top + h)
    size = O.fit(cr, labels, 38 * st.u, w * 0.45) if labels else 0
    return {"plot": plot, "labels": labels, "size": size, "box": (plot[0], top, plot[2], top + h + label_room),
            "texts": [(s, size, w * 0.45) for s in labels]}


def curve(params, plot, n=48):
    vals = [float(v) for v in params.get("values", [])] or SHAPES.get(params.get("trend", "up"), SHAPES["up"])
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    x0, y0, x1, y1 = plot
    left, right = x0 + (x1 - x0) * 0.08, x1 - (x1 - x0) * 0.04
    pts = []
    for i in range(n + 1):                               # smooth curve through the values
        t = i / n * (len(vals) - 1)
        j = min(int(t), len(vals) - 2)
        f = t - j
        f = f * f * (3 - 2 * f)
        v = vals[j] + (vals[j + 1] - vals[j]) * f
        pts.append((left + (right - left) * i / n, y1 - (y1 - y0) * (0.10 + 0.80 * (v - lo) / span)))
    return pts


def label_x(cr, L, pts, i):
    """Centre of the left/right label: under its end of the curve, pulled in so it stays over the plot."""
    from ..stage import text_width
    x0, _, x1, _ = L["plot"]
    half = text_width(cr, L["labels"][i], L["size"]) / 2
    px = pts[0][0] if i == 0 else pts[-1][0]
    return min(max(px, x0 + half), x1 - half)


def draw(cr, st, p, d, a, params):
    L, u = layout(cr, st, params), st.u
    x0, y0, x1, y1 = L["plot"]
    axes = [(x0, y0), (x0, y1), (x1, y1)]
    line(cr, partial(axes, ramp(p, 0.0, 0.18)), 3 * u, WHITE, a=a)
    pts = curve(params, L["plot"])
    k = ramp(p, 0.15, 0.80)
    col = COLORS.get(params.get("color", "gold"), GOLD)
    line(cr, partial(pts, k), 5 * u, col, a=a)
    if k > 0:
        hx, hy = partial(pts, k)[-1]
        glow_dot(cr, hx, hy, 8 * u, col, a=a, rings=8)
    for i, s in enumerate(L["labels"]):
        px = label_x(cr, L, pts, i)
        text(cr, s, L["size"], px, y1 + 36 * u, WHITE, a=a * ramp(p, 0.2 + 0.5 * i, 0.35 + 0.5 * i))
