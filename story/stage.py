"""The shared world every shot is drawn in: night sky, stars, moon, three mountain layers and the ground.

Coordinates: `u` is one design pixel (the frame's short side / 1080), so a scene written once works for
1920×1080 and 1080×1920.  The camera has three values that every shot eases between, which is what makes
the video one continuous take:
  lift   0 = looking along the ground, 1 = looking up into the sky (the world slides down)
  zoom   1 = normal; < 1 pulls back
  travel how far the walker has gone; mountains and stars scroll at different speeds (parallax)
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random

import cairo


def hexc(h: str, a: float = 1.0) -> tuple[float, float, float, float]:
    h = h.lstrip("#")
    return int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a


SKY_TOP, SKY_BOT = hexc("141b2c"), hexc("2b3550")
GOLD = hexc("f2c14e")
WHITE = (1.0, 1.0, 1.0, 1.0)
RED = hexc("e5645a")
M_FAR, M_MID, M_NEAR = (hexc("6f6a80"), hexc("5a566c")), (hexc("8f8a9e"), hexc("74708a")), (hexc("3a4058"), hexc("30354a"))
GROUND = hexc("262b3d")
# Cairo's toy text API on this Mac does not resolve the installed Noto Sans CJK
# family correctly and falls back to tofu boxes. Use the system CJK family,
# which renders Chinese glyphs reliably in the story renderer.
FONT = "PingFang SC"


# ---------- easing ----------
def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def ease(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


def ramp(t: float, a: float, b: float) -> float:
    """0 before a, 1 after b, smooth in between."""
    return ease((t - a) / (b - a)) if b > a else float(t >= a)


def window(t: float, a: float, b: float, f: float = 0.15) -> float:
    """Fade in over [a, a+f], hold, fade out over [b-f, b]."""
    return ramp(t, a, a + f) * (1 - ramp(t, b - f, b))


def lerp(a: float, b: float, k: float) -> float:
    return a + (b - a) * k


# ---------- drawing helpers ----------
def glow_dot(cr, x, y, r, col=GOLD, a=1.0, rings=8, spread=0.6):
    if a <= 0:
        return
    for k in range(rings, 0, -1):
        cr.set_source_rgba(col[0], col[1], col[2], 0.05 * a)
        cr.arc(x, y, r * (1 + k * spread), 0, 2 * math.pi)
        cr.fill()
    cr.set_source_rgba(col[0], col[1], col[2], a)
    cr.arc(x, y, r, 0, 2 * math.pi)
    cr.fill()


def line(cr, pts, width, col=WHITE, a=1.0, glow=True):
    """A glowing white stroke through the points: the look of every line in the video."""
    if a <= 0 or len(pts) < 2:
        return
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    halos = ((width * 3.2, 0.05), (width * 2.0, 0.09)) if glow else ()
    for w, alpha in (*halos, (width, 1.0)):
        cr.set_source_rgba(col[0], col[1], col[2], alpha * a * col[3])
        cr.set_line_width(w)
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        cr.stroke()


def circle(cr, x, y, r, width, col=WHITE, a=1.0, glow=True):
    if a <= 0:
        return
    halos = ((width * 3.2, 0.05), (width * 2.0, 0.09)) if glow else ()
    for w, alpha in (*halos, (width, 1.0)):
        cr.set_source_rgba(col[0], col[1], col[2], alpha * a * col[3])
        cr.set_line_width(w)
        cr.new_sub_path()
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.stroke()


def partial(pts, frac):
    """The first `frac` (0..1) of a polyline, by length: for lines that draw themselves on."""
    if frac <= 0 or len(pts) < 2:
        return pts[:1]
    seg = [0.0]
    for i in range(1, len(pts)):
        seg.append(seg[-1] + math.dist(pts[i - 1], pts[i]))
    length = seg[-1] * clamp(frac)
    out = [pts[0]]
    for i in range(1, len(pts)):
        if seg[i] <= length:
            out.append(pts[i])
        else:
            r = (length - seg[i - 1]) / max(1e-9, seg[i] - seg[i - 1])
            out.append((lerp(pts[i - 1][0], pts[i][0], r), lerp(pts[i - 1][1], pts[i][1], r)))
            break
    return out


def text(cr, s, size, cx, cy, col=WHITE, a=1.0, weight=cairo.FONT_WEIGHT_NORMAL, glow=0.0, shadow=True):
    """Centred text; `glow` > 0 adds the soft halo used for the gold quote."""
    if a <= 0 or not s:
        return
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    ext = cr.text_extents(s)
    x, y = cx - ext.x_advance / 2, cy + size * 0.35
    if glow > 0:
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        for k in range(10, 0, -1):
            cr.move_to(x, y)
            cr.text_path(s)
            cr.set_line_width(k * size * 0.045)
            cr.set_source_rgba(col[0], col[1], col[2], 0.035 * glow * a)
            cr.stroke()
    if shadow:
        cr.move_to(x + size * 0.03, y + size * 0.03)
        cr.set_source_rgba(0, 0, 0, 0.4 * a)
        cr.show_text(s)
    cr.move_to(x, y)
    cr.set_source_rgba(col[0], col[1], col[2], col[3] * a)
    cr.show_text(s)


def text_runs(cr, parts, size, cx, cy, a=1.0, outline=0.0):
    """Centred text in coloured runs [(text, colour)], e.g. a subtitle with gold keywords.  `outline` (a fraction
    of the size) draws a dark edge round the letters so they stay readable over bright parts of the picture."""
    if a <= 0 or not parts:
        return
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    cr.set_font_size(size)
    x, y = cx - sum(cr.text_extents(s).x_advance for s, _ in parts) / 2, cy + size * 0.35
    if outline > 0:
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        cr.move_to(x, y)
        for s, _ in parts:
            cr.text_path(s)
        cr.set_line_width(outline * size)
        cr.set_source_rgba(0.04, 0.05, 0.09, 0.62 * a)
        cr.stroke()
    cr.move_to(x, y)
    for s, col in parts:
        cr.set_source_rgba(col[0], col[1], col[2], col[3] * a)
        cr.show_text(s)


def text_width(cr, s, size, weight=cairo.FONT_WEIGHT_NORMAL) -> float:
    cr.select_font_face(FONT, cairo.FONT_SLANT_NORMAL, weight)
    cr.set_font_size(size)
    return cr.text_extents(s).x_advance


# ---------- the world ----------
@dataclass
class Camera:
    lift: float = 0.0
    zoom: float = 1.0
    travel: float = 0.0


@dataclass
class Stage:
    W: int
    H: int
    seed: int = 7
    cam: Camera = field(default_factory=Camera)
    scenery: bool = False          # forested mountains, street lamps and benches (forest.py, scenery.py)
    roadside: float = 1.0          # lamps and benches opacity for the current frame, set by the film

    def __post_init__(self):
        self.u = min(self.W, self.H) / 1080
        self.portrait = self.H > self.W
        self.s = (1.5 if not self.portrait else 1.9) * self.u   # hero scale
        self.hx = self.W * (0.36 if not self.portrait else 0.30)  # where the hero usually stands
        self.v = 135 * self.s                                  # walking speed, px per second
        self.t = 0.0                                           # global time, set per frame
        self.local = 0.0                                       # distance walked since the shot began, px
        rnd = random.Random(self.seed)
        span = self.W * 3
        # stars live in a tall band above the horizon so the camera can look up into them
        self.stars = [(rnd.uniform(0, span), rnd.uniform(-self.H * 1.1, self.H * 0.62), rnd.uniform(0.7, 2.0) * self.u,
                       rnd.uniform(0, 6.28), rnd.uniform(0.5, 1.8)) for _ in range(int(420 * span / 3840 * 2))]
        self.layers = [self._peaks(rnd, 0.50, 0.60, 0.33, 0.50, M_FAR, 0.10),
                       self._peaks(rnd, 0.58, 0.67, 0.28, 0.42, M_MID, 0.25)]
        if self.scenery:
            from .scenery import Scenery
            self.props = Scenery(self, self.seed)
            self.forest = self._forest()

    def _forest(self):
        """The mountain layers covered in trees (story/forest.py), far to near, plus a low wooded ridge."""
        from .forest import forest_mountain_layer
        hf, k = self.horizon / self.H, min(self.W, self.H) / self.H        # near hills as tall in both formats
        near = self._peaks(random.Random(self.seed + 1), hf - 0.12 * k, hf - 0.06 * k, 0.2, 0.32, M_NEAR, 0.45)
        specs = [  # layer, lift, tree height (design px), density, tree colours (light half, dark half), swaying trees
            (self.layers[0], 0.80, 16, 1.8, ["55606a/434c57", "515d64/3f4952", "59646d/47505a"], 0),
            (self.layers[1], 0.90, 26, 1.8, ["47584f/34433c", "42524b/313e38", "4c5d54/384740"], 0),
            (near, 0.95, 40, 1.6, ["3f7353/24493a", "386a4c/1f4133", "468059/295240"], 12),
        ]
        out = []
        for k, ((peaks, cols, speed), lift_k, size, density, shades, sway) in enumerate(specs):
            out.append(forest_mountain_layer(
                peaks, cols, density, size, self.seed * 7 + k, W=self.W, H=self.H, horizon=self.horizon, u=self.u,
                speed=speed, lift_k=lift_k, sway=sway, lights=(0, 3),
                tree_colors=[tuple(hexc(c) for c in pair.split("/")) for pair in shades]))
        return out

    def _peaks(self, rnd, ymin, ymax, wmin, wmax, cols, speed):
        peaks, x = [], -self.W * 0.3
        unit = max(self.W, self.H * 0.9)
        while x < self.W * 3.3:
            w = rnd.uniform(wmin, wmax) * unit
            peaks.append((x + w / 2, rnd.uniform(ymin, ymax), w))
            x += w * rnd.uniform(0.45, 0.75)
        return peaks, cols, speed

    @property
    def horizon(self) -> float:
        """Ground line (y) at the current camera lift: the hero's feet."""
        return self.H * (0.78 if not self.portrait else 0.64) + self.cam.lift * self.H * 0.95

    @property
    def sky_shift(self) -> float:
        return self.cam.lift * self.H * 0.95

    def draw_world(self, cr, t: float) -> None:
        W, H, cam = self.W, self.H, self.cam
        g = cairo.LinearGradient(0, 0, 0, H)
        g.add_color_stop_rgba(0, *SKY_TOP)
        g.add_color_stop_rgba(1, *SKY_BOT)
        cr.set_source(g)
        cr.paint()
        span = W * 3
        for x, y, r, ph, sp in self.stars:
            sx = (x - cam.travel * 0.04 - t * 1.5 * self.u) % span - W * 0.5
            sy = y + self.sky_shift * 0.6
            if -10 < sx < W + 10 and -10 < sy < H + 10:
                a = 0.35 + 0.65 * (0.5 + 0.5 * math.sin(t * sp + ph))
                cr.set_source_rgba(1, 1, 1, a * 0.8)
                cr.arc(sx, sy, r, 0, 2 * math.pi)
                cr.fill()
        mx, my = W * (0.84 if not self.portrait else 0.78), H * (0.13 if not self.portrait else 0.16) + self.sky_shift * 0.55
        glow_dot(cr, mx - cam.travel * 0.02, my, 34 * self.u, hexc("efe9dc"), rings=6, spread=0.5)
        unit_w = max(W, H * 0.9) * 0.5
        for layer in (self.forest if self.scenery else []):
            layer.paint(cr, cam.travel, self.sky_shift, t, self.u)
        for (peaks, (light, dark), speed) in ([] if self.scenery else self.layers):
            dy = self.sky_shift * (0.8 if speed < 0.2 else 0.9)
            for cx, top, w in peaks:          # peaks cover 3.6 widths: enough for any walk in one video
                x = cx - cam.travel * speed
                y = top * H + dy
                base = H + dy + 400
                half = (base - y) / 0.62 * min(1.0, w / (unit_w * 0.9))   # gentle slopes, as in the sample
                if x + half < -50 or x - half > W + 50:
                    continue
                _tri(cr, [(x - half, base), (x, y), (x, base)], light)
                _tri(cr, [(x, y), (x + half, base), (x, base)], dark)
        # ground: a low dark hill the hero walks on, with a faint path line
        gy = self.horizon
        cr.set_source_rgba(*GROUND)
        cr.rectangle(-W, gy, W * 3, H * 2)
        cr.fill()
        cr.set_source_rgba(1, 1, 1, 0.18)
        cr.set_line_width(1.6 * self.u)
        cr.move_to(-W, gy)
        cr.line_to(W * 2, gy)
        cr.stroke()
        if self.scenery:
            self.props.roadside(cr, self, t, self.roadside)


def _tri(cr, pts, col):
    cr.set_source_rgba(*col)
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)
    cr.close_path()
    cr.fill()
