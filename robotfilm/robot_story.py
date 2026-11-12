"""Robot story film: the side-view robot (walker.py) walks one continuous road through the night world (world.py),
stops at props (Codex-drawn, cut out of a props sheet) and acts each shot out, with code-drawn coins, charts,
arrows and fog.  Voice, subtitles, quotes and the cover come from the episode's timeline (story.render --stills)
and are drawn like robotfilm/compose.py.

    .venv/bin/python -m robotfilm.robot_story <episode folder> [--lang zh|en|all] [--world robot|story] [--preview] [--sheet]

The episode folder holds robot2/beats.py: BEATS[shot id] = dict(walk=seconds of walking at the start of the
shot, pose=walker pose or callable(lt, dur) -> pose, stations=[(prop, screen x as a share of the width, height
px, ...)], fx=callable(film, cr, ctx) drawing the shot's own elements and optionally returning a dict with
"lift" (px the robot stands above the ground) and "items" (things it holds)).
"""
from __future__ import annotations

import argparse
import importlib.util
import math
import random
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from multiprocessing import get_context
from pathlib import Path

import cairo
import numpy as np
from PIL import Image
from scipy import ndimage

from vagent import config as configmod
from story.render import FPS
from story.stage import GOLD, WHITE, ramp, text

from .compose import Film as WordsFilm, merged_timeline
from .front import Front
from .puppet import ICE, _surface
from .walker import STAND, Walker, blend, cutout, load_side_parts, walk_pose
from .world import HORIZON, WIDE, StoryWorld, World, soft_ellipse

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).parent / "assets"      # the robot as Codex drew it (see tests/robot-figure, robot-puppet)
SIDE_PARTS = ASSETS / "side_parts.png"
FRONT = [ASSETS / "front_00_stand.png", ASSETS / "front_03_arm_shoulder.png", ASSETS / "front_01_hand_up.png"]
ANGLES = ASSETS / "angles"       # the robot from other camera angles (Codex; prompts in examples/角度图提示词, -i front_00)
ANGLE_SCALE = {"back": 1.0, "three_quarter": 1.0, "low": 1.35, "high": 0.8}   # x the robot's height
TILT = {"low": 0.10, "high": -0.10}   # camera tilt as a share of the frame height: up shows sky, down ground
ANGLE_FADE = 0.7                 # s: another angle dissolves in and out, never a hard cut (used once or twice a film)
PROPS = ["city", "terminal", "factory", "scale", "bench", "stairs", "book", "tablet", "bag"]
FORMATS = {"zh": ("portrait", 1080, 1920), "en": ("landscape", 1920, 1080)}
BLEND = 0.3                      # walk <-> action pose blending
ROBOT_X = 0.38                   # the robot stands on the left-third line (props go toward the right one)
CAM_TALK = (1.05, 1.11)          # "full" shots push in a little, alternating shot by shot
CAM_SIZES = {"medium": (1.6, 1.35), "close": (2.2, 1.8)}  # zoom on the robot (portrait, landscape)
ORDER = ("full", "medium", "close")
CAM_RATE = 0.2                   # the zoom changes by at most ~22 % per second (log units): never dizzying
TURNS = ("medium", "full", "close")                        # talking shots take turns
OPENING_WALK = 3.0               # s: the opening shot walks the robot in unless the beat says still_open=True
FG_MIN_WALK = 0.2                # frame widths the camera must travel in one walk for grass to pass in front
LEAF_COLOURS = [(0.86, 0.52, 0.18), (0.93, 0.74, 0.25), (0.62, 0.72, 0.3), (0.8, 0.36, 0.2)]
SHADOW = (0.0, 0.0, 0.02)
SMOKE = (0.85, 0.86, 0.9)
WARM_LIGHT = (1.0, 0.72, 0.38)     # station glow=True: firelight / lamplight
smooth = lambda k: k * k * (3 - 2 * k)


@dataclass
class Sprite:
    surf: cairo.ImageSurface
    dim: cairo.ImageSurface
    w: int
    h: int

    def draw(self, cr, cx, base, height, alpha=1.0, dim=0.0, flip=False):
        """Bottom-centre at (cx, base), scaled to `height` px tall; `dim` 0..1 fades it toward its dark copy."""
        k = height / self.h
        cr.save()
        cr.translate(cx, base)
        cr.scale(-k if flip else k, k)
        cr.translate(-self.w / 2, -self.h)
        for surf, a in ((self.surf, alpha * (1 - dim)), (self.dim, alpha * dim)):
            if a > 0.003:
                cr.set_source_surface(surf, 0, 0)
                cr.get_source().set_filter(cairo.FILTER_GOOD)
                cr.paint_with_alpha(a)
        cr.restore()


def _sprite(rgb, mask=None, inside=0.62):
    """A prop cut out of its sheet.  `inside` is how opaque its dark inside is: 0.62 for the white line drawings
    (a little of the world shows through), 1.0 for props drawn in full colour (solid objects)."""
    ys, xs = np.where((rgb.max(2) > 22) if mask is None else mask)
    y0, y1, x0, x1 = max(0, ys.min() - 8), ys.max() + 8, max(0, xs.min() - 8), xs.max() + 8
    rgb = rgb[y0:y1, x0:x1]
    m = None if mask is None else mask[y0:y1, x0:x1]
    alpha = cutout(rgb, None if m is None else ndimage.binary_dilation(m, iterations=10), inside)
    gray = rgb.mean(2, keepdims=True)
    return Sprite(_surface(rgb, alpha), _surface(gray * 0.35 + rgb * 0.05, alpha), x1 - x0, y1 - y0)


def load_props(sheet: Path, machine: Path | None, names=PROPS, solid_props: bool = False) -> dict[str, Sprite]:
    a = np.asarray(Image.open(sheet).convert("RGB")).astype(np.float32)
    lum = a.max(2)
    # props drawn close together merge through their glow: try tighter cut-outs until each prop is one island
    for thr, grow in ((22, 6), (40, 3), (40, 1), (60, 1)):
        solid = ndimage.binary_fill_holes(ndimage.binary_closing(lum > thr, iterations=4))
        lab, _ = ndimage.label(ndimage.binary_dilation(solid, iterations=grow))
        boxes = [(sl, i) for i, sl in enumerate(ndimage.find_objects(lab), 1)
                 if (sl[0].stop - sl[0].start) * (sl[1].stop - sl[1].start) > 2000]
        if len(boxes) == len(names):
            break
    if len(boxes) != len(names):
        raise ValueError(f"props sheet: found {len(boxes)} props, expected {len(names)}")
    H = a.shape[0]
    row = lambda sl: min(2, int((sl[0].start + sl[0].stop) / 2 / (H / 3)))
    boxes.sort(key=lambda b: (row(b[0]), b[0][1].start))
    out = {}
    for name, (sl, i) in zip(names, boxes):
        out[name] = _sprite(a, lab == i, 1.0 if solid_props else 0.62)
    if machine is None:
        return out
    b = np.asarray(Image.open(machine).convert("RGB")).astype(np.float32)
    solid = ndimage.binary_fill_holes(ndimage.binary_closing(b.max(2) > 22, iterations=4))
    lab, n = ndimage.label(ndimage.binary_dilation(solid, iterations=6))
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    out["machine"] = _sprite(b, lab == (int(np.argmax(sizes)) + 1))
    return out


# ---------- small code-drawn things ----------
def coin(cr, x, y, r, a=1.0, glow=1.0):
    if a <= 0:
        return
    g = cairo.RadialGradient(x, y, 0, x, y, r * 2.4)
    g.add_color_stop_rgba(0, *ICE, 0.35 * a * glow)
    g.add_color_stop_rgba(1, *ICE, 0)
    cr.set_source(g)
    cr.arc(x, y, r * 2.4, 0, 2 * math.pi)
    cr.fill()
    cr.save()
    cr.translate(x, y)
    cr.scale(1, 0.42)
    cr.arc(0, 0, r, 0, 2 * math.pi)
    cr.restore()
    cr.set_source_rgba(0.05, 0.12, 0.2, a)
    cr.fill_preserve()
    cr.set_source_rgba(*ICE, a)
    cr.set_line_width(max(1.5, r * 0.18))
    cr.stroke()


def coin_stack(cr, x, base, r, n, a=1.0):
    for k in range(int(n)):
        coin(cr, x, base - k * r * 0.42, r, a, glow=0.4)


def glow_line(cr, pts, width, col, a, glow=True):
    if len(pts) < 2 or a <= 0:
        return
    cr.save()
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.set_line_join(cairo.LINE_JOIN_ROUND)
    for w, k in ([(width * 4, 0.1), (width * 2, 0.22), (width, 1.0)] if glow else [(width, 1.0)]):
        cr.move_to(*pts[0])
        for p in pts[1:]:
            cr.line_to(*p)
        cr.set_line_width(w)
        cr.set_source_rgba(*col[:3], a * k)
        cr.stroke()
    cr.restore()


def orb(cr, x, y, r, a=1.0, col=ICE):
    if a <= 0:
        return
    g = cairo.RadialGradient(x, y, 0, x, y, r * 2.2)
    g.add_color_stop_rgba(0, 1, 1, 1, a)
    g.add_color_stop_rgba(0.25, *col, 0.9 * a)
    g.add_color_stop_rgba(1, *col, 0)
    cr.set_source(g)
    cr.arc(x, y, r * 2.2, 0, 2 * math.pi)
    cr.fill()


class Angles:
    """The robot from other angles (back, three-quarter, low, high: full figures standing on their feet;
    over_shoulder: the back of its head and shoulder, cut by the left and bottom edges of its drawing)."""

    def __init__(self, folder: Path):
        self.sprites = {}
        for p in sorted(Path(folder).glob("*.png")):
            rgb = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
            ys, xs = np.where(rgb.max(2) > 60)
            top, feet = ys.min(), ys.max()
            low = ys > feet - 12
            self.sprites[p.stem] = (_surface(rgb, cutout(rgb)), top, feet, (xs[low].min() + xs[low].max()) / 2,
                                    rgb.shape[0])

    def stand(self, cr, name, x, ground, height, t, alpha=1.0):
        """Feet at (x, ground), `height` px tall, breathing a little."""
        surf, top, feet, fx, _ = self.sprites[name]
        k = height / (feet - top)
        cr.save()
        cr.translate(x, ground)
        cr.scale(k, k * (1 + 0.008 * math.sin(t * 2.1)))
        cr.translate(-fx, -feet)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def over_shoulder(self, cr, W, H, bottom, height, t, alpha=1.0, shift=0.0):
        """The over-the-shoulder close-up in the bottom-left foreground: its drawing's left edge on the frame's
        left edge, its bottom edge at `bottom`, `height` px tall; it sways a hair, like a held camera."""
        surf, _, _, _, ih = self.sprites["over_shoulder"]
        k = height / ih
        cr.save()
        cr.translate(shift - 6 + 4 * math.sin(t * 0.7), bottom - height + 3 * math.sin(t * 0.9))
        cr.scale(k, k)
        cr.set_source_surface(surf, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(alpha)
        cr.restore()


@lru_cache(maxsize=None)
def _angles(folder: str) -> Angles:
    """Cut out once per process: every Film (both formats, every render worker) shares them."""
    return Angles(Path(folder))


class Film(WordsFilm):
    """One language, one format.  Words (cover, quotes, subtitles, ①②③) come from compose.Film."""

    def __init__(self, folder: Path, timeline: dict, W: int, H: int, beats, lang: str, world: str = "robot"):
        self.W, self.H, self.portrait = W, H, H > W
        self.u = min(W, H) / 1080
        self.tl, self.shots, self.lang = timeline, timeline["shots"], lang
        self.ep = beats
        self.beats = beats.BEATS
        # while it plays only the subtitles carry words (the user's choice, 2026-11-12): no sky words or gold quotes
        # unless an episode asks with SKY_WORDS / QUOTES = True; the opening title card stays (COVER_TITLE = False
        # to drop it)
        self.sky_words = getattr(beats, "SKY_WORDS", False)
        self.show_quotes = getattr(beats, "QUOTES", False)
        self.show_cover = getattr(beats, "COVER_TITLE", True)
        # robot (default): dark blue-black silhouettes with thin white outlines; story: the 「一笔」 night world
        self.world = StoryWorld(W, H) if world == "story" else World(W, H, palette="color" if world == "color" else "night")
        self.walker = Walker(load_side_parts(SIDE_PARTS))
        machine = getattr(beats, "MACHINE", folder / "frames/样帧04_经济机器_v1.png")
        self.props = load_props(folder / "robot2/frames/道具图_v1.png", machine, getattr(beats, "PROPS", PROPS),
                                getattr(beats, "SOLID_PROPS", False))     # beats: SOLID_PROPS = True for colour props
        self.height = (250 if self.portrait else 300) * self.u   # portrait: smaller next to the larger mountains
        self.front = Front(FRONT, self.height * 1.02)
        self.angles = _angles(str(ANGLES))
        self.hip_x = W * ROBOT_X
        self.fg = _foreground(W, H, self.u) if world == "color" else None   # blurred grass passing close by
        self.ground = self.world.horizon
        self._plan()

    # ---------- timing ----------
    def beat(self, i):
        b = self.beats.get(self.shots[i]["id"], {})
        if i == 0 and not b.get("walk") and not b.get("still_open"):
            # the film opens moving: the robot walks in from the left while the camera waits on the first place
            dur = self.shots[0]["end"] - self.shots[0]["start"]
            b = {**b, "walk": min(OPENING_WALK, max(0.0, dur - 0.5)), "enter": True}
        return b

    def shot_at(self, t):
        for i, s in enumerate(self.shots):
            if s["start"] <= t < s["end"]:
                return i
        return len(self.shots) - 1

    def action_pose(self, i, lt):
        b, s = self.beat(i), self.shots[i]
        p = b.get("pose", STAND)
        return p(lt, s["end"] - s["start"]) if callable(p) else p

    def pose(self, t):
        i = self.shot_at(t)
        s, b = self.shots[i], self.beat(i)
        lt = t - s["start"]
        w = b.get("walk", 0.0)
        act = self.action_pose(i, max(0.0, lt - w))
        if b.get("leave"):                        # sets off again before the shot ends and walks out of frame
            off = lt - (s["end"] - s["start"] - b["leave"])
            if off >= 0:
                return blend(act, walk_pose(t), smooth(min(1.0, off / BLEND)))
        if w <= 0:
            return act
        if lt < w:
            q = walk_pose(t)
            if lt < BLEND and i > 0 and not self.beat(i - 1).get("walk_end"):   # from the last shot's pose
                prev = self.action_pose(i - 1, self.shots[i - 1]["end"] - self.shots[i - 1]["start"])
                return blend(prev, q, smooth(lt / BLEND))
            return q
        return blend(walk_pose(t), act, smooth(min(1.0, (lt - w) / BLEND)))

    def _plan(self):
        n = int(math.ceil(self.tl["duration"] * FPS)) + 2
        s = self.walker.scale_for(self.height)
        self.travel = [0.0]
        prev = self.walker.solve(self.pose(0.0))
        for f in range(1, n):
            cur = self.walker.solve(self.pose(f / FPS))
            side = prev["support"]
            dx = (prev["leg_" + side][-1][0] - cur["leg_" + side][-1][0]) * s
            self.travel.append(self.travel[-1] + max(0.0, dx))
            prev = cur
        # stations: props placed in the world where the robot stops for that shot
        self.stations = []
        for i, sh in enumerate(self.shots):
            b = self.beat(i)
            arrive = self.trav(min(sh["end"], sh["start"] + b.get("walk", 0.0)))   # walking all shot: its end
            for st in b.get("stations", []):
                name, fx, height = st[:3]
                opts = dict(st[3]) if len(st) > 3 else {}
                h = height * self.u
                w = h * self.props[name].w / self.props[name].h
                if "left_at" in opts:            # its left edge reaches the robot's hip at that moment of the shot
                    x = self.trav(sh["start"] + opts["left_at"]) + self.hip_x + w / 2
                elif "after" in opts:            # right behind the station with that key
                    prev = next(p for p in self.stations if p.get("key") == opts["after"])
                    x = prev["x"] + prev["w"] / 2 + w / 2 - opts.get("overlap", 0) * self.u
                else:
                    x = arrive + fx * self.W
                self.stations.append({"name": name, "x": x, "h": h, "w": w, "i": i, **opts})
        # each prop is there from its shot until the next shot that brings its own props (fading in and out
        # while the robot walks), so the road never piles up with things from earlier shots
        with_props = [k for k, sh in enumerate(self.shots) if self.beat(k).get("stations")]
        for st in self.stations:
            later = [k for k in with_props if k > st["i"] and not (st.get("key") and any(
                o["i"] == k and o.get("after") == st["key"] for o in self.stations))]
            # a station built onto another ("after") is part of the same structure and comes with it: the robot
            # may reach it before its own shot begins (down the far side of stairs it climbed in the last shot)
            base = next((p for p in self.stations if p.get("key") == st["after"]), st) if "after" in st else st
            st["t_in"] = self.shots[base["i"]]["start"]
            st["t_out"] = self.shots[later[0]]["start"] + 0.9 if later else 1e9
            if "out" in st:                      # gone as the shot with that id begins (earlier or later than usual)
                k = next(k for k, sh in enumerate(self.shots) if sh["id"] == st["out"])
                st["t_out"] = self.shots[k]["start"] + 0.9
        self._plan_holds()
        self._plan_foreground()
        self._plan_camera()

    # ---------- still camera: the robot walks into or out of a frame that holds still ----------
    def _plan_holds(self):
        """enter=True: the camera waits at the robot's mark while it walks in (the walk of that shot);
        leave=<s>: the camera stays put for the last s of the shot while the robot walks off to the right."""
        self.holds = []
        for i, s in enumerate(self.shots):
            b, dur = self.beat(i), s["end"] - s["start"]
            w = min(b.get("walk", 0.0), dur)
            if b.get("enter") and w > 0:
                self.holds.append((s["start"], s["start"] + w, self.trav(s["start"] + w)))
            if b.get("leave"):
                t0 = s["end"] - min(b["leave"], dur)
                self.holds.append((t0, s["end"], self.trav(t0)))

    def view_trav(self, t):
        """How far the camera has travelled: with the robot, except while it holds still."""
        for t0, t1, v in self.holds:
            if t0 <= t <= t1:
                return v
        return self.trav(t)

    def robot_x(self, t):
        return self.hip_x + self.trav(t) - self.view_trav(t)

    # ---------- camera ----------
    # The camera is an affine map: screen = a + z * point (z zoom, a offset), eased from shot to shot.
    def _plan_camera(self):
        """The shot size each shot ends on, and the camera that gives it.

        full: the whole place, pushing in a little (1.05 / 1.11 in turn); medium: the robot from close by;
        close: the robot's head and shoulders.  A shot that walks or brings props ends full (it shows the place),
        unless it would be the third full in a row and has 4 s left after arriving (then it pushes in to medium);
        a quote shot is a close-up, the rest take turns medium / full / close, never three of one size in a row.
        The shot before a walk and very short shots don't go close (the camera would have to rush).  A beat can
        choose with cam="full" | "medium" | "close"."""
        n = len(self.shots)
        walks = [self.beat(i).get("walk", 0.0) > 0 for i in range(n)]
        names, turn = [], 0
        for i, s in enumerate(self.shots):
            b, dur = self.beat(i), s["end"] - s["start"]
            if b.get("cam") in CAM_SIZES:
                name = b["cam"]
            elif b.get("angle") == "over_shoulder":   # looks past the robot at the place: must show it whole
                name = "full"
            elif walks[i] or b.get("stations"):
                # shows the place; but after two full shots, a long one pushes in once the robot is there
                settled = dur - min(b.get("walk", 0.0), dur)
                name = "medium" if len(names) >= 2 and names[-1] == names[-2] == "full" and settled >= 4.0 else "full"
            elif s.get("quote"):
                name = "close"
            elif dur < 2.5 and names:
                name = names[-1] if names[-1] != "close" else "medium"
            else:
                name = TURNS[turn % len(TURNS)]
                turn += 1
                if len(names) >= 2 and names[-1] == names[-2] == name:
                    name = TURNS[turn % len(TURNS)]
                    turn += 1
            if name == "close" and (i + 1 < n and walks[i + 1]):
                name = "medium"
            prev = names[-1] if names else "full"
            if b.get("cam") not in CAM_SIZES:
                if dur < 3.0:                     # too short to change size gently: keep the last one
                    name = prev
                elif abs(ORDER.index(name) - ORDER.index(prev)) == 2:
                    name = "medium"               # one step per shot: full <-> medium <-> close
            names.append(name)
        self.sizes = names
        talk = 0
        self.cam_in, self.cam_to = [], []
        c = WIDE
        for i, name in enumerate(names):
            if name == "full":
                want = self._full(CAM_TALK[talk % 2])
                talk += 1
            else:
                want = self._on_robot(name, ANGLE_SCALE.get(self.beat(i).get("angle"), 1.0))
            s = self.shots[i]
            # never faster than CAM_RATE: smooth() peaks at 1.5x its mean speed, so over a shot of d seconds the
            # zoom may change by at most exp(CAM_RATE * d / 1.5); a bigger change stops part of the way
            room = CAM_RATE * (s["end"] - s["start"]) / 1.5
            need = abs(math.log(want[0] / c[0]))
            to = want if need <= room else _mix(c, want, _part(c[0], want[0], room))
            self.cam_in.append(c)
            self.cam_to.append(to)
            c = to

    def _full(self, z):
        """Pushed in a little on the middle of the place, between the robot and its props."""
        top = self.H * (0.13 if self.portrait else 0.10)
        fx, fy = self.W * 0.5, (top + self.ground) / 2
        return (z, fx * (1 - z), fy * (1 - z))

    def _on_robot(self, name, scale=1.0):
        """Closer on the robot, its head kept on the left-third line and in the upper part of the frame
        (`scale`: how tall it is drawn in this shot, e.g. larger from a low angle)."""
        z = CAM_SIZES[name][0 if self.portrait else 1]
        hx, hy = self.hip_x, self.ground - self.height * 0.92 * scale
        tx, ty = self.W * ROBOT_X, self.H * (0.40 if self.portrait else 0.36)
        return (z, tx - z * hx, ty - z * hy)

    def shot_size(self, i):
        return self.sizes[i]

    def camera(self, t):
        """(z, ax, ay) at time t: a point p of the frame is drawn at (ax + z * px, ay + z * py)."""
        i = self.shot_at(t)
        s = self.shots[i]
        lt, dur = t - s["start"], s["end"] - s["start"]
        c0, c1 = self.cam_in[i], self.cam_to[i]
        return _mix(c0, c1, smooth(min(1.0, lt / dur))) if dur > 0 else c1

    def zoom(self, t):
        return self.camera(t)[0]

    def angle_mix(self, t):
        """(angle, k): which other view of the robot shows at t and how far it has dissolved in (0..1). An angle
        shot dissolves in over its first ANGLE_FADE s and back out over the first ANGLE_FADE s of the next shot:
        no hard cuts."""
        i = self.shot_at(t)
        lt = t - self.shots[i]["start"]
        cur = self.beat(i).get("angle")
        prev = self.beat(i - 1).get("angle") if i > 0 else None
        if cur:
            return cur, (1.0 if prev == cur else smooth(min(1.0, lt / ANGLE_FADE)))
        if prev and lt < ANGLE_FADE:
            return prev, 1 - smooth(lt / ANGLE_FADE)
        return None, 0.0

    def tilt(self, t):
        """Vertical shift of the whole picture for low / high angles, easing in and out with the dissolve."""
        name, k = self.angle_mix(t)
        return TILT.get(name, 0.0) * self.H * k

    def shot_index(self, shot_id):
        return next(k for k, sh in enumerate(self.shots) if sh["id"] == shot_id)

    def trav(self, t):
        return self.travel[min(len(self.travel) - 1, max(0, int(round(t * FPS))))]

    def climb(self, travel):
        """Height of the stairs under the robot's hip (stations with "climb": up or down)."""
        best = 0.0
        for st in self.stations:
            if not st.get("climb"):
                continue
            left = st["x"] - st["w"] / 2 - travel
            f = (self.hip_x - left) / st["w"]
            if st.get("flip"):
                f = 1 - f
            if 0 <= f <= 1:
                best = max(best, min(1.0, f / 0.86) * st["h"] * 0.93)
        return best

    # ---------- helpers for beats ----------
    def screen_x(self, world_x, t):
        return world_x - self.trav(t)

    def robot(self, cr, x, ground, q, alpha=1.0, flip=False, height=None, chest=1.0):
        """Draw a robot (also the extra ones); returns joints in screen space and its chest-core position."""
        h = height or self.height
        if flip:
            cr.save()
            cr.translate(2 * x, 0)
            cr.scale(-1, 1)
        J = self.walker.draw(cr, x, ground, q, h, alpha)
        c = self.chest(J, h)
        if chest < 1:          # the chest core dims: a dark disc over it
            cr.arc(c[0], c[1], h * 0.03, 0, 2 * math.pi)
            cr.set_source_rgba(0.04, 0.05, 0.08, (1 - chest) * alpha)
            cr.fill()
        if flip:
            cr.restore()
            mirror = lambda p: (2 * x - p[0], p[1])
            J = {k: (mirror(v) if isinstance(v, tuple) else [mirror(p) for p in v] if isinstance(v, list) else v)
                 for k, v in J.items()}
            c = mirror(c)
        J["chest"] = c
        return J

    def chest(self, J, h):
        neck, hip = J["neck"], J["hip"]
        return (neck[0] + (hip[0] - neck[0]) * 0.22 + h * 0.035, neck[1] + (hip[1] - neck[1]) * 0.22)

    def hand(self, J):
        sh, el, wr = J["arm_f"]
        d = (wr[0] - el[0], wr[1] - el[1])
        n = math.hypot(*d) or 1
        k = self.walker.hand * self.walker.scale_for(self.height) * 0.6
        return wr[0] + d[0] / n * k, wr[1] + d[1] / n * k

    # ---------- a frame ----------
    def draw(self, cr, t, lang=None):
        i = self.shot_at(t)
        s = self.shots[i]
        lt = t - s["start"]
        b = self.beat(i)
        travel = self.view_trav(t)
        rx = self.robot_x(t)
        cam = self.camera(t)
        angle, ak = self.angle_mix(t)
        cr.save()                                 # low / high angle: the whole scene tilts (not the subtitles)
        cr.translate(0, self.tilt(t))
        self.world.draw(cr, travel, t, cam)      # far layers follow the camera only partly (depth)
        cr.save()                                 # the camera moves the props, the robot and what it does ...
        z, ax, ay = cam
        cr.translate(ax, ay)
        cr.scale(z, z)
        for st in self.stations:
            x = st["x"] - travel
            if -self.W * 0.6 < x < self.W * 1.6 and st["t_in"] - 0.01 <= t <= st["t_out"]:
                a = st.get("alpha", 1.0) * ramp(t, st["t_in"] - 0.01, st["t_in"] + 0.7) * (1 - ramp(t, st["t_out"] - 0.9, st["t_out"]))
                if st["i"] == 0:
                    a = st.get("alpha", 1.0) * (1 - ramp(t, st["t_out"] - 0.9, st["t_out"]))   # there from the first frame
                if "taken" in st:                 # picked up by the robot that many seconds into its shot
                    a *= 1 - ramp(t, st["t_in"] + st["taken"], st["t_in"] + st["taken"] + 0.25)
                dim = st["dim"](t, self) if callable(st.get("dim")) else st.get("dim", 0.0)
                base = self.ground + st.get("sink", 0) * self.u
                h = st["h"] * (0.35 + 0.65 * smooth(ramp(t, st["t_in"] + 0.6, st["t_in"] + 3.5))) if st.get("grow") else st["h"]
                sp = self.props[st["name"]]
                if st.get("glow"):                # a prop that gives light: a halo and a pool of it on the ground
                    col = st["glow"] if isinstance(st["glow"], tuple) else WARM_LIGHT
                    f = (0.82 + 0.18 * math.sin(t * 9.0 + x * 0.01) * math.sin(t * 5.3)) if st.get("flicker") else 1.0
                    k = a * f * (1 - dim)
                    soft_ellipse(cr, x, base - h * 0.45, h * 1.1, h * 1.1, col, 0.30 * k)
                    soft_ellipse(cr, x, base + 10 * self.u, h * 1.9, h * 0.26, col, 0.48 * k)
                w = h * sp.w / sp.h                    # soft contact shadow, so it stands on the ground
                soft_ellipse(cr, x, base + 3 * self.u, w * 0.55, max(5 * self.u, w * 0.06), SHADOW, 0.55 * a)
                if st.get("sway"):                # trees and plants: a gentle wind, the base stays put
                    cr.save()
                    cr.translate(x, base)
                    cr.rotate(0.035 * math.sin(t * 1.3 + x * 0.002) + 0.012 * math.sin(t * 2.9 + 1.0))
                    cr.translate(-x, -base)
                sp.draw(cr, x, base, h, a, dim, st.get("flip", False))
                if st.get("sway"):
                    cr.restore()
                if st.get("smoke"):               # smoke or steam rising from it and drifting away
                    self._smoke(cr, x, base - h * (st["smoke"] if not isinstance(st["smoke"], bool) else 0.85), h, t,
                                a * (1 - 0.6 * dim))
        ctx = {"i": i, "t": t, "lt": lt, "dur": s["end"] - s["start"], "walk": b.get("walk", 0.0),
               "voice": s["voice_end"] - s["start"], "lang": self.lang}
        q = self.pose(t)
        front = b.get("front")
        pre = b.get("before")
        if pre:
            pre(self, cr, ctx)
        extra = {}
        fx = b.get("fx")
        if fx and b.get("fx_behind"):
            extra = fx(self, cr, ctx) or {}
        lift = extra.get("lift", 0.0) + self.climb(self.trav(t))
        if "settle" in b:                 # comes back down from where the last shot left it
            lift += b["settle"] * self.height * (1 - smooth(ramp(lt, 0.0, 0.8)))
        shade = max(0.0, 1 - lift / (self.height * 0.6))     # the robot's own shadow, fainter when it is lifted
        soft_ellipse(cr, rx + self.height * 0.02, self.ground + 3 * self.u, self.height * 0.21,
                     self.height * 0.035, SHADOW, 0.8 * shade)
        if front is not None and lt >= front[0]:
            self._front(cr, ctx, front)
            J = None
        else:                                     # the side view, dissolving into another angle when there is one
            J = self.robot(cr, rx, self.ground - lift, q, alpha=1 - ak, chest=extra.get("chest", 1.0)) if ak < 1 else None
            if angle and angle != "over_shoulder" and ak > 0:
                self.angles.stand(cr, angle, rx, self.ground - lift, self.height * ANGLE_SCALE[angle], t, ak)
            if ak > 0:
                J = None
        ctx["J"] = J
        if J is not None and b.get("hold"):      # the robot holds a prop: hold=(prop, height in design px[, from s])
            name, hh, *since = b["hold"]
            k = ramp(lt, since[0], since[0] + 0.25) if since else 1.0
            hx, hy = self.hand(J)
            self.props[name].draw(cr, hx + 6 * self.u, hy + hh * self.u * 0.35, hh * self.u, k)
        if fx and not b.get("fx_behind"):
            fx(self, cr, ctx)
        cr.restore()                              # ... but not the subtitles and quotes: they stay put
        cr.restore()                              # (the tilt)
        if angle == "over_shoulder" and ak > 0:    # the robot is the camera's shoulder, in front, below
            # its drawing is cut by its own left and bottom edges: put those beyond the frame's edges
            # (portrait: smaller and further off the left edge, so the place still fills most of the frame)
            self.angles.over_shoulder(cr, self.W, self.H, self.H + 8 * self.u, self.H * (0.46 if self.portrait else 0.62),
                                      t, ak, shift=-self.W * (0.12 if self.portrait else 0.0))
        if b.get("drift"):                       # leaves or paper drifting across a still shot, near the lens
            self._drift(cr, b["drift"], lt, t)
        self._foreground(cr, t)
        self._words(cr, i, t)

    # ---------- foreground and things drifting by ----------
    def _plan_foreground(self):
        """Blurred grass right in front of the lens, passing during the longer walks only.  Each clump is a thing
        beside the road: it is just outside the right edge when the walk starts and has gone past the left edge
        by the time the robot stops, so it only ever comes in and goes out at the edges -- never fades, never
        stays in frame.  Its nearness (how fast it passes) is chosen to cross the whole frame within the walk;
        a walk too short for that gets none (it would whip past), and only every other long walk has one."""
        self.fg_passes = []
        if self.fg is None:
            return
        cw = self.fg.get_width()
        long_walks = 0
        for i, s in enumerate(self.shots):
            b = self.beat(i)
            w = min(b.get("walk", 0.0), s["end"] - s["start"])
            if w <= 0 or b.get("enter"):
                continue
            t0, t1 = s["start"], s["start"] + w
            dv = self.view_trav(t1) - self.view_trav(t0)
            if dv < FG_MIN_WALK * self.W:
                continue
            long_walks += 1
            if long_walks % 2 == 1:
                self.fg_passes.append((t0, self.view_trav(t0), (self.W + cw) / dv))

    def foreground_clumps(self, t):
        """[(left x, width)] of the foreground clumps in frame at t."""
        cw, out, v = self.fg.get_width() if self.fg is not None else 0, [], self.view_trav(t)
        for t0, v0, near in self.fg_passes:
            x = self.W - (v - v0) * near
            if -cw < x < self.W:
                out.append((x, cw))
        return out

    def foreground_cover(self, t):
        return 1.0 if self.foreground_clumps(t) else 0.0

    def _foreground(self, cr, t):
        for x, _ in self.foreground_clumps(t):
            cr.set_source_surface(self.fg, x, self.H - self.fg.get_height())
            cr.paint_with_alpha(0.95)

    def _drift(self, cr, kind, lt, t):
        """A few leaves (or sheets of paper) blown across the frame from right to left, turning as they go."""
        u = self.u
        for k in range(4):
            f = (lt * 0.16 + k * 0.29) % 1.25
            x = self.W * (1.1 - f)
            y = self.H * (0.24 + 0.09 * k) + 40 * u * math.sin(lt * 1.3 + k * 2) + f * 60 * u
            spin = lt * (1.6 + 0.4 * k) + k
            cr.save()
            cr.translate(x, y)
            cr.rotate(spin)
            if kind == "paper":
                cr.scale(max(0.15, abs(math.cos(spin * 0.7))), 1)
                cr.rectangle(-30 * u, -40 * u, 60 * u, 80 * u)
                cr.set_source_rgba(0.95, 0.94, 0.9, 0.9)
                cr.fill()
            else:
                cr.scale(1, 0.45)
                cr.arc(0, 0, 20 * u, 0, 2 * math.pi)
                cr.set_source_rgba(*LEAF_COLOURS[k % len(LEAF_COLOURS)], 0.92)
                cr.fill()
            cr.restore()

    def _smoke(self, cr, x, top, h, t, a):
        """Soft puffs rising from (x, top), growing and fading as they drift up and to the right."""
        for k in range(10):
            ph = (t * 0.35 + k / 10) % 1.0
            px = x + math.sin(ph * 3 + k) * h * 0.12 + ph * h * 0.25
            py = top - ph * h * 1.5
            r = h * (0.07 + 0.14 * ph)
            soft_ellipse(cr, px, py, r, r, SMOKE, 0.22 * a * math.sin(math.pi * ph))

    def _front(self, cr, ctx, front):
        """Turn to the viewer: a hard cut with a short white flash, then the front drawings cross-fading (only the
        arm changes between them)."""
        at, fades = front
        lt = ctx["lt"]
        j0 = self.walker.solve(STAND)
        s = self.walker.scale_for(self.height)
        fp = self.walker.p["foot"]
        foot_mid = (j0["leg_f"][-1][0] + j0["leg_b"][-1][0]) / 2
        x = self.hip_x + (foot_mid + (sum(px for px, _ in fp.sole) / 2 - fp.top[0])) * s
        starts = [at] + list(fades)
        for k, t0 in enumerate(starts):
            a = 1.0 if k == 0 else smooth(ramp(lt, t0, t0 + 0.3))
            if k + 1 < len(starts) and lt >= starts[k + 1] + 0.3:
                continue
            if a > 0:
                self.front.draw(cr, k, x, self.ground, a)
        flash = 1 - min(1.0, abs(lt - at) / (1.5 / FPS))
        if flash > 0:
            orb(cr, x, self.ground - self.height * 0.5, self.height * 0.35, flash)


def _mix(p, q, k):
    return tuple(x + (y - x) * k for x, y in zip(p, q))


def _part(z0, z1, room):
    """How far from camera z0 toward z1 one may go so the zoom changes by exactly exp(room)."""
    target = z0 * math.exp(room if z1 > z0 else -room)
    return (target - z0) / (z1 - z0)


def _foreground(W, H, u):
    """A clump of tall grass, dark and out of focus (drawn small and scaled up, which blurs it)."""
    k = 6                                                     # drawn at 1/6 size
    w, h = int(W * 0.42 / k), int((H * (1 - HORIZON) + H * 0.15) / k)   # rises well above the road line
    small = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    sc = cairo.Context(small)
    rnd = random.Random(23)
    for _ in range(26):
        bx = rnd.uniform(0.1, 0.9) * w
        top = rnd.uniform(0.0, 0.5) * h
        lean = rnd.uniform(-0.25, 0.25) * w
        half = rnd.uniform(0.02, 0.05) * w
        sc.move_to(bx - half, h)
        sc.curve_to(bx - half, h * 0.6, bx + lean * 0.5, top + h * 0.2, bx + lean, top)
        sc.curve_to(bx + lean * 0.5 + half, top + h * 0.25, bx + half, h * 0.6, bx + half, h)
        sc.close_path()
        sc.set_source_rgba(0.03, 0.08, 0.05, 1.0)
        sc.fill_preserve()
        sc.set_line_width(0.6)                                # a faint moonlit rim on each blade
        sc.set_source_rgba(0.45, 0.55, 0.65, 0.35)
        sc.stroke()
    big = cairo.ImageSurface(cairo.FORMAT_ARGB32, w * k, h * k)
    bc = cairo.Context(big)
    bc.scale(k, k)
    bc.set_source_surface(small, 0, 0)
    bc.get_source().set_filter(cairo.FILTER_BILINEAR)
    bc.paint()
    return big


def load_beats(folder: Path) -> dict:
    spec = importlib.util.spec_from_file_location("beats", folder / "robot2/beats.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _render_part(args):
    folder, tl, W, H, lang, fps, first, last, out, world = args
    film = Film(Path(folder), tl, W, H, load_beats(Path(folder)), lang, world)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    for f in range(first, last):
        film.draw(cairo.Context(surf), f / fps)
        surf.flush()
        ff.stdin.write(bytes(surf.get_data()))
    ff.stdin.close()
    assert ff.wait() == 0
    return out


def sheet(film, out, cols=6, at=0.7):
    shots = film.shots
    tw, th = film.W // 4, film.H // 4
    big = cairo.ImageSurface(cairo.FORMAT_ARGB32, tw * cols, th * math.ceil(len(shots) / cols))
    sc = cairo.Context(big)
    frame = cairo.ImageSurface(cairo.FORMAT_ARGB32, film.W, film.H)
    for n, s in enumerate(shots):
        film.draw(cairo.Context(frame), s["start"] + (s["end"] - s["start"]) * at)
        sc.save()
        sc.translate((n % cols) * tw, (n // cols) * th)
        sc.scale(0.25, 0.25)
        sc.set_source_surface(frame, 0, 0)
        sc.paint()
        sc.restore()
        text(sc, str(s["id"]), 26, (n % cols) * tw + 24, (n // cols) * th + 24, GOLD)
    big.write_to_png(str(out))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--lang", choices=["zh", "en", "all"], default="all")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--sheet", action="store_true")
    ap.add_argument("--at", type=float, default=0.7)
    ap.add_argument("--world", choices=["robot", "color", "story"], default="color",
                    help="color: the user's favourite night in colour (navy sky, big soft lit clouds, green hills; "
                         "the default since 2026-11-11); robot: the original blue-black silhouettes; "
                         "story: the 「一笔」 forested night world")
    args = ap.parse_args(argv)
    folder = args.folder.resolve()
    from vagent.audio.mix import mix
    from vagent.render.engine import embed_artwork
    beats = load_beats(folder)
    for lang in (["zh", "en"] if args.lang == "all" else [args.lang]):
        tag = "" if lang == "zh" else f"_{lang}"
        name, W, H = FORMATS[lang]
        tl = merged_timeline(folder, lang)
        film = Film(folder, tl, W, H, beats, lang, args.world)
        sheet(film, folder / f"robot2/review/sheet{tag}_{name}.png", at=args.at)
        print("wrote sheet", lang, flush=True)
        if args.sheet:
            continue
        cover_png = folder / f"robot2/cover{tag}_{name}.png"
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
        film.draw(cairo.Context(surf), 0.0)
        surf.write_to_png(str(cover_png))
        final, stats = mix(folder / "build" / f"voice{tag}.wav", tl["duration"], 19, folder / "build" / f"robot2_{lang}",
                           music=configmod.music())
        fps = FPS
        if args.preview:
            W, H, fps = W // 2, H // 2, 15
        frames = int(math.ceil(tl["duration"] * fps))
        out = folder / "robot2" / (f"preview{tag}_{name}.mp4" if args.preview else f"robot2{tag}_{name}.mp4")
        workers = 4
        with tempfile.TemporaryDirectory(prefix="robot2-") as tmp:
            cuts = [frames * k // workers for k in range(workers + 1)]
            jobs = [(str(folder), tl, W, H, lang, fps, cuts[k], cuts[k + 1], f"{tmp}/part{k}.mp4", args.world)
                    for k in range(workers)]
            with get_context("spawn").Pool(workers) as pool:
                parts = pool.map(_render_part, jobs)
            listing = Path(tmp) / "parts.txt"
            listing.write_text("".join(f"file '{p}'\n" for p in parts))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                            "-i", str(final), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a",
                            "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
        embed_artwork(out, cover_png)
        print("wrote", out, flush=True)


if __name__ == "__main__":
    main()
