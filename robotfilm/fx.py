"""Shared helpers for robot-story beats (episode files robot2/beats.py): poses, sky placement, labels, timing,
anchoring things in the world, the robot's joints, fog."""
import math

import cairo

from robotfilm.robot_story import ICE, coin, coin_stack, glow_line, orb, smooth
from robotfilm.walker import STAND
from story.stage import FONT, GOLD, WHITE, ramp, text

P = lambda **kw: {**STAND, **kw}
CHEER = P(ua_f=160, la_f=172, head=-12)
BOW = P(head=24, lean=4)
THINK = P(ua_f=28, la_f=158, head=10)
LOOK_UP = P(head=-30, lean=-3)
GIVE = P(ua_f=72, la_f=82)
HOLD = P(ua_f=34, la_f=82, ua_b=26, la_b=78)
POINT = P(ua_f=128, la_f=136, head=-14)
BEND = P(lean=26, th_f=30, sh_f=-8, th_b=22, sh_b=-20, ua_f=20, la_f=40, ua_b=-10, la_b=60, head=10)
SHRUG = P(ua_f=26, la_f=96, ua_b=-22, la_b=82, head=6)
READ = P(ua_f=36, la_f=96, ua_b=30, la_b=92, head=22)
WORK = lambda lt, d: P(ua_f=46, la_f=88 + 14 * math.sin(lt * 9), ua_b=40, la_b=80 + 12 * math.sin(lt * 9 + 2), head=18)


def L(ctx, zh, en):
    return en if ctx["lang"] == "en" else zh


def sky(film, fx, fy):
    """A point in the sky band: x as a share of the width, y as a share of the space between the top margin and
    the horizon (so charts sit in the sky in both formats)."""
    top = film.H * (0.13 if film.portrait else 0.10)
    return fx * film.W, top + fy * (film.ground - film.height * 1.15 - top)


def label_scale(film):
    """Sky words are drawn larger than their nominal size: 1.5x on the phone (portrait), 1.25x in landscape, so
    they read at a glance on a small screen."""
    return 1.5 if film.portrait else 1.25


def label_width(film, s, size=40):
    """Width in px of a fully shown label (for strike-through lines and the like)."""
    cr = film.cr
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(size * film.u * label_scale(film))
    return cr.text_extents(s).x_advance


def label(film, s, x, y, a, size=40, col=WHITE):
    """Sky text with a dark outline, so it reads on the dark sky and on the light clouds of the colour night.
    It comes in growing a little and rising into place as it fades in."""
    if a <= 0 or not s:
        return
    cr = film.cr
    px = size * film.u * label_scale(film) * (0.88 + 0.12 * a)
    y += (1 - a) * 16 * film.u
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    cr.set_font_size(px)
    ext = cr.text_extents(s)
    cr.move_to(x - ext.x_advance / 2, y + px * 0.35)
    cr.text_path(s)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    cr.set_line_width(px * 0.16)
    cr.set_source_rgba(0.03, 0.04, 0.10, 0.75 * a)
    cr.stroke()
    text(cr, s, px, x, y, col, a=a, weight=1)


def appear(ctx, start=0.2, end=None):
    a = ramp(ctx["lt"], ctx["walk"] + start, ctx["walk"] + start + 0.5)
    return a * (1 - ramp(ctx["lt"], ctx["dur"] - 0.35, ctx["dur"]))


def anchor(film, ctx, fx):
    """Screen x of something standing in the world where fx*W was when the robot arrived in this shot."""
    s = film.shots[ctx["i"]]
    return film.trav(min(s["end"], s["start"] + ctx["walk"])) + fx * film.W - film.trav(ctx["t"])


def anchor_shot(film, ctx, shot_id, fx):
    i = next(k for k, s in enumerate(film.shots) if s["id"] == shot_id)
    s = film.shots[i]
    w = film.beat(i).get("walk", 0.0)
    return film.trav(min(s["end"], s["start"] + w)) + fx * film.W - film.trav(ctx["t"])


def joints(film, q, lift=0.0, x=None):
    """The robot's joints (screen) for pose q, without drawing it."""
    s = film.walker.scale_for(film.height)
    j = film.walker.solve(q)
    x = film.hip_x if x is None else x
    to = lambda p: (x + p[0] * s, film.ground - lift + p[1] * s)
    return {k: (to(v) if isinstance(v, tuple) else [to(p) for p in v] if isinstance(v, list) else v)
            for k, v in j.items()}


def fog(film, cr, ctx, start_fx=0.55, strength=1.0):
    """Soft fog ahead of the robot: wide, flat glowing blobs drifting slowly, no hard edges."""
    import cairo
    a = strength * ramp(ctx["lt"], 0.2, 1.5) * (1 - ramp(ctx["lt"], ctx["dur"] - 0.4, ctx["dur"]))
    if a <= 0:
        return
    for k in range(7):
        cx = film.W * (start_fx + 0.12 * k) + 30 * film.u * math.sin(ctx["t"] * 0.4 + k)
        cy = film.ground - film.height * (0.15 + 0.22 * (k % 4))
        rx = film.W * 0.32
        cr.save()
        cr.translate(cx, cy)
        cr.scale(1, 0.28)
        g = cairo.RadialGradient(0, 0, 0, 0, 0, rx)
        g.add_color_stop_rgba(0, 0.85, 0.9, 1.0, 0.22 * a)
        g.add_color_stop_rgba(1, 0.85, 0.9, 1.0, 0)
        cr.set_source(g)
        cr.arc(0, 0, rx, 0, 2 * math.pi)
        cr.fill()
        cr.restore()




def book(film, cr, J, glow=1.0, tilt=45):
    """An open book held in both hands in front of the chest, tilted `tilt` degrees with its top away from the
    robot so the pages face its eyes: the spine down the middle, a page on each side (turned a little toward the
    viewer so the spread reads), lines of text across the pages.  It is solid: the hands behind it don't show."""
    u = film.height / 300
    hx, hy = film.hand(J)
    a = math.radians(tilt)
    s = (math.cos(a), -math.sin(a))                          # along the spine, bottom -> top
    n = (math.sin(a), math.cos(a))                           # across the spread, as seen from the side
    length, half, dip = 54 * u, 18 * u, 5 * u
    b = (hx - 6 * u, hy + 4 * u)                             # bottom of the spine, resting in the hands
    at = lambda p, k, m: (p[0] + n[0] * k + s[0] * m, p[1] + n[1] * k + s[1] * m)
    sb, st = at(b, 0, dip), at(b, 0, length - dip)          # the spine sinks into the gutter between the pages
    pages = []
    for side in (1, -1):                                     # each page curves up from the spine like a wing
        k = side * half
        pages.append([sb, at(b, k * 0.45, -1 * u), at(b, k, 0), at(b, k, length), at(b, k * 0.45, length + 1 * u), st])
    outline = pages[0][:4] + pages[1][3:0:-1]
    cr.move_to(*outline[0])                                  # solid paper: hides the hands behind it
    for p in outline[1:]:
        cr.line_to(*p)
    cr.close_path()
    cr.set_source_rgb(0.05, 0.06, 0.09)
    cr.fill_preserve()
    cr.set_source_rgba(*ICE, 0.32 * glow)
    cr.fill()
    for side in (1, -1):                                     # text lines across each page
        for j in range(2, 10):
            m = length * j / 11
            glow_line(cr, [at(b, side * half * 0.25, m), at(b, side * half * (0.82 - 0.2 * (j % 3 == 0)), m)], 0.9 * u, WHITE, 0.45,
                      glow=False)
    glow_line(cr, outline + [outline[0]], 2.6 * u, WHITE, 1.0)
    glow_line(cr, [sb, st], 2.2 * u, WHITE, 0.9, glow=False)
    for side in (1, -1):                                     # the cover's thickness under the outer page edge
        k = side * (half + 2.5 * u)
        glow_line(cr, [at(b, k, 1 * u), at(b, k, length + 1 * u)], 1.4 * u, WHITE, 0.6, glow=False)
