"""The robot walking in side view: a cut-out puppet from a side parts sheet, with its own walk cycle.

Differences from puppet.py (the first try):
- parts are drawn the way the character sheet looks on black: outlines solid, the dark inside of each plate
  partly see-through, so the robot reads as white glowing lines, not as dark solid shapes; the far arm and leg
  are the same lines, a little dimmer;
- the arm length is set in code: with the arms hanging, the fingertips end at the middle of the thigh (the
  parts are stretched or shortened along their length only, never made thinner);
- the walk is eight key poses (contact, down, passing, up, then the same with the legs swapped), blended with
  smooth steps.  The lowest foot is put on the ground every frame, so the body rises at "passing" and dips at
  "down" by itself, and the ground scrolls exactly as fast as the planted foot moves back: the feet don't slide.

Side parts sheet: top row head, torso; bottom row upper arm, forearm, hand, thigh, shin, foot (all facing right,
limbs vertical with the end nearer the body on top) — tests/robot-puppet/prompts/04_侧面零件图.txt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cairo
import numpy as np
from PIL import Image
from scipy import ndimage

from .puppet import ICE, _cap, _surface

SIDE = ["head", "torso", "upper", "fore", "hand", "thigh", "shin", "foot"]
KEYS = ("lean", "head", "ua_f", "la_f", "ua_b", "la_b", "th_f", "sh_f", "th_b", "sh_b", "ft_f", "ft_b")


@dataclass
class Part:
    surf: cairo.ImageSurface
    dim: cairo.ImageSurface
    top: tuple
    bottom: tuple
    w: int
    h: int
    sole: tuple = ()               # (heel, toe) points of the sole, foot part only

    @property
    def length(self):
        return math.dist(self.top, self.bottom)


def cutout(rgb: np.ndarray, label_mask: np.ndarray | None = None, inside=0.62):
    """Alpha for a drawing on black: 1 on the bright lines and their glow, `inside` on the dark inside of the
    filled silhouette (a little of the world shows through, like the character sheet on black), 0 outside."""
    lum = rgb.max(2)
    solid = ndimage.binary_fill_holes(ndimage.binary_closing(lum > 22, iterations=4))
    if label_mask is not None:
        solid &= label_mask
    line = np.clip(lum / 140.0, 0, 1)
    soft = ndimage.gaussian_filter(solid.astype(np.float32), 1.0)
    near = ndimage.binary_dilation(solid, iterations=10) if label_mask is None else label_mask
    return np.maximum(soft * (inside + (1 - inside) * line), line * near).clip(0, 1)


def load_side_parts(sheet: Path) -> dict[str, Part]:
    a = np.asarray(Image.open(sheet).convert("RGB")).astype(np.float32)
    lum = a.max(2)
    solid = ndimage.binary_fill_holes(ndimage.binary_closing(lum > 22, iterations=4))
    lab, _ = ndimage.label(ndimage.binary_dilation(solid, iterations=6))
    boxes = [(sl, i) for i, sl in enumerate(ndimage.find_objects(lab), 1)
             if (sl[0].stop - sl[0].start) * (sl[1].stop - sl[1].start) > 2000]
    if len(boxes) != len(SIDE):
        raise ValueError(f"side parts sheet: found {len(boxes)} parts, expected {len(SIDE)}")
    mid = a.shape[0] / 2
    rows = [sorted([b for b in boxes if (b[0][0].start + b[0][0].stop) / 2 < mid], key=lambda b: b[0][1].start),
            sorted([b for b in boxes if (b[0][0].start + b[0][0].stop) / 2 >= mid], key=lambda b: b[0][1].start)]
    parts = {}
    for name, (sl, i) in zip(SIDE, rows[0] + rows[1]):
        pad = 10
        y0, y1 = max(0, sl[0].start - pad), min(a.shape[0], sl[0].stop + pad)
        x0, x1 = max(0, sl[1].start - pad), min(a.shape[1], sl[1].stop + pad)
        mine = lab[y0:y1, x0:x1] == i
        m = (solid & (lab == i))[y0:y1, x0:x1]
        rgb = a[y0:y1, x0:x1]
        alpha = cutout(rgb, mine)
        sole = ()
        if name == "foot":
            ys, xs = np.where(m)
            low = ys >= ys.max() - 6
            sole = ((float(xs[low].min()), float(ys.max())), (float(xs[low].max()), float(ys.max())))
        parts[name] = Part(_surface(rgb, alpha), _surface(rgb * 0.62, alpha * 0.85), _cap(m, True), _cap(m, False),
                           x1 - x0, y1 - y0, sole)
    return parts


# ---------- the walk ----------
def _key(lean, ua_f, la_f, ua_b, la_b, th_f, sh_f, th_b, sh_b, ft_f, ft_b):
    return dict(lean=lean, head=0, ua_f=ua_f, la_f=la_f, ua_b=ua_b, la_b=la_b,
                th_f=th_f, sh_f=sh_f, th_b=th_b, sh_b=sh_b, ft_f=ft_f, ft_b=ft_b)


# Angles in degrees from straight down, positive = forward (the way the robot faces); ft = foot tip (positive =
# heel up, toe down).  "f" is the near limb.  Arms swing against the leg on the same side.
HALF = [
    _key(4, -16, -8, 16, 28, 22, 19, -18, -29, -8, 20),     # 1 contact: near heel down in front, far toe behind
    _key(5, -10, -2, 10, 20, 16, 2, -16, -46, 0, 34),       # 2 down: near foot flat, knee bent, far heel up
    _key(4, 0, 6, 0, 10, 0, -4, 20, -46, 0, 18),            # 3 passing: far leg lifted, knee bent, swinging by
    _key(4, 10, 20, -10, -2, -11, -13, 27, 10, 14, -4),     # 4 up: far leg reaching forward, near on its toes
]


def _swap(k):
    s = dict(k)
    for a, b in (("ua_f", "ua_b"), ("la_f", "la_b"), ("th_f", "th_b"), ("sh_f", "sh_b"), ("ft_f", "ft_b")):
        s[a], s[b] = k[b], k[a]
    return s


CYCLE = HALF + [_swap(k) for k in HALF]
STAND = _key(2, 2, 6, -2, 2, 2, 0, -2, -2, 0, 0)
PERIOD = 1.15          # seconds per full cycle (two steps)


def blend(a: dict, b: dict, k: float) -> dict:
    return {key: a[key] + (b[key] - a[key]) * k for key in KEYS}


def walk_pose(t: float) -> dict:
    f = (t / PERIOD % 1.0) * len(CYCLE)
    i = int(f)
    k = f - i
    k = k * k * (3 - 2 * k)
    return blend(CYCLE[i], CYCLE[(i + 1) % len(CYCLE)], k)


class Walker:
    def __init__(self, parts: dict[str, Part], finger_at=0.5):
        self.p = parts
        P = parts
        self.thigh, self.shin = P["thigh"].length, P["shin"].length
        self.torso = P["torso"].length
        self.foot_h = P["foot"].h - P["foot"].top[1] - 10
        self.head_len = P["head"].length
        # arms: shoulder sits 12% below the top of the torso; fingertips at `finger_at` of the thigh, arms hanging
        shoulder_drop = self.torso * 0.88
        reach = shoulder_drop + self.thigh * finger_at
        natural = P["upper"].length + P["fore"].length + P["hand"].length
        self.arm_k = reach / natural
        self.upper, self.fore = P["upper"].length * self.arm_k, P["fore"].length * self.arm_k
        self.hand = P["hand"].length * self.arm_k
        self.stand_h = self.thigh + self.shin + self.foot_h + self.torso + P["head"].h * 0.97

    def solve(self, q):
        lean = math.radians(q["lean"])
        up = (math.sin(lean), -math.cos(lean))
        neck = (self.torso * up[0], self.torso * up[1])
        sh = (neck[0] - up[0] * self.torso * 0.12, neck[1] - up[1] * self.torso * 0.12)

        def chain(o, segs):
            pts = [o]
            x, y = o
            for length, ang in segs:
                r = math.radians(ang)
                x += length * math.sin(r)
                y += length * math.cos(r)
                pts.append((x, y))
            return pts
        arm = lambda s: chain(sh, [(self.upper, q["ua_" + s]), (self.fore, q["la_" + s])])
        leg = lambda s: chain((0.0, 0.0), [(self.thigh, q["th_" + s]), (self.shin, q["sh_" + s])])
        legs = {s: leg(s) for s in "fb"}
        # the lowest point of each foot: its heel or toe, with the foot turned by ft about the ankle
        foot = self.p["foot"]
        ax, ay = foot.top

        def low(side):
            r = math.radians(q["ft_" + side])
            ankle = legs[side][-1]
            return max(ankle[1] + (px - ax) * math.sin(r) + (py - ay) * math.cos(r) for px, py in foot.sole)
        sole = {s: low(s) for s in "fb"}
        ground = max(sole.values())
        move = lambda p: (p[0], p[1] - ground)
        return {"neck": move(neck), "hip": move((0.0, 0.0)), "sh": move(sh), "q": q,
                "arm_f": [move(p) for p in arm("f")], "arm_b": [move(p) for p in arm("b")],
                "leg_f": [move(p) for p in legs["f"]], "leg_b": [move(p) for p in legs["b"]],
                "support": "f" if sole["f"] >= sole["b"] else "b"}

    def _place(self, cr, part, a, b, width_k, dim=False, alpha=1.0):
        """Part from a to b: stretched along its length to fit, scaled across by width_k."""
        ang = math.atan2(b[0] - a[0], b[1] - a[1])
        along = math.dist(a, b) / part.length
        cr.save()
        cr.translate(*a)
        cr.rotate(-ang)
        cr.scale(width_k, along)
        cr.translate(-part.top[0], -part.top[1])
        cr.set_source_surface(part.dim if dim else part.surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _hang(self, cr, part, at, ang, k, dim=False, alpha=1.0):
        cr.save()
        cr.translate(*at)
        cr.rotate(-math.radians(ang))
        cr.scale(k, k)
        cr.translate(-part.top[0], -part.top[1])
        cr.set_source_surface(part.dim if dim else part.surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _joint(self, cr, c, r, dim=False, alpha=1.0):
        x, y = c
        d = 0.6 if dim else 1.0
        g = cairo.RadialGradient(x, y, 0, x, y, r * 1.5)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.9 * d * alpha)
        g.add_color_stop_rgba(0.3, *ICE, 0.85 * d * alpha)
        g.add_color_stop_rgba(0.65, *ICE, 0.25 * d * alpha)
        g.add_color_stop_rgba(1, *ICE, 0)
        cr.set_source(g)
        cr.arc(x, y, r * 1.5, 0, 2 * math.pi)
        cr.fill()
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.set_line_width(r * 0.18)
        cr.set_source_rgba(0.9, 0.95, 1.0, 0.75 * d * alpha)
        cr.stroke()

    def scale_for(self, height):
        return height / self.stand_h

    def draw(self, cr, x, ground, q, height, alpha=1.0):
        s = self.scale_for(height)
        j = self.solve(q)
        to = lambda p: (x + p[0] * s, ground + p[1] * s)
        P = self.p
        rj = P["upper"].w * s * 0.17

        def arm(side, dim):
            a, b, c = [to(p) for p in j["arm_" + side]]
            self._place(cr, P["upper"], a, b, s, dim, alpha)
            self._place(cr, P["fore"], b, c, s, dim, alpha)
            d = (c[0] - b[0], c[1] - b[1])
            n = math.hypot(*d) or 1
            end = (c[0] + d[0] / n * self.hand * s, c[1] + d[1] / n * self.hand * s)
            self._place(cr, P["hand"], c, end, s, dim, alpha)
            for p, k in ((a, 1.1), (b, 0.9), (c, 0.8)):
                self._joint(cr, p, rj * k, dim, alpha)

        def leg(side, dim):
            a, b, c = [to(p) for p in j["leg_" + side]]
            self._place(cr, P["thigh"], a, b, s, dim, alpha)
            self._place(cr, P["shin"], b, c, s, dim, alpha)
            self._hang(cr, P["foot"], c, -q["ft_" + side], s, dim, alpha)   # positive ft: toe down
            for p, k in ((a, 1.1), (b, 1.0), (c, 0.85)):
                self._joint(cr, p, rj * k, dim, alpha)

        arm("b", True)
        leg("b", True)
        neck, hip = to(j["neck"]), to(j["hip"])
        self._place(cr, P["torso"], neck, hip, s, False, alpha)
        hd = math.radians(q["lean"] + q.get("head", 0))
        top = (neck[0] + math.sin(hd) * self.head_len * s, neck[1] - math.cos(hd) * self.head_len * s)
        self._place(cr, P["head"], top, neck, s, False, alpha)
        leg("f", False)
        arm("f", False)
        return {k: (to(v) if isinstance(v, tuple) else [to(p) for p in v] if isinstance(v, list) else v)
                for k, v in j.items()}
