"""Roadside scenery: street lamps and benches by the road (the forested mountains behind them are
story/forest.py).  Background only: flat colours and dim white lines, never gold (gold means
something in this world: the hero's light, the lamp, the quotes), drawn under every scene and the hero.

Everything sits at a fixed place in the world, so it slides past as the hero walks with the ground (one px of
travel = one px on screen).  Lamps and benches only stand by the road while the hero walks (a scene with a
`speed`); in a shot where the hero stands still they would sit right behind him or across the scene's object.
A shot can force them on or off with "roadside": true / false in the storyboard.
"""
from __future__ import annotations

import math
import random

from .stage import glow_dot, hexc, line

LAMP_LIGHT = hexc("efe9dc")                   # the moon's colour: a soft white, not gold
PERIOD = 7.0                                  # the roadside pattern repeats every PERIOD frame widths


class Scenery:
    def __init__(self, st, seed: int):
        rnd = random.Random(seed * 31 + 5)
        W = st.W
        span = W * PERIOD
        self.lamps = [W * (0.55 + 1.15 * k) + rnd.uniform(-0.1, 0.1) * W for k in range(int(PERIOD / 1.15))]
        self.benches = [(a + b) / 2 for a, b in zip(self.lamps[1::3], self.lamps[2::3])]
        self.span = span

    # ----- ground -----
    def roadside(self, cr, st, t, alpha=1.0):
        """Lamps and benches standing by the road, behind the hero; `alpha` fades them (0 = hidden)."""
        if alpha <= 0:
            return
        gy, s, travel = st.horizon, st.s, st.cam.travel
        cr.push_group()
        for wx in self.lamps:
            for x in self._on_screen(wx, travel, st.W, 100):
                k = _whole_in_frame(x - 6 * s, x + LAMP_REACH * s, st.W, 40 * s)
                if k > 0:
                    cr.push_group()
                    _street_lamp(cr, x, gy, s, t)
                    cr.pop_group_to_source()
                    cr.paint_with_alpha(k)
        for wx in self.benches:
            for x in self._on_screen(wx, travel, st.W, 100):
                _bench(cr, x, gy, s)
        cr.pop_group_to_source()
        cr.paint_with_alpha(alpha)

    def _on_screen(self, wx, travel, W, size):
        """Screen positions of a thing at world x `wx` (the pattern repeats every `span`) that can be seen."""
        x = (wx - travel) % self.span
        return [p for p in (x, x - self.span) if p + size > -100 and p - 100 < W]


LAMP_REACH = 74              # from the post to the far edge of the lamp glow (arm 34 + glow 38.4), design px


def _whole_in_frame(left, right, W, fade):
    """Opacity for a thing spanning [left, right]: 0 as soon as any part of it is outside the frame, fading up to
    1 over `fade` px as it comes fully inside.  A lamp then never shows as a head without its post (its post has
    left the frame) or a post without its head: it fades out at the edges instead of being cut by them."""
    room = min(left, W - right)
    return max(0.0, min(1.0, room / fade))


def _street_lamp(cr, x, gy, s, t):
    """A thin lamp post with a curved arm; its light is a soft white glow, much dimmer than the hero's lamp."""
    top = gy - 235 * s
    line(cr, [(x, gy), (x, top)], 2.6 * s, a=0.42, glow=False)
    arm = [(x + 34 * s * math.sin(math.pi / 2 * i / 10), top - 14 * s * math.sin(math.pi * i / 10)) for i in range(11)]
    line(cr, arm, 2.4 * s, a=0.42, glow=False)
    hx, hy = arm[-1][0], arm[-1][1] + 6 * s
    line(cr, [(hx - 10 * s, hy), (hx + 10 * s, hy)], 2.4 * s, a=0.5, glow=False)
    flicker = 0.92 + 0.08 * math.sin(t * 2.3 + x * 0.01)
    glow_dot(cr, hx, hy + 6 * s, 6 * s, LAMP_LIGHT, a=0.55 * flicker, rings=6, spread=0.9)
    line(cr, [(x - 9 * s, gy), (x + 9 * s, gy)], 2.6 * s, a=0.42, glow=False)


def _bench(cr, x, gy, s):
    """A plain park bench seen from the side-front: seat, backrest, two pairs of legs."""
    w, seat, back = 64 * s, gy - 34 * s, gy - 66 * s
    a = 0.42
    line(cr, [(x - w, seat), (x + w, seat)], 3.0 * s, a=a, glow=False)
    line(cr, [(x - w, back), (x + w, back)], 2.6 * s, a=a, glow=False)
    line(cr, [(x - w * 0.95, back + 12 * s), (x + w * 0.95, back + 12 * s)], 2.0 * s, a=a * 0.8, glow=False)
    for lx in (-w * 0.82, w * 0.82):
        line(cr, [(x + lx, back), (x + lx, gy)], 2.6 * s, a=a, glow=False)
        line(cr, [(x + lx + (6 * s if lx > 0 else -6 * s), seat), (x + lx + (10 * s if lx > 0 else -10 * s), gy)],
             2.2 * s, a=a * 0.8, glow=False)
