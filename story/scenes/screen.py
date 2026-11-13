"""屏幕: a phone (or laptop) screen lights up in the sky and fills with content; with `off` it goes dark at the
end ("关掉屏幕").  The hero looks up at it.

params
  device  "phone" (default) or "laptop"; in portrait a laptop is drawn as a phone (a wide laptop would only
          fit, small, in the low strip over the hero's head; a tall phone fits large beside the hero)
  lines   optional short words shown on the screen, one row each, up to 4 (+ `lines_en`); without them the
          screen shows rows of glowing text bars
  off     true: near the end the screen switches off (the picture shrinks to a line and fades)
"""
from __future__ import annotations

from ..stage import GOLD, WHITE, line, partial, ramp, text
from . import _objects as O

TITLE = "屏幕"
MIN_S = 3.5


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def hero(st, p, d, params):
    return O.hero_looking(st, p)


def device(st, params):
    return "laptop" if params.get("device") == "laptop" and not st.portrait else "phone"


def layout(cr, st, params):
    laptop = device(st, params) == "laptop"
    cx, cy, max_w, max_h = O.region(st, aspect=1.45 if laptop else 0.5)
    u = st.u
    if laptop:
        w = min(max_w / 1.12, max_h / 0.70)              # the keyboard base is 6% wider on each side
        h = w * 0.60
        top = cy - (h + w * 0.08) / 2
        screen = (cx - w / 2, top, cx + w / 2, top + h)
        box = (cx - w / 2 - w * 0.06, top, cx + w / 2 + w * 0.06, top + h + w * 0.08)
    else:
        h = min(max_h, max_w / 0.52)
        w = h * 0.50
        screen = (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
        box = screen
    pad = 0.12 * (screen[2] - screen[0])
    inner = (screen[0] + pad, screen[1] + pad * 1.4, screen[2] - pad, screen[3] - pad * 1.4)
    words = list(params.get("lines", []))[:4]
    step = (inner[3] - inner[1]) / max(1, len(words))     # one row per word: the size also fits the row height
    size = O.fit(cr, words, min(66 * u, step / 1.3), inner[2] - inner[0]) if words else 0
    return {"screen": screen, "inner": inner, "box": box, "words": words, "size": size, "step": step,
            "texts": [(w_, size, inner[2] - inner[0]) for w_ in words]}


def draw(cr, st, p, d, a, params):
    L, u = layout(cr, st, params), st.u
    x0, y0, x1, y1 = L["screen"]
    ix0, iy0, ix1, iy1 = L["inner"]
    appear = ramp(p, 0.0, 0.2)
    off = ramp(p, 0.62, 0.80) if params.get("off") else 0.0
    on = ramp(p, 0.12, 0.28) * (1 - off)
    outline = O.rrect(x0, y0, x1, y1, (x1 - x0) * (0.10 if device(st, params) != "laptop" else 0.03))
    if on > 0:                                           # the lit glass
        cr.set_source_rgba(0.85, 0.9, 1.0, 0.10 * a * on)
        cr.move_to(*outline[0])
        for q in outline[1:]:
            cr.line_to(*q)
        cr.fill()
    line(cr, partial(outline, appear), 3.4 * u, WHITE, a=a * (1 - 0.5 * off))
    if device(st, params) == "laptop":
        w = x1 - x0
        base = [(x0 - w * 0.06, y1 + w * 0.08), (x1 + w * 0.06, y1 + w * 0.08), (x1, y1), (x0, y1)]
        line(cr, partial(base + base[:1], appear), 3 * u, WHITE, a=a * (1 - 0.5 * off))
    else:
        cxs = (x0 + x1) / 2
        line(cr, [(cxs - 18 * u, y0 + 18 * u), (cxs + 18 * u, y0 + 18 * u)], 3 * u, WHITE, a=a * appear * 0.7,
             glow=False)
    content = on * a
    words = L["words"]
    if words:
        n = len(words)
        for i, w_ in enumerate(words):
            k = ramp(p, 0.25 + 0.1 * i, 0.38 + 0.1 * i)
            y = iy0 + (iy1 - iy0) * (i + 0.5) / n
            text(cr, w_, L["size"], (ix0 + ix1) / 2, y, GOLD if i == 0 else WHITE, a=content * k)
    else:
        rows = 6
        for r in range(rows):
            k = ramp(p, 0.25 + 0.05 * r, 0.40 + 0.05 * r)
            y = iy0 + (iy1 - iy0) * r / (rows - 1)
            end = ix0 + (ix1 - ix0) * (1.0 if r == 0 else 0.55 + 0.4 * ((r * 7) % 5) / 4)
            line(cr, partial([(ix0, y), (end, y)], k), (5 if r == 0 else 3) * u, GOLD if r == 0 else WHITE,
                 a=content * (1 if r == 0 else 0.7), glow=r == 0)
    if 0 < off < 1:                                      # switching off: a bright line that shrinks to nothing
        cxs, cys = (x0 + x1) / 2, (y0 + y1) / 2
        half = (ix1 - ix0) / 2 * (1 - off)
        line(cr, [(cxs - half, cys), (cxs + half, cys)], 3 * u, WHITE, a=a * (1 - off))
