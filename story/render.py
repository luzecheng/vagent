"""Render a storyboard into story-style videos: 1920×1080 landscape and 1080×1920 portrait.

    .venv/bin/python -m story.render <episode folder or storyboard.json> [--portrait | --only landscape|portrait]
Default formats: Chinese portrait, English landscape (DEFAULT_FORMATS); --portrait gives both for each.
                                     [--preview] [--stills]

Steps: narration (vagent TTS, your configured voice) -> shot timeline from the real audio -> soft music mix
(vagent's procedural score, voice at -16 LUFS) -> frames drawn with pycairo in parallel -> H.264 + AAC.
Everything is written into the episode folder.  Nothing is uploaded or published.

--draft    contact sheets with estimated timing and no TTS: a quick look at a new storyboard before confirming it
--stills   narrate (TTS) and stop after the contact sheets
--preview  half size, 15 fps: quick to check motion and timing
"""
from __future__ import annotations

import argparse
import json
import math
from multiprocessing import get_context
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import zlib

import cairo

from vagent import config as configmod
from vagent.audio.mix import mix
from vagent.render.engine import embed_artwork

from . import hero as H
from . import narrate as narration
from . import scenes
from .stage import GOLD, WHITE, Camera, Stage, circle, lerp, ramp, text, text_runs, text_width

FORMATS = {"landscape": (1920, 1080), "portrait": (1080, 1920)}
# What each language gets without --portrait / --only: Chinese is for 视频号, watched on phones (portrait);
# English is for X (landscape).
DEFAULT_FORMATS = {"zh": ["portrait"], "en": ["landscape"]}


def formats_for(lang: str, args) -> list[str]:
    if args.only:
        return [args.only]
    return list(FORMATS) if args.portrait else DEFAULT_FORMATS.get(lang, ["landscape"])
FPS = 30
TRANS = 0.7          # seconds two shots overlap while one fades into the next
HERO_BLEND = 0.6     # seconds the hero takes to flow from one shot's pose into the next


class Film:
    """Everything needed to draw any frame of one format: the timeline plus per-shot precomputation."""

    def __init__(self, timeline: dict, W: int, H_: int, seed: int):
        self.tl, self.shots = timeline, timeline["shots"]
        self.duration = timeline["duration"]
        self.st = Stage(W, H_, seed=seed, scenery=bool(timeline.get("scenery")))
        self.mods = [scenes.get(s["scene"]) for s in self.shots]
        lang = timeline.get("lang", "zh")
        self.params = [localized(s.get("params", {}), lang) for s in self.shots]
        self._camera_starts()
        self._travel()
        self._lamps()

    # ----- precomputation -----
    def _target(self, i):
        c = {"lift": 0.0, "zoom": 1.0, "ease": 1.2}
        c.update(self.mods[i].camera(self.params[i]))
        return c

    def _camera_at(self, i, t, start_cam):
        tgt = self._target(i)
        k = ramp(t, self.shots[i]["start"], self.shots[i]["start"] + tgt["ease"])
        return {key: lerp(start_cam[key], tgt[key], k) for key in ("lift", "zoom")}

    def _camera_starts(self):
        self.cam_start = [{"lift": 0.0, "zoom": 1.0}]
        for i in range(1, len(self.shots)):
            self.cam_start.append(self._camera_at(i - 1, self.shots[i]["start"], self.cam_start[i - 1]))

    def _speed(self, i, t):
        s = self.shots[i]
        d = max(1e-6, s["end"] - s["start"])
        fn = getattr(self.mods[i], "speed", None)
        return fn(ramp_lin(t, s["start"], s["end"]), d, self.params[i]) if fn else 0.0

    def _travel(self):
        """Distance walked (px) at every frame, and at every shot start: integrated from each scene's speed."""
        n = int(math.ceil(self.duration * FPS)) + 2
        self.travel = [0.0] * n
        dist, i = 0.0, 0
        for f in range(n):
            t = f / FPS
            while i + 1 < len(self.shots) and t >= self.shots[i + 1]["start"]:
                i += 1
            self.travel[f] = dist
            dist += self.st.v * self._speed(i, t) / FPS
        self.travel_start = [self.travel[min(n - 1, int(s["start"] * FPS))] for s in self.shots]

    def _lamps(self):
        """Whether the hero carries the lamp in each shot: a scene sets it, later shots inherit it."""
        state, self.lamp_in = False, []
        for i, s in enumerate(self.shots):
            self.lamp_in.append(state)
            self.st.t, self.st.local = s["end"], 0.0
            got = self.mods[i].hero(self.st, 1.0, s["end"] - s["start"], self.params[i]).get("lamp")
            if got is not None:
                state = True if got == "ground" else got   # set down for this shot; picked up again after

    # ----- one frame -----
    def _progress(self, i, t):
        s = self.shots[i]
        return ramp_lin(t, s["start"], s["end"]), max(1e-6, s["end"] - s["start"])

    def _hero_state(self, i, t):
        p, d = self._progress(i, t)
        self.st.local = self.travel[min(len(self.travel) - 1, int(t * FPS))] - self.travel_start[i]
        h = {"x": self.st.hx, "y": None, "pose": None, "facing": 1, "light": 0.5, "alpha": 1.0, "scale": 1.0,
             "lamp": None, "lamp_glow": 0.8}
        h.update({k: v for k, v in self.mods[i].hero(self.st, p, d, self.params[i]).items()})
        if h["lamp"] is None:
            h["lamp"] = self.lamp_in[i]
        return h

    def _roadside(self, i):
        """Lamps and benches in shot i (1 or 0): the storyboard's "roadside" if set, else while the hero walks."""
        forced = self.shots[i].get("roadside")
        if forced is not None:
            return 1.0 if forced else 0.0
        mod = self.mods[i]
        return 1.0 if getattr(mod, "ROADSIDE", hasattr(mod, "speed")) else 0.0

    def draw(self, cr, t):
        st = self.st
        i = shot_at(self.shots, t)
        st.t = t
        if st.scenery:                      # roadside props fade along with the shot change
            k = ramp(t, self.shots[i]["start"], self.shots[i]["start"] + TRANS) if i > 0 else 1.0
            now, before = self._roadside(i), self._roadside(i - 1) if i > 0 else self._roadside(i)
            st.roadside = lerp(before, now, k)
        cam = self._camera_at(i, t, self.cam_start[i])
        st.cam = Camera(lift=cam["lift"], zoom=cam["zoom"], travel=self.travel[min(len(self.travel) - 1, int(t * FPS))])

        cr.save()
        if abs(st.cam.zoom - 1) > 1e-4:     # zoom about a point above the hero's head
            cx, cy = st.W / 2, st.H * 0.55
            cr.translate(cx, cy)
            cr.scale(st.cam.zoom, st.cam.zoom)
            cr.translate(-cx, -cy)
        st.draw_world(cr, t)

        start = self.shots[i]["start"]
        k_in = ramp(t, start, start + TRANS) if i > 0 else 1.0
        layers = [(i, k_in)]
        if i > 0 and k_in < 1:
            layers.insert(0, (i - 1, 1 - k_in))
        for j, a in layers:
            p, d = self._progress(j, t)
            st.local = self.travel[min(len(self.travel) - 1, int(t * FPS))] - self.travel_start[j]
            self.mods[j].draw(cr, st, p, d, a, self.params[j])

        joints = self._draw_hero(cr, i, t)
        for j, a in layers:
            fn = getattr(self.mods[j], "front", None)
            if fn:
                p, d = self._progress(j, t)
                fn(cr, st, p, d, a, self.params[j], joints)
        cr.restore()

        self._overlays(cr, i, t)

    def _draw_hero(self, cr, i, t):
        st = self.st
        now = self._hero_state(i, t)
        k = ramp(t, self.shots[i]["start"], self.shots[i]["start"] + HERO_BLEND) if i > 0 else 1.0
        if k < 1:
            before = self._hero_state(i - 1, t)
            if before["pose"] is None:
                before["pose"] = now["pose"]
            if now["pose"] is None:
                now["pose"] = before["pose"]
            for key in ("x", "light", "alpha", "scale", "lamp_glow"):
                now[key] = lerp(before[key], now[key], k)
            if before["y"] is not None or now["y"] is not None:
                now["y"] = lerp(before["y"] if before["y"] is not None else st.horizon,
                                now["y"] if now["y"] is not None else st.horizon, k)
            if before["pose"] is not None:
                now["pose"] = H.blend(before["pose"], now["pose"], k)
            if k < 0.5:
                now["facing"], now["lamp"] = before["facing"], before["lamp"]
        if now["pose"] is None:
            now["pose"] = H.pose("look_up")
        ground = now["y"] if now["y"] is not None else st.horizon
        scale = st.s * now["scale"]
        if now["lamp"] == "ground":
            H.lamp(cr, (now["x"] - 58 * scale * now["facing"], ground - 46 * scale), scale, glow=now["lamp_glow"])
        joints = H.draw(cr, now["x"], ground, now["pose"], scale, facing=now["facing"], light=now["light"],
                        alpha=now["alpha"])
        if now["lamp"] is True:
            H.lamp(cr, joints["arm_f"][-1], scale, glow=now["lamp_glow"], alpha=now["alpha"])
        return joints

    def _title_card(self, cr, t):
        """The cover: title over the opening scene.  It is the first frame (so the video never starts black) and
        fades out just before the first word."""
        cover = self.tl.get("cover") or {}
        end = self.shots[0].get("start", 0.0) + narration.LEAD_IN
        a = 1 - ramp(t, end - 0.8, end)
        if a <= 0 or not cover.get("title"):
            return
        st, u = self.st, self.st.u
        portrait = st.portrait
        shade = cairo.LinearGradient(0, 0, 0, st.H * 0.7)
        shade.add_color_stop_rgba(0, 0.03, 0.04, 0.08, 0.55 * a)
        shade.add_color_stop_rgba(1, 0.03, 0.04, 0.08, 0.0)
        cr.set_source(shade)
        cr.paint()
        cx = st.W / 2 if not portrait else st.W * PORTRAIT_WORDS["x"]
        max_w = st.W * (PORTRAIT_WORDS["title_width"] if portrait else 0.8)
        sub, sub_size, sub_rows = cover.get("subtitle", ""), (48 if portrait else 44) * u, []
        if sub:
            sub_rows = [sub]
            if text_width(cr, sub, sub_size) > max_w:
                sub_rows = [r.strip() for r in sub.split("·")] if "·" in sub else wrap(cr, sub, sub_size, max_w)
        # the text block sits above the hero's head and inside the safe area; a title too tall for that
        # space is set smaller
        head_top = st.horizon - 250 * st.s - 30 * u
        min_top = st.H * (0.12 if portrait else 0.06)
        size = (128 if portrait else 120) * u
        while True:
            rows, size = quote_lines(cr, cover["title"], max_w, size)
            height = len(rows) * size * 1.3 + (20 * u + len(sub_rows) * sub_size * 1.45 if sub_rows else 0)
            if head_top - height >= min_top or size < 60 * u:
                break
            size *= 0.92
        top = max(min_top, min(st.H * (PORTRAIT_WORDS["title_top"] if portrait else 0.22), head_top - height))
        for n, row in enumerate(rows):
            text(cr, row, size, cx, top + size * 0.65 + n * size * 1.3, GOLD, a=a, weight=cairo.FONT_WEIGHT_BOLD,
                 glow=a)
        sub_top = top + len(rows) * size * 1.3 + 20 * u
        for n, row in enumerate(sub_rows):
            text(cr, row, sub_size, cx, sub_top + sub_size * 0.7 + n * sub_size * 1.45, WHITE, a=a * 0.9)

    def _overlays(self, cr, i, t):
        st, shot = self.st, self.shots[i]
        u, W, Hh = st.u, st.W, st.H
        portrait = st.portrait
        self._title_card(cr, t)
        # gold quote: fades in rising as the voice says it, holds, fades out as the shot ends
        for j in (i - 1, i):
            if j < 0 or not self.shots[j].get("quote"):
                continue
            q = self.shots[j]
            t0, t1 = q["quote_at"], max(q["end"], q["quote_at"] + 2.6)
            a = ramp(t, t0, t0 + 0.7) * (1 - ramp(t, t1 - 0.3, t1 + 0.5))
            if a <= 0:
                continue
            rise = (1 - ramp(t, t0, t0 + 1.0)) * 24 * u
            lines = quote_lines(cr, q["quote"], W * (PORTRAIT_WORDS["width"] if portrait else 0.86), 92 * u)
            size = lines[1]
            y = Hh * (PORTRAIT_WORDS["quote"] if portrait else 0.20) + rise
            for n, s in enumerate(lines[0]):
                text(cr, s, size, W / 2 if not portrait else W * PORTRAIT_WORDS["x"], y + n * size * 1.3, GOLD, a=a,
                     weight=cairo.FONT_WEIGHT_BOLD, glow=a)
        # corner number (①②③)
        if shot.get("corner"):
            a = ramp(t, shot["start"], shot["start"] + 0.6) * (1 - ramp(t, shot["end"] - 0.4, shot["end"]))
            x, y = (110 * u, 110 * u) if not portrait else (W * PORTRAIT_WORDS["corner"][0], Hh * PORTRAIT_WORDS["corner"][1])
            circle(cr, x, y, 44 * u, 3 * u, GOLD, a=a)
            mark = shot["corner"]
            number = str("①②③④⑤⑥⑦⑧⑨".index(mark) + 1) if mark in "①②③④⑤⑥⑦⑧⑨" else mark
            text(cr, number, 50 * u, x, y - 2 * u, GOLD, a=a, weight=cairo.FONT_WEIGHT_BOLD, shadow=False)
        # subtitles
        for j in (i - 1, i, i + 1):
            if not 0 <= j < len(self.shots):
                continue
            keys = self.shots[j].get("highlight", [])
            for sub in self.shots[j]["subs"]:
                if sub["start"] <= t <= sub["end"]:           # fades stay inside the line's own time
                    a = ramp(t, sub["start"], sub["start"] + 0.12) * (1 - ramp(t, sub["end"] - 0.12, sub["end"]))
                    size = (SUB_SIZE["portrait"] if portrait else SUB_SIZE["landscape"]) * u
                    max_w = W * (PORTRAIT_WORDS["width"] if portrait else 0.82)
                    rows, size = fit_rows(cr, sub["text"], size, max_w, keep=keys)
                    base = Hh * (PORTRAIT_WORDS["sub"] if portrait else 0.895) - (len(rows) - 1) * size * 1.3
                    for n, row in enumerate(rows):
                        parts = [(s, GOLD if gold else WHITE) for s, gold in runs(row, keys)]
                        text_runs(cr, parts, size, W * (PORTRAIT_WORDS["x"] if portrait else 0.5), base + n * size * 1.3, a=a,
                                  outline=0.14)
        # vignette and the fade in / out at the ends
        v = cairo.RadialGradient(W / 2, Hh / 2, min(W, Hh) * 0.35, W / 2, Hh / 2, max(W, Hh) * 0.75)
        v.add_color_stop_rgba(0, 0, 0, 0, 0)
        v.add_color_stop_rgba(1, 0, 0, 0, 0.42)
        cr.set_source(v)
        cr.paint()
        # no fade to black at either end: the video opens on its cover and stops on its last picture, which
        # platforms loop or freeze on


def localized(params: dict, lang: str) -> dict:
    """Scene params for one language: in English, `labels_en` replaces `labels`, `label_en` replaces `label`..."""
    out = {k: v for k, v in params.items() if not k.endswith("_en")}
    if lang == "en":
        out.update({k[:-3]: v for k, v in params.items() if k.endswith("_en")})
    return out


def ramp_lin(t, a, b):
    return min(1.0, max(0.0, (t - a) / (b - a))) if b > a else 1.0


def shot_at(shots, t):
    i = 0
    while i + 1 < len(shots) and t >= shots[i + 1]["start"]:
        i += 1
    return i


SUB_SIZE = {"landscape": 60, "portrait": 68}   # subtitle size in px at 1080: large enough to read on a phone
# where words go in portrait (视频号), as shares of the frame, shared with the robot film (robotfilm/compose.py):
# centred a little left of the middle, clear of the buttons on the right; the subtitles high enough to stay
# clear of the caption bar at the bottom, the gold quote low enough to clear the top bar
PORTRAIT_WORDS = {"x": 0.46, "width": 0.80, "sub": 0.775, "quote": 0.24, "corner": (0.12, 0.19), "title_top": 0.20,
                  "title_width": 0.78}
NO_START = "》」』”’）)、，。：；？！?!:;,."
NO_END = "《「『“‘（("


def _break_points(s: str) -> list[int]:
    """Where a row may end: at spaces, or between CJK characters — never inside a Latin word or a 《title》,
    never before closing punctuation or after an opening mark."""
    points = []
    for k in range(1, len(s)):
        depth = s[:k].count("《") - s[:k].count("》") + s[:k].count("“") - s[:k].count("”")
        if depth or s[k] in NO_START or s[k - 1] in NO_END:
            continue
        if s[k] == " " or s[k - 1] == " " or not (s[k - 1].isascii() and s[k].isascii()):
            points.append(k)
    return points


def _greedy(cr, s, size, width, points, cut=True):
    """Fill rows up to `width`, ending them only at break points.  A word wider than `width` is cut when `cut`
    (better than spilling off screen); with cut=False the answer is None instead."""
    rows, start = [], 0
    while text_width(cr, s[start:].strip(), size) > width:
        fits = [k for k in points if k > start and text_width(cr, s[start:k].strip(), size) <= width]
        if not fits:                     # one word wider than the screen: cut it rather than let it spill
            if not cut:
                return None
            fits = [max(k for k in range(start + 1, len(s)) if text_width(cr, s[start:k], size) <= width)]
        rows.append(s[start:fits[-1]].strip())
        start = fits[-1]
    rows.append(s[start:].strip())
    return [r for r in rows if r]


NUMERALS = "零一二三四五六七八九十百千万亿两双第0123456789"
PAUSE_AFTER = "，、；：。？！ ,;:"
PAUSE_BEFORE = "“《「（"


def runs(s: str, words) -> list[tuple[str, bool]]:
    """`s` cut into (piece, is_keyword) runs.  Longer keywords win; Latin keywords match whole words, any case."""
    words = sorted({w for w in words if w}, key=len, reverse=True)
    if not words:
        return [(s, False)] if s else []
    pattern = "|".join(rf"(?<!\w){re.escape(w)}(?!\w)" if w.isascii() else re.escape(w) for w in words)
    out, pos = [], 0
    for m in re.finditer(pattern, s, re.IGNORECASE):
        if m.start() > pos:
            out.append((s[pos:m.start()], False))
        out.append((m.group(), True))
        pos = m.end()
    if pos < len(s):
        out.append((s[pos:], False))
    return out


def wrap(cr, s, size, max_w, keep=()):
    """Break a subtitle into rows that each fit max_w, as evenly filled as the row count allows.  Two rows break
    where a reader would pause (after punctuation, before a quote) when that keeps both rows fitting.  Words in
    `keep` (the gold keywords) are never broken across rows."""
    inside, pos = set(), 0
    for piece, gold in runs(s, keep):
        if gold:
            inside.update(range(pos + 1, pos + len(piece)))
        pos += len(piece)
    points = [k for k in _break_points(s)
              if not (s[k - 1] in NUMERALS and s[k] in NUMERALS) and k not in inside]  # keep 双十一 whole
    rows = _greedy(cr, s, size, max_w, points)
    if len(rows) == 2:
        fitting = [k for k in points
                   if text_width(cr, s[:k].strip(), size) <= max_w and text_width(cr, s[k:].strip(), size) <= max_w]
        if fitting:
            def cost(k):
                widest = max(text_width(cr, s[:k].strip(), size), text_width(cr, s[k:].strip(), size))
                natural = s[k - 1] in PAUSE_AFTER or s[k] in PAUSE_BEFORE
                return widest + (0 if natural else 0.25 * max_w)
            k = min(fitting, key=cost)
            return [s[:k].strip(), s[k:].strip()]
    width = max_w
    while width > max_w * 0.5:           # narrow the target while the row count stays: balanced rows
        trial = _greedy(cr, s, size, width * 0.96, points, cut=False)
        if trial is None or len(trial) != len(rows):     # narrower would cut a word or add a row: stop
            break
        rows, width = trial, width * 0.96
    return rows


def fit_rows(cr, s, size, max_w, max_rows=2, keep=()):
    """Rows and font size for a subtitle: shrink the text a little (down to 80%) before using more rows."""
    for k in (1.0, 0.92, 0.85, 0.8):
        rows = wrap(cr, s, size * k, max_w, keep)
        if len(rows) <= max_rows:
            return rows, size * k
    return rows, size * 0.8


def quote_lines(cr, q, max_w, size):
    """The quote on one line if it fits, else broken at its comma; shrunk if it still doesn't fit."""
    rows = [q]
    if text_width(cr, q, size, cairo.FONT_WEIGHT_BOLD) > max_w:
        for mark in ("，", "：", ": ", ", "):
            if mark in q:
                head, _, tail = q.partition(mark)
                rows = [head + mark.strip(), tail]
                break
        else:
            if " " in q:
                rows = wrap(cr, q, size, max_w)
    widest = max(text_width(cr, r, size, cairo.FONT_WEIGHT_BOLD) for r in rows)
    if widest > max_w:
        size *= max_w / widest
    return rows, size


# ---------- rendering ----------
def _render_part(args):
    timeline, W, H_, seed, fps, first, last, out = args
    film = Film(timeline, W, H_, seed)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H_}",
                           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H_)
    for f in range(first, last):
        cr = cairo.Context(surf)
        cr.set_antialias(cairo.ANTIALIAS_BEST)
        film.draw(cr, f / fps)
        surf.flush()
        ff.stdin.write(bytes(surf.get_data()))
    ff.stdin.close()
    ff.wait()
    return out


def cover(timeline, W, H_, seed, out: Path) -> Path:
    """The first frame, saved as the cover image."""
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H_)
    Film(timeline, W, H_, seed).draw(cairo.Context(surf), 0.0)
    surf.write_to_png(str(out))
    return out


def render_video(timeline, W, H_, seed, audio, out: Path, fps=FPS, workers=4):
    frames = int(math.ceil(timeline["duration"] * fps))
    with tempfile.TemporaryDirectory(prefix="story-") as tmp:
        cuts = [frames * k // workers for k in range(workers + 1)]
        jobs = [(timeline, W, H_, seed, fps, cuts[k], cuts[k + 1], f"{tmp}/part{k}.mp4") for k in range(workers)]
        with get_context("spawn").Pool(workers) as pool:
            parts = pool.map(_render_part, jobs)
        listing = Path(tmp) / "parts.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(audio),
                        "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                        "-movflags", "+faststart", str(out)], check=True)


def contact_sheet(timeline, W, H_, seed, out: Path, cols=5):
    film = Film(timeline, W, H_, seed)
    shots = timeline["shots"]
    rows = math.ceil(len(shots) / cols)
    tw, th = W // 4, H_ // 4
    sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, tw * cols, th * rows)
    sc = cairo.Context(sheet)
    frame = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H_)
    for n, s in enumerate(shots):
        cr = cairo.Context(frame)
        t = s["start"] + (s["end"] - s["start"]) * 0.7
        film.draw(cr, t)
        sc.save()
        sc.translate((n % cols) * tw, (n // cols) * th)
        sc.scale(0.25, 0.25)
        sc.set_source_surface(frame, 0, 0)
        sc.paint()
        sc.restore()
        text(sc, f"{s['id']} {film.mods[n].TITLE}", 22, (n % cols) * tw + 90, (n // cols) * th + 24, GOLD)
    sheet.write_to_png(str(out))


def load(path: Path) -> tuple[Path, dict]:
    folder = path if path.is_dir() else path.parent
    sb = json.loads((folder / "storyboard.json").read_text(encoding="utf-8"))
    return folder, sb


def main(argv=None):
    ap = argparse.ArgumentParser(prog="story.render", description=__doc__.splitlines()[0])
    ap.add_argument("episode", type=Path)
    ap.add_argument("--portrait", action="store_true",
                    help="both formats for every language (default: Chinese portrait 1080x1920, English landscape)")
    ap.add_argument("--only", choices=list(FORMATS), help="render just this format")
    ap.add_argument("--lang", choices=["zh", "en", "all"], default="all",
                    help="all (default): Chinese, plus English when every shot has narration_en")
    ap.add_argument("--draft", action="store_true", help="contact sheets from estimated timing, no TTS (seconds)")
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--stills", action="store_true")
    args = ap.parse_args(argv)
    folder, sb = load(args.episode)
    for s in sb["shots"]:
        scenes.get(s["scene"])          # fail early on a misspelt scene name
    if sb.get("script"):                # the narration must be the script itself, word for word
        script = Path(sb["script"]).expanduser()
        script = script if script.is_absolute() else configmod.PROJECT / script
        narration.check_script(sb, script.read_text(encoding="utf-8"))
    langs = ["zh", "en"] if args.lang == "all" else [args.lang]
    langs = [lang for lang in langs if lang == "zh" or narration.has_lang(sb, lang)]
    if args.lang == "en" and not langs:
        raise SystemExit("no English version: every shot needs narration_en")
    for lang in langs:
        render_language(folder, sb, lang, args)
    return 0


def render_language(folder: Path, sb: dict, lang: str, args) -> None:
    """Everything for one language: files carry an `_en` tag for English (story_en_landscape.mp4, qa_en.md...)."""
    config = configmod.load()
    build = folder / "build"
    build.mkdir(exist_ok=True)
    tag = "" if lang == "zh" else f"_{lang}"
    seed = zlib.crc32(sb.get("title", "").encode())
    formats = formats_for(lang, args)
    print(f"--- {lang}", flush=True)

    audio, timeline = narration.narrate(sb, config, log=lambda m: print(m, flush=True), draft=args.draft, lang=lang)
    spoken = timeline.pop("_spoken")
    key = "" if lang == "zh" else f"_{lang}"
    timeline["cover"] = {"title": sb.get(f"cover_title{key}", sb.get(f"title{key}", "")),
                         "subtitle": sb.get(f"cover_subtitle{key}", "")}
    for w in narration.waits(timeline):
        print(f"  wait {w['wait_s']:.1f}s after shot {w['id']} ({w['scene']}): {w['narration']}  "
              "-> the line is shorter than the picture: merge it with a neighbouring shot or pick a quicker scene",
              flush=True)
    if args.draft:
        for name in formats:
            out = folder / f"draft{tag}_{name}.png"
            contact_sheet(timeline, *FORMATS[name], seed, out)
            print("wrote", out, flush=True)
        print(f"draft timing about {timeline['duration']:.0f}s", flush=True)
        return
    voice = build / f"voice{tag}.wav"
    narration.save(audio, voice)
    (folder / f"timeline{tag}.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"narration {timeline['duration']:.1f}s, {len(timeline['shots'])} shots", flush=True)
    flagged = narration.listen(spoken, lang)
    write_qa(folder / f"qa{tag}.md", flagged)
    print(f"listening check: {len(flagged)} sentence(s) to review", flush=True)

    for name in formats:
        contact_sheet(timeline, *FORMATS[name], seed, folder / f"contact_sheet{tag}_{name}.png")
    if args.stills:
        return
    final, stats = mix(voice, timeline["duration"], seed, build / lang, music=True)
    print(f"mix {stats['final_lufs']} LUFS, music {stats['music_lufs']} LUFS", flush=True)
    for name in formats:
        W, H_ = FORMATS[name]
        fps = FPS
        if args.preview:
            W, H_, fps = W // 2, H_ // 2, 15
        out = folder / (f"preview{tag}_{name}.mp4" if args.preview else f"story{tag}_{name}.mp4")
        render_video(timeline, W, H_, seed, final, out, fps=fps, workers=min(4, os.cpu_count() or 2))
        embed_artwork(out, cover(timeline, *FORMATS[name], seed, folder / f"cover{tag}_{name}.png"))
        print("wrote", out, flush=True)


def write_qa(path: Path, flagged: list) -> None:
    lines = ["# 配音回听（Whisper 逐句比对）", ""]
    if not flagged:
        lines.append("✅ 每一句都和原文一致，没有听出读错或漏字。")
    for f in flagged:
        lines.append(f"- 🟡 原文“{f['text']}” / 听到“{f['heard']}”（差异 {f['error']:.0%}）")
    if flagged:
        lines += ["", "Whisper 也会听错同音字，被标出的句子不一定真的读错，请试听确认。"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
