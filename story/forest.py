"""Forested mountains: a mountain layer whose slopes are covered in trees, pre-rendered once into an image.

forest_mountain_layer() draws a layer's peaks plus a few thousand trees into one cairo ImageSurface wide enough
for any camera travel; every frame only pastes that image at the layer's parallax offset (ForestLayer.paint),
so thousands of trees cost about as much as the plain triangles did.

The look: trees cover each peak right up to the summit, thickest and biggest at the foot, a little thinner and
smaller towards the top so the peak stays pointed; trees along both ridge lines poke their tips above the slope, so a ridge reads
as a saw-tooth of treetops.  Farther layers get smaller trees in colours close to the mountain (air
perspective), nearer ones bigger, darker, higher-contrast trees.  Each tree is lit from the left like the
mountains (light left half, dark right half).  Fixed seeds: every render is identical.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import cairo

from .stage import glow_dot, hexc

WARM = hexc("f0c987")          # a cabin window far off in the woods: warm, small and dim


@dataclass
class Tree:
    x: float
    y: float                   # base of the trunk, local layer coordinates
    h: float
    shade: int                 # index into the layer's tree colours
    round: bool = False


@dataclass
class ForestLayer:
    surface: cairo.ImageSurface
    x0: float                  # local coordinates of the surface's top-left corner
    y0: float
    speed: float               # parallax: screen x = local x - travel * speed
    lift_k: float              # how much the layer slides when the camera tilts up (x sky_shift)
    trees: int
    lights: list = field(default_factory=list)     # (x, y, phase) warm dots, drawn live so they flicker
    sway: list = field(default_factory=list)       # Trees drawn live with a slight wind sway (nearest layer)
    colors: list = field(default_factory=list)
    peaks: list = field(default_factory=list)

    def paint(self, cr, travel: float, sky_shift: float, t: float, u: float) -> None:
        dx, dy = -travel * self.speed, sky_shift * self.lift_k
        cr.set_source_surface(self.surface, self.x0 + dx, self.y0 + dy)
        cr.paint()
        for tr in self.sway:
            off = 1.5 * u * math.sin(t * 1.3 + tr.x * 0.013)
            _tree(cr, tr, self.colors[tr.shade], dx, dy, lean=off)
        for x, y, ph in self.lights:
            k = 0.75 + 0.25 * math.sin(t * 1.1 + ph)
            glow_dot(cr, x + dx, y + dy, 2.6 * u, WARM, a=0.75 * k, rings=5, spread=1.0)


def forest_mountain_layer(peaks, colors, tree_density, tree_scale, seed, *, W, H, horizon, u, speed, lift_k,
                          tree_colors, sway=0, lights=(0, 3)) -> ForestLayer:
    """One mountain layer with its forest, pre-rendered.

    peaks         [(cx, top_fraction_of_H, width)] as Stage._peaks makes them (local coordinates, travel 0)
    colors        (light face, dark face) of the mountains
    tree_density  how many trees cover each bit of slope (1 = edge to edge, 2 = every spot two trees deep)
    tree_scale    average tree height in design px (multiplied by u)
    tree_colors   [(light half, dark half)] 2-3 close shades, picked at random per tree
    horizon       the ground line at lift 0 (trees below it are hidden by the ground anyway)
    sway          how many ridge trees on this layer sway in the wind (drawn live, not baked in)
    lights        (min, max) warm cabin lights in the woods of this layer
    """
    rnd = random.Random(seed)
    unit_w = max(W, H * 0.9) * 0.5
    base = H + 400
    geo = []                                   # (apex x, apex y, half-width at base) per peak
    for cx, top, w in peaks:
        y = top * H
        geo.append((cx, y, (base - y) / 0.62 * min(1.0, w / (unit_w * 0.9))))
    x0 = min(cx - half for cx, y, half in geo) if geo else 0
    x0 = max(x0, -W * 0.8)
    x1 = min(max(cx + half for cx, y, half in geo), W * 4.2) if geo else W
    y0 = min(y for _, y, _ in geo) - tree_scale * u * 2
    y1 = horizon + H * 0.35                    # the camera may look down a little (fork, wall): cover that
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, int(x1 - x0) + 2, int(y1 - y0) + 2)
    cr = cairo.Context(surf)
    cr.translate(-x0, -y0)

    light, dark = colors
    total, live, glows = 0, [], []
    for n, (cx, py, half) in enumerate(geo):
        _tri(cr, [(cx - half, base), (cx, py), (cx, base)], light)
        _tri(cr, [(cx, py), (cx + half, base), (cx, base)], dark)
        height = horizon - py
        if height <= 0:
            continue
        line_y = py + tree_scale * u * 0.15                      # trees right up to the summit
        bottom = min(y1, horizon + H * 0.3)
        trees = _slope_trees(rnd, cx, py, half, base, line_y, bottom, tree_density, tree_scale * u, len(tree_colors))
        trees.sort(key=lambda tr: tr.y)                          # back to front
        later = geo[n + 1:]
        swayers = set()
        if sway:
            ridge = [i for i, tr in enumerate(trees) if tr.y < line_y + height * 0.25 and not _covered(tr, later, base)]
            swayers = set(rnd.sample(ridge, min(len(ridge), max(0, sway // max(1, len(geo)) + rnd.randint(0, 1)))))
        for i, tr in enumerate(trees):
            if i in swayers:
                live.append(tr)
            else:
                _tree(cr, tr, tree_colors[tr.shade])
        total += len(trees)
        glows.append((n, trees, height, line_y))
    lo, hi = lights
    spots = []
    picks = [g for g in glows if g[1]]
    for _ in range(rnd.randint(lo, hi) if picks else 0):
        n, trees, height, line_y = rnd.choice(picks)
        for _ in range(20):                                       # a spot in the woods no nearer peak hides
            tr = rnd.choice(trees)
            if line_y + height * 0.3 < tr.y < horizon - 8 * u and not _covered(tr, geo[n + 1:], base):
                spots.append((tr.x + rnd.uniform(-0.2, 0.2) * tr.h, tr.y - tr.h * 0.3, rnd.uniform(0, 6.28)))
                break
    return ForestLayer(surf, x0, y0, speed, lift_k, total, spots, live, tree_colors, geo)


def _slope_trees(rnd, cx, py, half, base, line_y, bottom, density, size, shades):
    """Trees filling one peak from just under its summit (line_y) down: densest at the foot, plus a row on each
    ridge line."""
    trees = []
    slope = half / (base - py)                                   # half-width grows by this per px downwards
    area = 0.0
    steps = 40
    for i in range(steps):
        y = line_y + (bottom - line_y) * (i + 0.5) / steps
        area += 2 * slope * (y - py) * (bottom - line_y) / steps
    n = int(area * density / (0.45 * size * size))
    for _ in range(n):
        y = line_y + (bottom - line_y) * rnd.random()
        k = (y - line_y) / max(1.0, bottom - line_y)
        if rnd.random() > 0.55 + 0.45 * k ** 0.6:                # a little thinner towards the summit
            continue
        w = slope * (y - py)
        trees.append(_make(rnd, cx + rnd.uniform(-w, w), y, size * _summit(k), shades))
    for side in (-1, 1):                                         # the saw-tooth along each ridge line
        y = line_y + size * rnd.uniform(0.1, 0.4)
        while y < bottom:
            k = (y - line_y) / max(1.0, bottom - line_y)
            h = size * _summit(k) * rnd.uniform(0.8, 1.2)
            trees.append(_make(rnd, cx + side * (slope * (y - py) - h * 0.12), y, size * _summit(k), shades))
            y += h * rnd.uniform(0.28, 0.42) * (1 + (y - line_y) / max(1.0, bottom - line_y))
    return trees


def _summit(k):
    """Trees are smaller near the summit (k = 0) than at the foot (k = 1), so the peak stays pointed."""
    return 0.45 + 0.55 * min(1.0, k * 3)


def _make(rnd, x, y, size, shades):
    return Tree(x, y, size * rnd.uniform(0.7, 1.3), rnd.randrange(shades), rnd.random() < 0.08)


def _covered(tr, later, base):
    """Is the treetop inside a peak drawn after this one (so something drawn live there would show through)?"""
    x, y = tr.x, tr.y - tr.h
    return any(y > py and abs(x - cx) < half * (y - py) / (base - py) for cx, py, half in later)


def _tree(cr, tr, col, dx=0.0, dy=0.0, lean=0.0):
    """A pine (three stacked tiers) or now and then a round-crowned tree; light left half, dark right half."""
    light, dark = col
    x, y, h = tr.x + dx, tr.y + dy, tr.h
    if tr.round:
        r = h * 0.3
        cy = y - h + r
        cr.set_source_rgba(*dark)
        cr.rectangle(x - h * 0.04, cy, h * 0.08, y - cy)
        cr.fill()
        cr.arc(x + lean, cy, r, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(*light)
        cr.arc(x + lean, cy, r, math.pi / 2, math.pi * 1.5)
        cr.close_path()
        cr.fill()
        return
    w = h * 0.36
    for top, bot, spread in ((0.0, 0.45, 0.6), (0.22, 0.72, 0.85), (0.45, 1.0, 1.0)):
        tx, ty, by = x + lean * (1 - top), y - h + h * top, y - h + h * bot
        _tri(cr, [(tx, ty), (x - w * spread, by), (x, by)], light)
        _tri(cr, [(tx, ty), (x, by), (x + w * spread, by)], dark)


def _tri(cr, pts, col):
    cr.set_source_rgba(*col)
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)
    cr.close_path()
    cr.fill()
