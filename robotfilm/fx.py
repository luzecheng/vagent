"""Shared helpers for robot-story beats (episode files robot2/beats.py): poses, sky placement, labels, timing,
anchoring things in the world, the robot's joints, fog."""
import math

from robotfilm.robot_story import ICE, coin, coin_stack, glow_line, orb, smooth
from robotfilm.walker import STAND
from story.stage import GOLD, WHITE, ramp, text

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


def label(film, s, x, y, a, size=40, col=WHITE):
    text(film.cr, s, size * film.u, x, y, col, a=a, weight=1)


def appear(ctx, start=0.2, end=None):
    a = ramp(ctx["lt"], ctx["walk"] + start, ctx["walk"] + start + 0.5)
    return a * (1 - ramp(ctx["lt"], ctx["dur"] - 0.35, ctx["dur"]))


def anchor(film, ctx, fx):
    """Screen x of something standing in the world where fx*W was when the robot arrived in this shot."""
    s = film.shots[ctx["i"]]
    return film.trav(s["start"] + ctx["walk"]) + fx * film.W - film.trav(ctx["t"])


def anchor_shot(film, ctx, shot_id, fx):
    i = next(k for k, s in enumerate(film.shots) if s["id"] == shot_id)
    s = film.shots[i]
    w = film.beat(i).get("walk", 0.0)
    return film.trav(s["start"] + w) + fx * film.W - film.trav(ctx["t"])


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


