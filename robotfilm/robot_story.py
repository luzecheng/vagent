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
import subprocess
import tempfile
from dataclasses import dataclass
from multiprocessing import get_context
from pathlib import Path

import cairo
import numpy as np
from PIL import Image
from scipy import ndimage

from story.render import FPS
from story.stage import GOLD, WHITE, ramp, text

from .compose import Film as WordsFilm, merged_timeline
from .front import Front
from .puppet import ICE, _surface
from .walker import STAND, Walker, blend, cutout, load_side_parts, walk_pose
from .world import StoryWorld, World

ROOT = Path(__file__).resolve().parents[1]
ASSETS = Path(__file__).parent / "assets"      # the robot as Codex drew it (see tests/robot-figure, robot-puppet)
SIDE_PARTS = ASSETS / "side_parts.png"
FRONT = [ASSETS / "front_00_stand.png", ASSETS / "front_03_arm_shoulder.png", ASSETS / "front_01_hand_up.png"]
PROPS = ["city", "terminal", "factory", "scale", "bench", "stairs", "book", "tablet", "bag"]
FORMATS = {"zh": ("portrait", 1080, 1920), "en": ("landscape", 1920, 1080)}
BLEND = 0.3                      # walk <-> action pose blending
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


def _sprite(rgb, mask=None):
    ys, xs = np.where((rgb.max(2) > 22) if mask is None else mask)
    y0, y1, x0, x1 = max(0, ys.min() - 8), ys.max() + 8, max(0, xs.min() - 8), xs.max() + 8
    rgb = rgb[y0:y1, x0:x1]
    m = None if mask is None else mask[y0:y1, x0:x1]
    alpha = cutout(rgb, None if m is None else ndimage.binary_dilation(m, iterations=10))
    gray = rgb.mean(2, keepdims=True)
    return Sprite(_surface(rgb, alpha), _surface(gray * 0.35 + rgb * 0.05, alpha), x1 - x0, y1 - y0)


def load_props(sheet: Path, machine: Path | None, names=PROPS) -> dict[str, Sprite]:
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
        out[name] = _sprite(a, lab == i)
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


class Film(WordsFilm):
    """One language, one format.  Words (cover, quotes, subtitles, ①②③) come from compose.Film."""

    def __init__(self, folder: Path, timeline: dict, W: int, H: int, beats, lang: str, world: str = "robot"):
        self.W, self.H, self.portrait = W, H, H > W
        self.u = min(W, H) / 1080
        self.tl, self.shots, self.lang = timeline, timeline["shots"], lang
        self.ep = beats
        self.beats = beats.BEATS
        # robot (default): dark blue-black silhouettes with thin white outlines; story: the 「一笔」 night world
        self.world = StoryWorld(W, H) if world == "story" else World(W, H)
        self.walker = Walker(load_side_parts(SIDE_PARTS))
        machine = getattr(beats, "MACHINE", folder / "frames/样帧04_经济机器_v1.png")
        self.props = load_props(folder / "robot2/frames/道具图_v1.png", machine, getattr(beats, "PROPS", PROPS))
        self.height = (250 if self.portrait else 300) * self.u   # portrait: smaller next to the larger mountains
        self.front = Front(FRONT, self.height * 1.02)
        self.hip_x = W * (0.30 if self.portrait else 0.36)
        self.ground = self.world.horizon
        self._plan()

    # ---------- timing ----------
    def beat(self, i):
        return self.beats.get(self.shots[i]["id"], {})

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
        travel = self.trav(t)
        self.world.draw(cr, travel, t)
        for st in self.stations:
            x = st["x"] - travel
            if -self.W * 0.6 < x < self.W * 1.6 and st["t_in"] - 0.01 <= t <= st["t_out"]:
                a = st.get("alpha", 1.0) * ramp(t, st["t_in"] - 0.01, st["t_in"] + 0.7) * (1 - ramp(t, st["t_out"] - 0.9, st["t_out"]))
                if st["i"] == 0:
                    a = st.get("alpha", 1.0) * (1 - ramp(t, st["t_out"] - 0.9, st["t_out"]))   # there from the first frame
                dim = st["dim"](t, self) if callable(st.get("dim")) else st.get("dim", 0.0)
                base = self.ground + st.get("sink", 0) * self.u
                h = st["h"] * (0.35 + 0.65 * smooth(ramp(t, st["t_in"] + 0.6, st["t_in"] + 3.5))) if st.get("grow") else st["h"]
                self.props[st["name"]].draw(cr, x, base, h, a, dim, st.get("flip", False))
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
        lift = extra.get("lift", 0.0) + self.climb(travel)
        if "settle" in b:                 # comes back down from where the last shot left it
            lift += b["settle"] * self.height * (1 - smooth(ramp(lt, 0.0, 0.8)))
        if front is not None and lt >= front[0]:
            self._front(cr, ctx, front)
            J = None
        else:
            J = self.robot(cr, self.hip_x, self.ground - lift, q, chest=extra.get("chest", 1.0))
        ctx["J"] = J
        if fx and not b.get("fx_behind"):
            fx(self, cr, ctx)
        self._words(cr, i, t)

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
    ap.add_argument("--world", choices=["robot", "story"], default="robot",
                    help="robot: blue-black silhouettes (default); story: the 「一笔」 forested night world")
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
                           music=True)
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
