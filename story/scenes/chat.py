"""对话框: a conversation with AI in the sky: speech bubbles appear one by one, yours on the left (white) and
AI's on the right (gold), each AI reply after a moment of typing dots.  The hero looks up at it.

params
  bubbles  optional short words, one per bubble, starting with yours and then alternating (+ `bubbles_en`);
           without them the bubbles hold glowing text bars
  count    how many bubbles when there are no words (default 3)
"""
from __future__ import annotations

from ..stage import GOLD, WHITE, glow_dot, line, partial, ramp, text, text_width
from . import _objects as O

TITLE = "对话框"
MIN_S = 4.0


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return O.hero_looking(st, p)


def layout(cr, st, params):
    """Bubbles stacked top to bottom.  Long words wrap onto more rows (like subtitles) rather than shrinking;
    the size only steps down when all the bubbles would not fit the space."""
    from ..render import wrap

    cx, cy, max_w, max_h = O.region(st, aspect=0.9)
    u = st.u
    words = list(params.get("bubbles", []))
    n = len(words) or int(params.get("count", 3))
    max_bw = max_w * 0.80
    size = 52 * u
    while True:
        pad = size * 0.9
        if words:
            rows = [wrap(cr, w, size, max_bw - 2 * pad) for w in words]
            heights = [len(r) * size * 1.35 + size * 1.0 for r in rows]
        else:
            rows = [[] for _ in range(n)]
            heights = [min(max_h / (n * 1.3), 120 * u)] * n
        gap = (max_h - sum(heights)) / (n + 1)
        if gap >= 22 * u or size <= 28 * u:
            break
        size *= 0.92
    left, right = cx - max_w / 2, cx + max_w / 2
    top = cy - max_h / 2
    bubbles, y = [], top + gap
    for i in range(n):
        mine = i % 2 == 0
        if words:
            bw = max(text_width(cr, r, size) for r in rows[i]) + 2 * pad
        else:
            bw = max_bw * (0.62 if mine else 0.78)
        bw = min(bw, max_bw)
        x0 = left if mine else right - bw
        bubbles.append({"rect": (x0, y, x0 + bw, y + heights[i]), "mine": mine, "rows": rows[i]})
        y += heights[i] + gap
    return {"bubbles": bubbles, "size": size, "pad": pad, "box": (left, top, right, top + max_h),
            "texts": [(r, size, max_bw - 2 * pad) for b in bubbles for r in b["rows"]]}


def draw(cr, st, p, d, a, params):
    L, u = layout(cr, st, params), st.u
    n = len(L["bubbles"])
    for i, b in enumerate(L["bubbles"]):
        x0, y0, x1, y1 = b["rect"]
        start = 0.05 + 0.82 * i / n
        typing = 0.0 if b["mine"] else 0.06
        if not b["mine"] and start - 0.02 < p < start + typing:      # AI is typing…
            for k in range(3):
                glow_dot(cr, x1 - (60 - 22 * k) * u, (y0 + y1) / 2, 5 * u, GOLD,
                         a=a * (0.4 + 0.6 * ((st.t * 3 + k * 0.33) % 1)), rings=3)
            continue
        k = ramp(p, start + typing, start + typing + 0.10)
        if k <= 0:
            continue
        col = WHITE if b["mine"] else GOLD
        shape = O.rrect(x0, y0, x1, y1, min(y1 - y0, 120 * u) * 0.35)
        tail = ([(x0 + 26 * u, y1 - 2 * u), (x0 + 8 * u, y1 + 22 * u), (x0 + 52 * u, y1 - 2 * u)] if b["mine"] else
                [(x1 - 26 * u, y1 - 2 * u), (x1 - 8 * u, y1 + 22 * u), (x1 - 52 * u, y1 - 2 * u)])
        cr.set_source_rgba(col[0], col[1], col[2], 0.08 * a * k)
        cr.move_to(*shape[0])
        for q in shape[1:]:
            cr.line_to(*q)
        cr.fill()
        line(cr, partial(shape, k), 3 * u, col, a=a)
        line(cr, tail, 3 * u, col, a=a * ramp(k, 0.7, 1.0))
        if b["rows"]:
            step = L["size"] * 1.35
            first = (y0 + y1) / 2 - step * (len(b["rows"]) - 1) / 2
            for r, row in enumerate(b["rows"]):
                text(cr, row, L["size"], (x0 + x1) / 2, first + r * step, col, a=a * ramp(k, 0.5, 1.0))
        else:
            pad = L["pad"]
            for r, frac in enumerate((0.9, 0.6)):
                y = y0 + (y1 - y0) * (0.36 + 0.3 * r)
                line(cr, partial([(x0 + pad, y), (x0 + pad + (x1 - x0 - 2 * pad) * frac, y)], ramp(k, 0.4, 1.0)),
                     3 * u, col, a=a * 0.8, glow=False)
