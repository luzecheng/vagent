"""The robot's world: a night landscape in the robot's own style — dark blue-black silhouettes with thin white
outlines (no green, no grain), a dark ground in perspective with faint receding lines and a soft sheen, stars, the
moon, and the street lamps of story/scenery.py.

Everything scrolls with `travel` (px the camera has moved): far ridge, near ridge with pines, ground lines and
lamps at different speeds, so walking reads as moving through the place.  The horizon (the robot's ground line)
is at HORIZON of the frame height.
"""
from __future__ import annotations

import math
import random
from types import SimpleNamespace

import cairo

from story.scenery import Scenery

HORIZON = 0.68
SKY_TOP, SKY_LOW = (0.027, 0.039, 0.075), (0.055, 0.075, 0.13)
FAR, NEAR = (0.045, 0.06, 0.105), (0.025, 0.035, 0.065)


class World:
    def __init__(self, W: int, H: int, seed: int = 19):
        self.W, self.H = W, H
        self.u = min(W, H) / 1080
        self.horizon = H * HORIZON
        self.s = 1.9 * self.u if H > W else 1.5 * self.u          # same prop scale as the story world
        rnd = random.Random(seed)
        span = W * 3
        self.stars = [(rnd.uniform(0, span), rnd.uniform(0, self.horizon * 0.85), rnd.uniform(0.6, 1.8) * self.u,
                       rnd.uniform(0, 6.3)) for _ in range(260)]
        self.far = self._ridge(rnd, 0.20, 0.30, 0.09, 26)
        self.near = self._ridge(rnd, 0.06, 0.13, 0.30, 18)
        self.pines = [(rnd.uniform(0, 1), rnd.uniform(0.6, 1.3)) for _ in range(120)]
        self.props = Scenery(SimpleNamespace(W=W), seed)

    def _ridge(self, rnd, lo, hi, speed, n):
        """A looping ridge line: n points over one repeat (3 frame widths), heights as fractions of the frame."""
        pts = [rnd.uniform(lo, hi) for _ in range(n)]
        return {"h": pts, "speed": speed}

    def _ridge_y(self, ridge, X):
        """Height of a ridge (px above the horizon) at world x X; linear between its peaks, looping."""
        span, h = self.W * 3, ridge["h"]
        f = (X % span) / span * len(h)
        i = int(f)
        k = f - i
        return (h[i] * (1 - k) + h[(i + 1) % len(h)] * k) * self.H

    def draw(self, cr, travel: float, t: float) -> None:
        W, H, hz, u = self.W, self.H, self.horizon, self.u
        g = cairo.LinearGradient(0, 0, 0, hz)
        g.add_color_stop_rgb(0, *SKY_TOP)
        g.add_color_stop_rgb(1, *SKY_LOW)
        cr.set_source(g)
        cr.rectangle(0, 0, W, hz)
        cr.fill()
        for x, y, r, ph in self.stars:
            sx = (x - travel * 0.03) % (W * 3)
            if sx < W:
                a = 0.35 + 0.35 * (0.5 + 0.5 * math.sin(t * 1.7 + ph))
                cr.arc(sx, y, r, 0, 2 * math.pi)
                cr.set_source_rgba(1, 1, 1, a)
                cr.fill()
        mx, my = W * 0.72, hz * 0.22
        for k in range(6, 0, -1):
            cr.arc(mx, my, 34 * u * (1 + k * 0.45), 0, 2 * math.pi)
            cr.set_source_rgba(0.85, 0.9, 1.0, 0.035)
            cr.fill()
        cr.arc(mx, my, 34 * u, 0, 2 * math.pi)
        cr.set_source_rgba(0.93, 0.95, 1.0, 0.95)
        cr.fill()
        self._layer(cr, self.far, travel, FAR, 0.22, pines=False)
        self._layer(cr, self.near, travel, NEAR, 0.42, pines=True)
        self._ground(cr, travel)
        st = SimpleNamespace(W=W, horizon=hz, s=self.s, cam=SimpleNamespace(travel=travel))
        self.props.roadside(cr, st, t, 1.0)

    def _layer(self, cr, ridge, travel, fill, line_a, pines):
        W, hz, u = self.W, self.horizon, self.u
        off = travel * ridge["speed"]
        xs = [x * 6 for x in range(int(W / 6) + 2)]
        top = [(x, hz - self._ridge_y(ridge, x + off)) for x in xs]
        cr.move_to(0, hz + 2)
        for p in top:
            cr.line_to(*p)
        cr.line_to(W, hz + 2)
        cr.close_path()
        cr.set_source_rgb(*fill)
        cr.fill()
        if pines:   # small pine silhouettes standing along the ridge
            span = W * 3
            for f, size in self.pines:
                X = f * span
                x = (X - off) % span
                if -40 * u < x < W + 40 * u:
                    y = hz - self._ridge_y(ridge, X)
                    h = 46 * u * size
                    tri = [(x, y - h), (x - h * 0.32, y + 2), (x + h * 0.32, y + 2)]
                    cr.move_to(*tri[0])
                    for p in tri[1:]:
                        cr.line_to(*p)
                    cr.close_path()
                    cr.set_source_rgb(*fill)
                    cr.fill_preserve()
                    cr.set_line_width(1.4 * u)
                    cr.set_source_rgba(1, 1, 1, line_a * 0.8)
                    cr.stroke()
        cr.move_to(*top[0])
        for p in top[1:]:
            cr.line_to(*p)
        cr.set_line_width(1.6 * u)
        cr.set_source_rgba(1, 1, 1, line_a)
        cr.stroke()

    def _ground(self, cr, travel):
        W, H, hz, u = self.W, self.H, self.horizon, self.u
        g = cairo.LinearGradient(0, hz, 0, H)
        g.add_color_stop_rgb(0, 0.04, 0.055, 0.09)
        g.add_color_stop_rgb(1, 0.008, 0.012, 0.022)
        cr.set_source(g)
        cr.rectangle(0, hz, W, H - hz)
        cr.fill()
        # soft sheen just below the horizon, under the moon's side of the sky
        cr.save()
        cr.translate(W * 0.5, hz)
        cr.scale(1, 0.22)                                   # a flat ellipse: no hard edges
        sh = cairo.RadialGradient(0, 0, 0, 0, 0, W * 0.6)
        sh.add_color_stop_rgba(0, 0.6, 0.75, 1.0, 0.12)
        sh.add_color_stop_rgba(1, 0.6, 0.75, 1.0, 0)
        cr.set_source(sh)
        cr.rectangle(-W, 0, 2 * W, W)
        cr.fill()
        cr.restore()
        # receding lines toward a vanishing point on the horizon; they slide with the walk
        vp = W * 0.5
        spacing = 140 * u
        first = -((travel % spacing))
        x = first - W
        while x < W * 2:
            cr.move_to(vp + (x - vp) * 0.06, hz)
            cr.line_to(x + (x - vp) * 1.2, H)
            x += spacing
        cr.set_line_width(1.2 * u)
        cr.set_source_rgba(0.75, 0.88, 1.0, 0.07)
        cr.stroke()
        # cross lines, closer together toward the horizon
        for k in range(1, 9):
            y = hz + (H - hz) * (k / 9) ** 2.2
            cr.move_to(0, y)
            cr.line_to(W, y)
        cr.set_source_rgba(0.75, 0.88, 1.0, 0.05)
        cr.stroke()
        cr.move_to(0, hz)
        cr.line_to(W, hz)
        cr.set_line_width(1.8 * u)
        cr.set_source_rgba(1, 1, 1, 0.35)
        cr.stroke()


class StoryWorld:
    """The 「一笔」 story world (story/stage.py): night sky with stars and moon, forested mountains in layers,
    street lamps and benches — with the same interface as World (horizon, draw(cr, travel, t))."""

    PORTRAIT_HORIZON = 0.755       # the portrait story world's ground sits at 64%: lower it, mountains larger

    def __init__(self, W: int, H: int, seed: int = 19):
        from story.stage import Stage
        self.W, self.H = W, H
        self.st = Stage(W, H, seed=seed, scenery=True)
        # portrait: the whole world is scaled up about the top centre so the ground line comes down to
        # PORTRAIT_HORIZON; mountains, trees and lamps grow by the same factor (taller next to the robot)
        self.k = self.PORTRAIT_HORIZON * H / self.st.horizon if H > W else 1.0
        self.horizon = self.st.horizon * self.k
        self.s = self.st.s * self.k

    def draw(self, cr, travel: float, t: float) -> None:
        from story.stage import Camera
        self.st.cam = Camera(travel=travel / self.k)   # on screen the ground still moves exactly `travel` px
        self.st.t = t
        cr.save()
        cr.translate(self.W / 2, 0)
        cr.scale(self.k, self.k)
        cr.translate(-self.W / 2, 0)
        self.st.draw_world(cr, t)
        cr.restore()
