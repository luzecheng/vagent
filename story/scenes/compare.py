"""对比卡: the hero and someone else stand facing each other across one shared thing; a thought bubble lights up
over each head with different words (the same thing, seen two ways).

params
  topic    optional: the shared thing, shown on the ground between them, e.g. "下周上线"; `topic_en`
  left     the hero's words: a string or a list of short lines, e.g. ["没测完？", "出问题？"]; `left_en`
  right    the other person's words, same form; `right_en`
  poses    optional [hero pose, other pose], names from hero.POSES, e.g. ["bend", "lamp_up"] (default stand)
Keep `quote` off this shot: the bubbles sit where the gold quote would.
"""
from __future__ import annotations

import math

from .. import hero as H
import cairo

from ..stage import GOLD, WHITE, line, partial, ramp, text, text_width

TITLE = "对比卡"
MIN_S = 4.0
BOLD = cairo.FONT_WEIGHT_BOLD
HEAD_TOP = 214   # the standing hero's height above the ground, in hero units (feet to top of head)


def camera(params):
    return {"lift": 0.0, "zoom": 1.0, "ease": 1.2}


def _lines(v) -> list[str]:
    return [v] if isinstance(v, str) else list(v or [])


def layout(st):
    """x of the hero and of the other person, the room for the bubbles (highest top, bottom) and each bubble's
    width.  A bubble is only as tall as its words need, hanging from the bottom line just over the heads."""
    xs = (st.W * 0.27, st.W * 0.73) if st.portrait else (st.W * 0.30, st.W * 0.70)
    head = st.horizon - HEAD_TOP * st.s
    top = head - (st.H * 0.30 if st.portrait else st.H * 0.40)
    return xs, (top, head - 50 * st.u), (st.W * 0.42 if st.portrait else st.W * 0.34)


def fit(cr, st, words):
    """Rows for each bubble and one word size for both.  The largest size (up to 64 px at 1080) that keeps every
    line whole, down to 44 px; failing that, long lines wrap, at the size that needs the fewest rows."""
    from ..render import wrap     # deferred: render imports the scene library
    _, (top, bottom), width = layout(st)
    room, height = width - 70 * st.u, bottom - top - 50 * st.u
    fits = lambda rows, size: max(len(r) for r in rows) * size * 1.35 <= height and \
        all(text_width(cr, s, size, BOLD) <= room for r in rows for s in r)
    for px in range(64, 43, -2):
        if fits(words, px * st.u):
            return words, px * st.u
    best = None
    for px in range(56, 31, -2):
        size = px * st.u
        rows = [[r for s in w for r in wrap(cr, s, size, room * 0.9)] for w in words]   # bold runs ~10% wider
        if fits(rows, size) and (best is None or max(map(len, rows)) < max(map(len, best[0]))):
            best = rows, size
    return best or (rows, size)


def bubble_top(st, rows, size):
    """Top of one bubble holding `rows` lines of words."""
    _, (_, bottom), _ = layout(st)
    return bottom - len(rows) * size * 1.35 - 60 * st.u


def hero(st, p, d, params):
    poses = params.get("poses", ["stand", "stand"])
    (hx, _), _, _ = layout(st)
    return {"x": hx, "pose": H.blend(H.pose("stand"), H.pose(poses[0]), ramp(p, 0.3, 0.5)), "light": 0.5,
            "facing": 1}


def _bubble(cr, st, x, top, bottom, width, rows, size, col, a, k):
    """A dark card (stars and moon don't show through) whose outline draws itself in, a small tail toward the
    head, then the words fade up."""
    r = 26 * st.u
    x0, x1 = x - width / 2, x + width / 2
    cr.new_sub_path()
    for cx, cy, a0 in ((x1 - r, top + r, -90), (x1 - r, bottom - r, 0), (x0 + r, bottom - r, 90), (x0 + r, top + r, 180)):
        cr.arc(cx, cy, r, math.radians(a0), math.radians(a0 + 90))
    cr.close_path()
    cr.set_source_rgba(0.07, 0.08, 0.14, 0.88 * a * ramp(k, 0.0, 0.3))
    cr.fill()
    pts = []
    for cx, cy, a0 in ((x1 - r, top + r, -90), (x1 - r, bottom - r, 0), (x0 + r, bottom - r, 90), (x0 + r, top + r, 180)):
        pts += [(cx + r * math.cos(math.radians(a0 + 9 * i)), cy + r * math.sin(math.radians(a0 + 9 * i)))
                for i in range(11)]
    pts.append(pts[0])
    line(cr, partial(pts, k), 2.6 * st.u, col, a=a * 0.75)
    for i, off in enumerate((24, 40)):
        dot = (x - (8 + 6 * i) * st.u, bottom + off * st.u)
        line(cr, [dot, (dot[0] + 0.5, dot[1])], (7 - 2 * i) * st.u, col, a=a * 0.75 * ramp(k, 0.9, 1.0))
    w = ramp(k, 0.85, 1.0)
    mid, gap = (top + bottom) / 2, size * 1.35
    for n, s in enumerate(rows):
        text(cr, s, size, x, mid + (n - (len(rows) - 1) / 2) * gap, col, a=a * w, weight=BOLD)


def draw(cr, st, p, d, a, params):
    (hx, ox), (_, bottom), width = layout(st)
    poses = params.get("poses", ["stand", "stand"])
    g = st.horizon
    other = H.blend(H.pose("stand"), H.pose(poses[1]), ramp(p, 0.5, 0.7))
    H.draw(cr, ox, g, other, st.s, facing=-1, light=0.0, alpha=a * 0.75 * ramp(p, 0.0, 0.15))  # dimmer: not the hero
    if params.get("topic"):            # on the ground between their feet, clear of a bending hero's head
        size = 46 * st.u
        size *= min(1.0, (ox - hx - 200 * st.u) / text_width(cr, params["topic"], size, BOLD))
        text(cr, params["topic"], size, st.W / 2, g - 36 * st.s, WHITE, a=a * ramp(p, 0.05, 0.2), weight=BOLD)
    words, size = fit(cr, st, [_lines(params.get("left")), _lines(params.get("right"))])
    for i, (x, rows, col) in enumerate(((hx, words[0], WHITE), (ox, words[1], GOLD))):
        if rows:
            k = ramp(p, 0.22 + 0.24 * i, 0.5 + 0.24 * i)
            _bubble(cr, st, x, bubble_top(st, rows, size), bottom, width, rows, size, col, a * ramp(k, 0.0, 0.05), k)

