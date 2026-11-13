"""The robot as a cut-out puppet: Codex draws the parts once (a parts sheet), code poses them every frame.

The parts sheet has ten separate islands on black (see tests/robot-puppet/prompts/01_零件图.txt):
  top row:    head (side), head (front), torso (side), torso (front)
  bottom row: upper arm, forearm, hand, thigh, shin, foot — limbs drawn vertical, the end nearer the body on top.
Each part is cut out with a soft mask, and its two attachment points (the middle of its top and bottom caps) are
measured, so a bone's length is the part's own length: the puppet keeps the proportions Codex drew.

Poses are the same angle dicts as 「一笔」 (story/hero.py: lean, head, ua_f, la_f, ua_b, la_b, th_f, sh_f, th_b,
sh_b, turn), so every pose, the walk cycle and pose blending carry over.  turn 0 = side view facing right,
1 = facing the camera: the head and torso cross-fade from the side part to the front part, hips and shoulders
spread apart, and the far limbs swing across (as in hero.solve).  The spherical joints are drawn in code over the
seams: ice-blue glow, like the character sheet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cairo
import numpy as np
from PIL import Image
from scipy import ndimage

ICE = (0.55, 0.85, 1.0)
ORDER = ["head_side", "head_front", "torso_side", "torso_front",
         "upper", "fore", "hand", "thigh", "shin", "foot"]


@dataclass
class Part:
    surf: cairo.ImageSurface        # cut-out, premultiplied
    dark: cairo.ImageSurface        # the same, darker: far-side limbs
    top: tuple[float, float]        # attachment points in the part's own pixels
    bottom: tuple[float, float]
    w: int
    h: int

    @property
    def length(self) -> float:
        return math.dist(self.top, self.bottom)


def _surface(rgb: np.ndarray, alpha: np.ndarray) -> cairo.ImageSurface:
    h, w = alpha.shape
    pre = (rgb.astype(np.float32) * alpha[..., None]).clip(0, 255).astype(np.uint8)
    bgra = np.dstack([pre[..., 2], pre[..., 1], pre[..., 0], (alpha * 255).astype(np.uint8)])
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    stride = surf.get_stride()
    buf = np.ndarray((h, stride // 4, 4), np.uint8, surf.get_data())
    buf[:, :w] = bgra
    surf.mark_dirty()
    return surf


def _cap(mask: np.ndarray, top: bool) -> tuple[float, float]:
    """Middle of the top (or bottom) cap: the centroid of the part's first (last) 5% of rows."""
    rows = np.where(mask.any(1))[0]
    h = rows[-1] - rows[0]
    band = (rows[0], rows[0] + max(3, int(h * 0.05))) if top else (rows[-1] - max(3, int(h * 0.05)), rows[-1])
    ys, xs = np.where(mask[band[0]:band[1] + 1])
    return float(xs.mean()), float(band[0] + ys.mean())


def load_parts(sheet: Path) -> dict[str, Part]:
    a = np.asarray(Image.open(sheet).convert("RGB")).astype(np.float32)
    lum = a.max(2)
    solid = ndimage.binary_fill_holes(ndimage.binary_closing(lum > 22, iterations=4))
    lab, n = ndimage.label(ndimage.binary_dilation(solid, iterations=6))
    boxes = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if (sl[0].stop - sl[0].start) * (sl[1].stop - sl[1].start) > 2000:
            boxes.append((sl, i))
    if len(boxes) != len(ORDER):
        raise ValueError(f"parts sheet: found {len(boxes)} parts, expected {len(ORDER)}")
    mid = a.shape[0] / 2
    rows = [sorted([b for b in boxes if (b[0][0].start + b[0][0].stop) / 2 < mid], key=lambda b: b[0][1].start),
            sorted([b for b in boxes if (b[0][0].start + b[0][0].stop) / 2 >= mid], key=lambda b: b[0][1].start)]
    parts = {}
    for name, (sl, i) in zip(ORDER, rows[0] + rows[1]):
        pad = 8
        y0, y1 = max(0, sl[0].start - pad), min(a.shape[0], sl[0].stop + pad)
        x0, x1 = max(0, sl[1].start - pad), min(a.shape[1], sl[1].stop + pad)
        m = (solid & (lab == i))[y0:y1, x0:x1]
        soft = ndimage.gaussian_filter(m.astype(np.float32), 1.2)
        glow = np.clip(lum[y0:y1, x0:x1] / 120, 0, 1)        # keep the outline glow just outside the mask
        alpha = np.maximum(soft, glow * (lab[y0:y1, x0:x1] == i))
        rgb = a[y0:y1, x0:x1]
        parts[name] = Part(_surface(rgb, alpha), _surface(rgb * 0.55, alpha), _cap(m, True), _cap(m, False),
                           x1 - x0, y1 - y0)
    return parts


class Puppet:
    """Draw the robot in any hero pose.  `height` is the standing height in px (feet to top of the helmet)."""

    def __init__(self, parts: dict[str, Part]):
        self.p = parts
        P = parts
        self.L = {k: P[k].length for k in ("upper", "fore", "thigh", "shin")}
        self.torso = P["torso_side"].length
        self.neck_len = P["head_side"].length
        self.foot_h = P["foot"].h - P["foot"].top[1]
        self.hip_w = P["torso_front"].w * 0.25          # half the hip width, front view
        self.sh_w = P["torso_front"].w * 0.40           # half the shoulder width, front view
        self.stand_h = self.L["thigh"] + self.L["shin"] + self.foot_h + self.torso + P["head_side"].h * 0.95

    # ---- skeleton (puppet units, x forward, ground y = 0) ----
    def solve(self, q: dict) -> dict:
        L = self.L
        turn = q.get("turn", 0.0)
        lean = math.radians(q["lean"])
        up = (math.sin(lean), -math.cos(lean))
        hip = (0.0, 0.0)
        neck = (self.torso * up[0], self.torso * up[1])
        sh = (neck[0] - up[0] * self.torso * 0.12, neck[1] - up[1] * self.torso * 0.12)
        mirror = 1 - 2 * turn

        def chain(x, y, segs, side):
            pts = [(x, y)]
            for length, ang in segs:
                r = math.radians(ang)
                x += length * math.sin(r) * (mirror if side == "b" else 1)
                y += length * math.cos(r)
                pts.append((x, y))
            return pts
        spread = lambda o, s, w: (o[0] + s * w * turn, o[1])
        arm_f = chain(*spread(sh, -1, self.sh_w), [(L["upper"], q["ua_f"]), (L["fore"], q["la_f"])], "f")
        arm_b = chain(*spread(sh, 1, self.sh_w), [(L["upper"], q["ua_b"]), (L["fore"], q["la_b"])], "b")
        leg_f = chain(*spread(hip, -1, self.hip_w), [(L["thigh"], q["th_f"]), (L["shin"], q["sh_f"])], "f")
        leg_b = chain(*spread(hip, 1, self.hip_w), [(L["thigh"], q["th_b"]), (L["shin"], q["sh_b"])], "b")
        lowest = max(leg_f[-1][1], leg_b[-1][1]) + self.foot_h
        move = lambda p: (p[0], p[1] - lowest)
        return {"hip": move(hip), "neck": move(neck), "shoulder": move(sh), "turn": turn,
                "head_ang": q["lean"] + q["head"] * (1 - 0.6 * turn), "lean": q["lean"],
                "arm_f": [move(p) for p in arm_f], "arm_b": [move(p) for p in arm_b],
                "leg_f": [move(p) for p in leg_f], "leg_b": [move(p) for p in leg_b]}

    # ---- drawing ----
    def _place(self, cr, part: Part, a, b, alpha=1.0, dark=False):
        """Draw `part` so its top attachment sits on a and its bottom on b (rotated and scaled along a→b)."""
        if alpha <= 0:
            return
        ang = math.atan2(b[0] - a[0], b[1] - a[1])          # from straight down
        k = math.dist(a, b) / max(1e-6, part.length)
        cr.save()
        cr.translate(*a)
        cr.rotate(-ang)
        cr.scale(k, k)
        cr.translate(-part.top[0], -part.top[1])
        cr.set_source_surface(part.dark if dark else part.surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _hang(self, cr, part: Part, at, ang_deg, k, alpha=1.0, dark=False, flip=False):
        """Draw `part` hanging from its top attachment at `at`, turned by ang_deg from straight down."""
        cr.save()
        cr.translate(*at)
        cr.rotate(-math.radians(ang_deg))
        cr.scale(-k if flip else k, k)
        cr.translate(-part.top[0], -part.top[1])
        cr.set_source_surface(part.dark if dark else part.surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _joint(self, cr, c, r, dark=False, alpha=1.0):
        x, y = c
        dim = 0.55 if dark else 1.0
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.set_source_rgba(0.05, 0.06, 0.08, alpha)
        cr.fill()
        g = cairo.RadialGradient(x, y, 0, x, y, r * 1.5)
        g.add_color_stop_rgba(0, 1, 1, 1, 0.9 * dim * alpha)
        g.add_color_stop_rgba(0.3, *ICE, 0.85 * dim * alpha)
        g.add_color_stop_rgba(0.65, *ICE, 0.25 * dim * alpha)
        g.add_color_stop_rgba(1, *ICE, 0)
        cr.set_source(g)
        cr.arc(x, y, r * 1.5, 0, 2 * math.pi)
        cr.fill()
        cr.arc(x, y, r, 0, 2 * math.pi)
        cr.set_line_width(r * 0.18)
        cr.set_source_rgba(0.9, 0.95, 1.0, 0.8 * dim * alpha)
        cr.stroke()

    def draw(self, cr, x: float, ground: float, q: dict, height: float, facing: int = 1, alpha: float = 1.0) -> dict:
        s = height / self.stand_h
        j = self.solve(q)
        to = lambda p: (x + p[0] * s * facing, ground + p[1] * s)
        J = {k: (to(v) if isinstance(v, tuple) else [to(p) for p in v] if isinstance(v, list) else v)
             for k, v in j.items()}
        P, turn = self.p, j["turn"]
        rj = P["upper"].w * s * 0.17                         # joint sphere radius

        def limb(chain_pts, upper, lower, end, dark, foot=False):
            a, b, c = chain_pts
            self._place(cr, P[upper], a, b, alpha, dark)
            self._place(cr, P[lower], b, c, alpha, dark)
            if foot:   # the foot stays nearly flat, tipping a little with the shin; points the way the hero faces
                tip = math.degrees(math.atan2(c[0] - b[0], c[1] - b[1])) * 0.25 * (1 - turn)
                self._hang(cr, P[end], c, tip, s, alpha, dark, flip=facing < 0)
            else:
                self._place(cr, P[end], c, (c[0] + (c[0] - b[0]) * 0.55, c[1] + (c[1] - b[1]) * 0.55), alpha, dark)
            for p in (a, b, c):
                self._joint(cr, p, rj * (1.1 if p is a else 0.9), dark, alpha)

        limb(J["arm_b"], "upper", "fore", "hand", dark=turn < 0.5)
        limb(J["leg_b"], "thigh", "shin", "foot", dark=turn < 0.5, foot=True)
        # torso and head: side part fading into the front part as the robot turns
        lean = j["lean"]
        for name, w in (("torso_side", 1 - turn), ("torso_front", turn)):
            if w > 0.01:
                self._place(cr, P[name], J["neck"], J["hip"], alpha * w)
        for name, w in (("head_side", 1 - turn), ("head_front", turn)):
            if w > 0.01:
                part = P[name]
                # the head stands on the neck: its bottom attachment on the neck point, pointing up
                ang = math.radians(j["head_ang"]) * facing
                top = (J["neck"][0] + math.sin(ang) * part.length * s, J["neck"][1] - math.cos(ang) * part.length * s)
                self._place(cr, part, top, J["neck"], alpha * w)
        limb(J["leg_f"], "thigh", "shin", "foot", dark=False, foot=True)
        limb(J["arm_f"], "upper", "fore", "hand", dark=False)
        return J
