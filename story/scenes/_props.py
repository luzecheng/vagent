"""Props shared by several scenes: the stone, a glowing flower, a dark cloud, footprints, a signpost, paper,
and other people (dimmer line figures).  Everything is drawn in the same glowing-white-line language."""
from __future__ import annotations

import math

from .. import hero
from ..stage import GOLD, RED, WHITE, circle, glow_dot, hexc, line, partial


def stone(cr, x, ground, s, a=1.0, glow=0.0, fog=0.0):
    """The recurring stone: a low rounded outline.  `glow` rings it with light, `fog` hides it."""
    if a <= 0:
        return
    w, h = 52 * s, 30 * s
    pts = [(x - w + 2 * w * i / 24, ground - h * math.sin(math.pi * i / 24) ** 0.7 * (1 - 0.12 * math.sin(i)))
           for i in range(25)]
    cr.set_source_rgba(0.75, 0.78, 0.88, 0.16 * a)
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)
    cr.close_path()
    cr.fill()
    line(cr, pts, 3.6 * s, a=a)
    line(cr, [(x - w * 0.35, ground - h * 0.55), (x - w * 0.1, ground - h * 0.7)], 2.2 * s, a=a * 0.6, glow=False)
    if glow > 0:
        for k in range(3):
            circle(cr, x, ground - h * 0.4, (w * 1.15) * (1 + 0.18 * k), 2.4 * s, GOLD, a=a * glow * (0.8 - 0.22 * k))
    if fog > 0:
        for i, (dx, dy, r) in enumerate([(-50, -10, 44), (0, -22, 52), (48, -8, 46), (-14, 6, 40), (24, 4, 38)]):
            cr.set_source_rgba(0.82, 0.85, 0.92, 0.22 * fog)
            cr.arc(x + dx * s, ground + dy * s, r * s, 0, 2 * math.pi)
            cr.fill()


def flower(cr, x, ground, s, grow=1.0, a=1.0):
    """A small glowing flower: the sweet reward of a wrong move."""
    if a <= 0 or grow <= 0:
        return
    top = ground - 46 * s * grow
    line(cr, [(x, ground), (x - 4 * s, ground - 22 * s * grow), (x, top)], 2.6 * s, a=a)
    line(cr, [(x - 2 * s, ground - 18 * s * grow), (x - 14 * s, ground - 26 * s * grow)], 2.2 * s, a=a * 0.8)
    for k in range(5):
        ang = k * 2 * math.pi / 5 + 0.3
        glow_dot(cr, x + math.cos(ang) * 8 * s * grow, top + math.sin(ang) * 8 * s * grow, 4.5 * s * grow,
                 hexc("f6d27a"), a=a, rings=3)
    glow_dot(cr, x, top, 4 * s * grow, GOLD, a=a, rings=10, spread=0.8)


def cloud(cr, x, y, s, a=1.0, dark=1.0):
    """A heavy cloud; `dark` 1 = storm grey, 0 = light."""
    if a <= 0:
        return
    shade = 0.32 + 0.5 * (1 - dark)
    for dx, dy, r in [(-60, 6, 34), (-24, -16, 46), (22, -8, 40), (60, 8, 30), (0, 12, 36)]:
        cr.set_source_rgba(shade, shade * 1.02, shade * 1.12, 0.92 * a)
        cr.arc(x + dx * s, y + dy * s, r * s, 0, 2 * math.pi)
        cr.fill()
    pts = [(x + (-94 + 188 * i / 40) * s, y + (16 + 10 * math.sin(i * 0.9)) * s) for i in range(41)]
    line(cr, pts, 2 * s, a=a * 0.35, glow=False)


def footprints(cr, pts, s, a=1.0, glow=0.0, count=None):
    """Small dashes along a path; `glow` lights them gold."""
    if a <= 0:
        return
    col = GOLD if glow > 0.5 else WHITE
    for i, (x, y) in enumerate(pts[:count]):
        side = 5 * s if i % 2 else -5 * s
        alpha = a * (0.35 + 0.65 * glow)
        line(cr, [(x - 6 * s, y + side), (x + 6 * s, y + side)], 3 * s, col, a=alpha, glow=glow > 0)


def signpost(cr, x, ground, s, rise=1.0, glow=0.0, a=1.0):
    if a <= 0 or rise <= 0:
        return
    h = 120 * s * rise
    line(cr, [(x, ground), (x, ground - h)], 4 * s, a=a)
    if rise > 0.6:
        k = (rise - 0.6) / 0.4
        bx, by = x, ground - h + 18 * s
        board = [(bx - 8 * s, by - 18 * s), (bx + 70 * s * k, by - 18 * s), (bx + 84 * s * k, by),
                 (bx + 70 * s * k, by + 18 * s), (bx - 8 * s, by + 18 * s), (bx - 8 * s, by - 18 * s)]
        if glow > 0:
            cr.set_source_rgba(GOLD[0], GOLD[1], GOLD[2], 0.25 * glow * a)
            cr.move_to(*board[0])
            for p in board[1:]:
                cr.line_to(*p)
            cr.fill()
        line(cr, board, 3.4 * s, GOLD if glow > 0.3 else WHITE, a=a)


def paper(cr, x, ground, s, a=1.0, written=0.0):
    """A sheet on the ground; `written` 0..1 draws handwriting lines on stroke by stroke."""
    if a <= 0:
        return
    w, h = 70 * s, 16 * s
    sheet = [(x - w, ground), (x + w, ground), (x + w * 0.8, ground - h), (x - w * 0.8, ground - h), (x - w, ground)]
    cr.set_source_rgba(1, 1, 1, 0.12 * a)
    cr.move_to(*sheet[0])
    for p in sheet[1:]:
        cr.line_to(*p)
    cr.fill()
    line(cr, sheet, 2.6 * s, a=a)
    rows = 3
    for r in range(rows):
        k = max(0.0, min(1.0, written * rows - r))
        if k <= 0:
            break
        y = ground - h * (0.25 + 0.25 * r)
        x0, x1 = x - w * (0.7 - 0.06 * r), x + w * (0.66 - 0.06 * r)
        pts = [(x0 + (x1 - x0) * i / 30, y + 1.6 * s * math.sin(i * 1.7)) for i in range(31)]
        line(cr, partial(pts, k), 1.8 * s, GOLD, a=a, glow=False)


def person(cr, x, ground, s, a=0.6, pose_name="stand", facing=1, light=0.0, t=0.0):
    """Someone other than the hero: the same line language, dimmer and without the chest light."""
    if a <= 0:
        return None
    return hero.draw(cr, x, ground, hero.pose(pose_name, t), s, facing=facing, light=light, alpha=a)


def flash(cr, x, y, s, a=1.0):
    """A brief red flash: pain."""
    glow_dot(cr, x, y, 7 * s, RED, a=a, rings=10, spread=0.9)
