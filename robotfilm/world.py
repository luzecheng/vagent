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
# palettes: "night" is the original blue-black world; "color" is the user's favourite city night in colour.
PALETTES = {
    "night": dict(sky_top=(0.027, 0.039, 0.075), sky_mid=None, sky_low=(0.055, 0.075, 0.13),
                  stars=[(1, 1, 1)], moon=(0.93, 0.95, 1.0), moon_glow=(0.85, 0.9, 1.0),
                  far=(0.045, 0.06, 0.105), near=(0.025, 0.035, 0.065), pine=None,
                  far_line=(1, 1, 1), near_line=(1, 1, 1), pine_line=(1, 1, 1),
                  ground_top=(0.04, 0.055, 0.09), ground_low=(0.008, 0.012, 0.022), sheen=(0.6, 0.75, 1.0),
                  grid=(0.75, 0.88, 1.0)),
    # the user's favourite night (their photo of a city night sky): deep navy sky, a little lighter low down,
    # big soft clouds lit from below to a warm grey-white with blue-grey shading, only a few stars; green hills.
    # The robot stays white; the props are drawn in colour.
    "color": dict(sky_top=(0.06, 0.08, 0.19), sky_mid=(0.12, 0.15, 0.31), sky_low=(0.24, 0.27, 0.42),
                  stars=[(1, 1, 1), (1.0, 0.97, 0.88)], star_share=0.25,
                  moon=(1.0, 0.98, 0.92), moon_glow=(0.85, 0.88, 1.0),
                  clouds=dict(light=(0.88, 0.86, 0.88), shade=(0.36, 0.38, 0.48), cover=0.50, edge=0.16, seed=7),
                  far=(0.15, 0.17, 0.30), near=(0.05, 0.13, 0.11), pine=(0.07, 0.21, 0.14),
                  far_line=(0.70, 0.74, 0.90), near_line=(0.55, 0.82, 0.66), pine_line=(0.58, 0.86, 0.62),
                  ground_top=(0.07, 0.08, 0.10), ground_low=(0.015, 0.018, 0.03), sheen=(1.0, 0.82, 0.55),
                  grid=(0.80, 0.82, 0.90)),
}


def _cloud_layer(w: int, h: int, u: float, cc: dict) -> cairo.ImageSurface:
    """Clouds as a texture, seamless left to right: fractal noise (octaves of smooth random bumps, stretched
    sideways and slanted a little, like windswept clouds), cut by `cover` (more = more sky covered) with an `edge`
    band (smaller = crisper edges, fibrous where the noise is fine).  Thick parts are lit warm grey-white, thin parts
    blue-grey; the clouds thin out toward the top of the frame and toward the hills."""
    import numpy as np
    from scipy import ndimage
    rnd = np.random.default_rng(cc.get("seed", 7))
    sw, sh = w // 2, h // 2                                  # build at half size, scale up when painting
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    dens = np.zeros((sh, sw), np.float32)
    fine = np.zeros((sh, sw), np.float32)                    # the small octaves alone: texture inside the clouds
    amp, total, ftotal = 1.0, 0.0, 0.0
    for k, cells_x in enumerate((5, 11, 23, 47, 95, 190)):   # coarse shapes down to fine fibres
        cells_y = max(2, int(cells_x * sh / sw * 2.4))       # fewer cells across = stretched sideways
        grid = rnd.random((cells_y, cells_x)).astype(np.float32)
        gx = xx / sw * cells_x + (yy / sh) * cells_x * 0.08  # a slight slant
        gy = yy / sh * cells_y
        n = ndimage.map_coordinates(grid, [gy, gx], order=3, mode="grid-wrap")
        dens += amp * n
        total += amp
        if k >= 2:
            fine += amp * n
            ftotal += amp
        amp *= 0.55
    dens /= total
    fine = np.clip((fine / ftotal - 0.5) * 2.2 + 0.5, 0, 1)
    dens = (dens - dens.mean()) / (dens.std() * 3.2) + 0.5  # spread to about 0..1
    band = np.clip((yy / sh - 0.04) / 0.18, 0, 1) * np.clip((0.92 - yy / sh) / 0.30, 0, 1)
    dens = dens * (0.55 + 0.45 * band) - (1 - band) * 0.25
    lo = 1.0 - cc["cover"]
    alpha = np.clip((dens - lo) / cc["edge"], 0, 1)
    alpha = alpha * alpha * (3 - 2 * alpha)
    thick = np.clip((dens - lo) / 0.35, 0, 1)
    lit = np.clip(0.25 + 0.55 * thick + 0.45 * (fine - 0.5), 0, 1)[..., None]   # thick, bumpy parts catch the light
    rgb = np.array(cc["shade"], np.float32) * (1 - lit) + np.array(cc["light"], np.float32) * lit
    a = (alpha * cc.get("opacity", 0.8) * (0.45 + 0.55 * fine) * (0.6 + 0.4 * thick))[..., None]   # thin, see-through
    img = np.dstack([(rgb * a)[..., ::-1], a]) * 255         # premultiplied BGRA for cairo
    small = cairo.ImageSurface.create_for_data(np.ascontiguousarray(img.astype(np.uint8)), cairo.FORMAT_ARGB32,
                                               sw, sh)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    cr = cairo.Context(surf)
    cr.scale(w / sw, h / sh)
    cr.set_source_surface(small, 0, 0)
    cr.get_source().set_filter(cairo.FILTER_GOOD)
    cr.get_source().set_extend(cairo.EXTEND_PAD)
    cr.paint()
    return surf


class World:
    def __init__(self, W: int, H: int, seed: int = 19, palette: str = "night"):
        self.W, self.H = W, H
        self.c = PALETTES[palette]
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
        self.clouds = _cloud_layer(W * 3, int(self.horizon), self.u, self.c["clouds"]) if self.c.get("clouds") else None
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
        c = self.c
        g = cairo.LinearGradient(0, 0, 0, hz)
        g.add_color_stop_rgb(0, *c["sky_top"])
        if c["sky_mid"]:                       # the dusk glow sits just above the far ridge, where it shows
            g.add_color_stop_rgb(0.30, *c["sky_mid"])
            g.add_color_stop_rgb(0.58, *c["sky_low"])
        g.add_color_stop_rgb(1, *c["sky_low"])
        cr.set_source(g)
        cr.rectangle(0, 0, W, hz)
        cr.fill()
        share = c.get("star_share", 1.0)
        for n, (x, y, r, ph) in enumerate(self.stars):
            sx = (x - travel * 0.03) % (W * 3)
            if sx < W and (n % 100) < share * 100:
                a = 0.35 + 0.35 * (0.5 + 0.5 * math.sin(t * 1.7 + ph))
                a *= 1 - 0.7 * min(1.0, max(0.0, y / hz - 0.3) / 0.3) if c["sky_mid"] else 1   # fainter in the dusk glow
                cr.arc(sx, y, r, 0, 2 * math.pi)
                cr.set_source_rgba(*c["stars"][n % len(c["stars"])], a)
                cr.fill()
        mx, my = W * 0.72, hz * 0.22
        for k in range(6, 0, -1):
            cr.arc(mx, my, 34 * u * (1 + k * 0.45), 0, 2 * math.pi)
            cr.set_source_rgba(*c["moon_glow"], 0.035)
            cr.fill()
        cr.arc(mx, my, 34 * u, 0, 2 * math.pi)
        cr.set_source_rgba(*c["moon"], 0.95)
        cr.fill()
        if self.clouds is not None:
            self._clouds(cr, travel, t, c["clouds"])
        self._layer(cr, self.far, travel, c["far"], c["far_line"], 0.22, pines=False)
        self._layer(cr, self.near, travel, c["near"], c["near_line"], 0.42, pines=True)
        self._ground(cr, travel)
        st = SimpleNamespace(W=W, horizon=hz, s=self.s, cam=SimpleNamespace(travel=travel))
        self.props.roadside(cr, st, t, 1.0)

    def _clouds(self, cr, travel, t, cc):
        """The cloud texture, drifting left and scrolling a little with the walk; it wraps every 3 frame widths."""
        span = self.W * 3
        off = (travel * 0.06 + t * 5 * self.u) % span
        for x in (-off, span - off):
            if x < self.W and x + span > 0:
                cr.set_source_surface(self.clouds, x, 0)
                cr.paint()

    def _layer(self, cr, ridge, travel, fill, line, line_a, pines):
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
                    cr.set_source_rgb(*(self.c["pine"] or fill))
                    cr.fill_preserve()
                    cr.set_line_width(1.4 * u)
                    cr.set_source_rgba(*self.c["pine_line"], line_a * 0.8)
                    cr.stroke()
        cr.move_to(*top[0])
        for p in top[1:]:
            cr.line_to(*p)
        cr.set_line_width(1.6 * u)
        cr.set_source_rgba(*line, line_a)
        cr.stroke()

    def _ground(self, cr, travel):
        W, H, hz, u, c = self.W, self.H, self.horizon, self.u, self.c
        g = cairo.LinearGradient(0, hz, 0, H)
        g.add_color_stop_rgb(0, *c["ground_top"])
        g.add_color_stop_rgb(1, *c["ground_low"])
        cr.set_source(g)
        cr.rectangle(0, hz, W, H - hz)
        cr.fill()
        # soft sheen just below the horizon, under the moon's side of the sky
        cr.save()
        cr.translate(W * 0.5, hz)
        cr.scale(1, 0.22)                                   # a flat ellipse: no hard edges
        sh = cairo.RadialGradient(0, 0, 0, 0, 0, W * 0.6)
        sh.add_color_stop_rgba(0, *c["sheen"], 0.12)
        sh.add_color_stop_rgba(1, *c["sheen"], 0)
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
        cr.set_source_rgba(*c["grid"], 0.07)
        cr.stroke()
        # cross lines, closer together toward the horizon
        for k in range(1, 9):
            y = hz + (H - hz) * (k / 9) ** 2.2
            cr.move_to(0, y)
            cr.line_to(W, y)
        cr.set_source_rgba(*c["grid"], 0.05)
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
