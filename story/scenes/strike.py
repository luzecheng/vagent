"""划掉旧观点: an old belief shines in the sky; a red line strikes it out, it dims and sinks, and the new view
rises in gold beneath it.

params
  old   the old view (e.g. "犯错=我不行"); `old_en` for the English version
  new   the new view that replaces it (optional: without it only the strike-out is shown); `new_en`
"""
from __future__ import annotations

from .. import hero as H
from ..stage import GOLD, RED, WHITE, line, partial, ramp, text, text_width

TITLE = "划掉旧观点"
MIN_S = 3.5


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return {"x": st.hx, "pose": H.blend(H.pose("stand"), H.pose("look_up"), ramp(p, 0.0, 0.2)), "light": 0.45}


def layout(cr, st, params):
    """(size, x centre, y of the old view, y of the new view): both lines fit the screen width."""
    size = 96 * st.u
    widest = max(text_width(cr, params.get("old", ""), size), text_width(cr, params.get("new", ""), size, weight=1))
    cx = st.W * (0.62 if not st.portrait else 0.5)
    size *= min(1.0, 2 * min(cx, st.W - cx) * 0.9 / widest)        # the struck line is a little wider than the text
    top = st.H * (0.20 if not st.portrait else 0.22)
    return size, cx, top, top + size * 2.0


def draw(cr, st, p, d, a, params):
    old, new = params.get("old", ""), params.get("new", "")
    size, cx, y_old, y_new = layout(cr, st, params)
    strike = ramp(p, 0.25, 0.45)
    sink = ramp(p, 0.45, 0.65) if new else 0.0
    y = y_old + sink * size * 0.3
    text(cr, old, size, cx, y, WHITE, a=a * ramp(p, 0.0, 0.15) * (1 - 0.6 * sink))
    half = text_width(cr, old, size) / 2 + size * 0.2
    pts = [(cx - half, y + size * 0.05), (cx + half, y - size * 0.05)]
    line(cr, partial(pts, strike), 5 * st.u, RED, a=a * (1 - 0.4 * sink))
    if new:
        k = ramp(p, 0.55, 0.8)
        text(cr, new, size, cx, y_new + (1 - k) * size * 0.4, GOLD, a=a * k, weight=1, glow=k)
