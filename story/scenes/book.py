"""书: an open book floats in the sky; its lines of text write themselves in.  The hero looks up at it.

params
  flips   pages riffle past this many times (reading fast, e.g. "三分钟读完一本书"); default 0
  close   true: at the end the text fades and the book folds shut
  title   optional short word over the book (+ `title_en`)
"""
from __future__ import annotations

from ..stage import GOLD, WHITE, line, partial, ramp, text
from . import _objects as O

TITLE = "书"
MIN_S = 3.5
ROWS = 6


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return O.hero_looking(st, p)


def layout(cr, st, params):
    cx, cy, max_w, max_h = O.region(st, aspect=1.3)
    title_room = 70 * st.u if params.get("title") else 0
    ph = min((max_h - title_room) * 0.86, max_w * 0.62)
    pw = min(ph * 0.80, max_w * 0.47)
    cy += title_room / 2
    size = O.fit(cr, [params.get("title", "")], 44 * st.u, max_w)
    box = (cx - pw, cy - ph / 2 - title_room, cx + pw, cy + ph / 2 + 10 * st.u)
    return {"cx": cx, "cy": cy, "pw": pw, "ph": ph, "title_size": size, "box": box,
            "texts": [(params.get("title", ""), size, max_w)]}


def _page(cx, cy, pw, ph, side, k, u):
    """One page from the spine to its outer edge `k` (0..1) of the full width; the spine sits a little lower."""
    ex = cx + side * pw * k
    top, bottom = cy - ph / 2, cy + ph / 2
    return [(cx, top + 10 * u), (cx + side * pw * k * 0.5, top + 2 * u), (ex, top), (ex, bottom),
            (cx + side * pw * k * 0.5, bottom - 2 * u), (cx, bottom + 10 * u)]


def draw(cr, st, p, d, a, params):
    L, u = layout(cr, st, params), st.u
    cx, cy, pw, ph = L["cx"], L["cy"], L["pw"], L["ph"]
    appear = ramp(p, 0.0, 0.22)
    shut = ramp(p, 0.72, 0.92) if params.get("close") else 0.0
    fold = 1 - 0.9 * shut
    for side in (-1, 1):
        pts = _page(cx, cy, pw, ph, side, fold, u)
        cr.set_source_rgba(1, 1, 1, 0.06 * a * appear)
        cr.move_to(*pts[0])
        for q in pts[1:]:
            cr.line_to(*q)
        cr.close_path()
        cr.fill()
        line(cr, partial(pts, appear), 3 * u, WHITE, a=a)
    flips = int(params.get("flips", 0))
    written = ramp(p, 0.18, 0.40 if flips else 0.65)
    for side in (-1, 1):                               # lines of text, row by row
        for r in range(ROWS):
            k = max(0.0, min(1.0, written * ROWS - r))
            if k <= 0:
                break
            y = cy - ph / 2 + ph * (0.18 + 0.66 * r / (ROWS - 1))
            inner, outer = cx + side * pw * 0.12, cx + side * pw * (0.84 - 0.12 * ((r * 3 + side) % 3) / 2)
            line(cr, partial([(inner, y), (outer, y)], k), 2.4 * u, GOLD if r == 0 else WHITE,
                 a=a * (0.75 if r else 1) * (1 - shut) * fold, glow=r == 0)
    if flips and shut == 0:                              # pages riffling over from right to left
        import math
        phase = ramp(p, 0.30, 0.85) * flips
        if 0 < phase < flips:
            f = phase % 1
            k = math.cos(math.pi * f)
            line(cr, _page(cx, cy, pw, ph, 1 if k >= 0 else -1, abs(k), u), 2.6 * u, WHITE, a=a * 0.8)
    if shut > 0.85:                                     # the closed cover
        c = ramp(shut, 0.85, 1.0)
        cover = O.rrect(cx - pw * 0.42, cy - ph / 2, cx + pw * 0.42, cy + ph / 2, 10 * u)
        line(cr, cover, 3.4 * u, GOLD, a=a * c)
        line(cr, [(cx - pw * 0.42 + 16 * u, cy - ph / 2 + 6 * u), (cx - pw * 0.42 + 16 * u, cy + ph / 2 - 6 * u)],
             2.4 * u, GOLD, a=a * c, glow=False)
    if params.get("title"):
        text(cr, params["title"], L["title_size"], cx, cy - ph / 2 - 44 * u, WHITE, a=a * ramp(p, 0.1, 0.3))
