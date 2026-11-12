"""Robot style: compose a video from Codex-drawn stills (one per shot, optionally an end frame) plus code.

    .venv/bin/python -m robotfilm.compose <episode folder> [--lang zh|en|all] [--preview] [--sheet]

Needs, in the episode folder: storyboard.json (each shot has "frame", optionally "frame_end", "chart", "labels"),
timeline.json / timeline_en.json and build/voice.wav / voice_en.wav (from `story.render --stills`), frames/*.png.

Everything that moves or has to be exact is code: a slow push-in on every still, cross-fades between stills, a
cross-fade from "frame" to "frame_end" halfway through the voice, drifting ice-blue dust, charts that draw
themselves (wave, bars, trend, ring), labels, the gold quote, ①②③, subtitles with gold keywords and the cover.
Chinese: portrait 1080×1920 (the still fills the frame).  English: landscape 1920×1080 (the still's picture band
is scaled up in the middle of the black frame).  Nothing is uploaded or published.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import tempfile
from multiprocessing import get_context
from pathlib import Path

import cairo

from vagent import config as configmod
from story.render import FPS, PORTRAIT_WORDS as PW, SUB_SIZE, fit_rows, quote_lines, runs
from story.stage import GOLD, WHITE, circle, ramp, text, text_runs
from story import narrate as narration

ICE = (0.55, 0.85, 1.0)
FADE = 0.35                     # cross-fade between two stills
ZOOM = 0.045                    # push-in over a shot
FORMATS = {"zh": ("portrait", 1080, 1920), "en": ("landscape", 1920, 1080)}


class Film:
    def __init__(self, folder: Path, timeline: dict, W: int, H: int):
        self.W, self.H, self.portrait = W, H, H > W
        self.u = min(W, H) / 1080
        self.tl, self.shots = timeline, timeline["shots"]
        self.images = {}
        for s in self.shots:
            for key in ("frame", "frame_end"):
                if s.get(key) and s[key] not in self.images:
                    self.images[s[key]] = cairo.ImageSurface.create_from_png(str(folder / "frames" / s[key]))
        img = next(iter(self.images.values()))
        iw, ih = img.get_width(), img.get_height()
        if self.portrait:                            # the still fills the frame
            self.scale = max(W / iw, H / ih)
            self.ox, self.oy = (W - iw * self.scale) / 2, (H - ih * self.scale) / 2
        else:                                        # its picture band (10%..78% of its height) fills 4%..80%
            self.scale = 0.76 * H / (0.68 * ih)
            self.ox, self.oy = (W - iw * self.scale) / 2, 0.04 * H - 0.10 * ih * self.scale
        self.iw, self.ih = iw, ih
        self.pic = iw * self.scale / 1080              # picture width relative to the portrait frame
        rnd = random.Random(19)
        self.dust = [(rnd.random(), rnd.random(), rnd.uniform(0.6, 1.6), rnd.uniform(0.01, 0.03), rnd.random() * 6.3)
                     for _ in range(46)]

    # image fraction -> screen
    def P(self, fx, fy):
        return self.ox + fx * self.iw * self.scale, self.oy + fy * self.ih * self.scale

    def shot_at(self, t):
        for i, s in enumerate(self.shots):
            if s["start"] <= t < s["end"]:
                return i
        return len(self.shots) - 1

    # ---------- stills ----------
    def _paint_still(self, cr, name, i, t, alpha):
        s = self.shots[i]
        k = ramp(t, s["start"], s["end"])
        z = 1 + ZOOM * k
        img = self.images[name]
        cx, cy = self.P(0.5, 0.45)
        cr.save()
        cr.translate(cx, cy)
        cr.scale(self.scale * z, self.scale * z)
        cr.translate(-0.5 * self.iw, -0.45 * self.ih)
        cr.set_source_surface(img, 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(alpha)
        cr.restore()

    def _shot_picture(self, cr, i, t, alpha=1.0):
        s = self.shots[i]
        if s.get("frame_end"):
            mid = (s["start"] + s["voice_end"]) / 2
            w = ramp(t, mid - 0.4, mid + 0.4)
            if w < 1:
                self._paint_still(cr, s["frame"], i, t, alpha * (1 - w) if w > 0 else alpha)
            if w > 0:
                self._paint_still(cr, s["frame_end"], i, t, alpha * w)
        else:
            self._paint_still(cr, s["frame"], i, t, alpha)

    def _last_frame(self, i):
        s = self.shots[i]
        return s.get("frame_end") or s["frame"]

    # ---------- code effects ----------
    def _dust(self, cr, t):
        W, H, u = self.W, self.H, self.u
        cr.save()
        cr.set_operator(cairo.OPERATOR_ADD)
        for x, y, r, v, ph in self.dust:
            yy = (y - t * v) % 1.0
            a = 0.10 + 0.08 * math.sin(t * 1.3 + ph)
            px, py = x * W, yy * H
            g = cairo.RadialGradient(px, py, 0, px, py, 7 * r * u)
            g.add_color_stop_rgba(0, *ICE, a)
            g.add_color_stop_rgba(1, *ICE, 0)
            cr.set_source(g)
            cr.arc(px, py, 7 * r * u, 0, 2 * math.pi)
            cr.fill()
        cr.restore()

    def _line(self, cr, pts, width, col, a, glow=True):
        if len(pts) < 2 or a <= 0:
            return
        cr.save()
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)
        passes = [(width * 4, 0.10), (width * 2, 0.22), (width, 1.0)] if glow else [(width, 1.0)]
        for w, k in passes:
            cr.move_to(*pts[0])
            for p in pts[1:]:
                cr.line_to(*p)
            cr.set_line_width(w)
            cr.set_source_rgba(*col[:3], a * k)
            cr.stroke()
        cr.restore()

    def _label(self, cr, s, fx, fy, a, size=44, col=WHITE):
        """Text placed on the picture: sized with the picture (it is narrower in the landscape frame)."""
        x, y = self.P(fx, fy)
        text(cr, s, size * self.pic, x, y, col, a=a, weight=cairo.FONT_WEIGHT_BOLD)

    def _chart(self, cr, i, t, lang):
        s = self.shots[i]
        c = s.get("chart")
        if not c:
            return
        a = ramp(t, s["start"] + 0.2, s["start"] + 0.7) * (1 - ramp(t, s["end"] - 0.3, s["end"]))
        if a <= 0:
            return
        k = ramp(t, s["start"] + 0.3, s["voice_end"])                    # how far it has drawn
        x0, y0, x1, y1 = c["box"]
        L = lambda key: c.get(key + ("_en" if lang == "en" else ""), c.get(key, ""))
        u = self.u
        if c["type"] == "wave":
            n = 160
            pts = [self.P(x0 + (x1 - x0) * j / n, (y0 + y1) / 2 - (y1 - y0) * 0.42 * math.sin(j / n * 2 * math.pi * 2.0))
                   for j in range(n + 1)]
            self._line(cr, pts[: max(2, int(n * k) + 1)], 5 * u, ICE, a)
            self._label(cr, L("top"), x0 + (x1 - x0) * 0.125, y0 - 0.02, a * ramp(k, 0.1, 0.3), 40, GOLD)
            self._label(cr, L("bottom"), x0 + (x1 - x0) * 0.375, y1 + 0.025, a * ramp(k, 0.3, 0.5), 40)
        elif c["type"] == "bars":
            base = self.P(0, y1)[1]
            for j, (key, h0, h1, col) in enumerate(((("left"), 0.55, 0.55, WHITE), (("right"), 0.3, 1.0, ICE))):
                fx = x0 + (x1 - x0) * (0.25 + 0.5 * j)
                h = (h0 + (h1 - h0) * k) * (y1 - y0)
                X, top = self.P(fx, y1 - h)
                bw = (x1 - x0) * self.iw * self.scale * 0.26
                cr.rectangle(X - bw / 2, top, bw, base - top)
                cr.set_source_rgba(*col[:3], 0.18 * a)
                cr.fill_preserve()
                cr.set_line_width(3 * u)
                cr.set_source_rgba(*col[:3], 0.9 * a)
                cr.stroke()
                self._label(cr, L(key), fx, y1 + 0.03, a, 40, GOLD if j else WHITE)
        elif c["type"] == "trend":
            n = 160
            trend = lambda f: y1 - (y1 - y0) * (0.15 + 0.55 * f)
            line = [self.P(x0 + (x1 - x0) * j / n, trend(j / n)) for j in range(n + 1)]
            wave = [self.P(x0 + (x1 - x0) * j / n, trend(j / n) - (y1 - y0) * 0.16 * math.sin(j / n * 2 * math.pi * 3))
                    for j in range(n + 1)]
            m = max(2, int(n * k) + 1)
            self._line(cr, line[:m], 4 * u, WHITE, a * 0.8, glow=False)
            self._line(cr, wave[:m], 5 * u, ICE, a)
            self._label(cr, L("line"), x1 - (x1 - x0) * 0.12, trend(1) - 0.045, a * ramp(k, 0.7, 0.9), 38)
            self._label(cr, L("wave"), x0 + (x1 - x0) * 0.18, y0 + 0.01, a * ramp(k, 0.2, 0.4), 38, GOLD)
        elif c["type"] == "ring":
            cx, cy = self.P((x0 + x1) / 2, (y0 + y1) / 2)
            R = (y1 - y0) * self.ih * self.scale * 0.38
            cr.set_line_width(22 * u)
            cr.set_source_rgba(1, 1, 1, 0.15 * a)
            cr.arc(cx, cy, R, 0, 2 * math.pi)
            cr.stroke()
            frac = 0.22 + 0.36 * k
            cr.set_source_rgba(*ICE, 0.95 * a)
            cr.set_line_cap(cairo.LINE_CAP_ROUND)
            cr.arc(cx, cy, R, -math.pi / 2, -math.pi / 2 + frac * 2 * math.pi)
            cr.stroke()
            text(cr, L("center"), 40 * self.pic, cx, cy, WHITE, a=a, weight=cairo.FONT_WEIGHT_BOLD)

    def _labels(self, cr, i, t, lang):
        s = self.shots[i]
        a = ramp(t, s["start"] + 0.3, s["start"] + 0.9) * (1 - ramp(t, s["end"] - 0.3, s["end"]))
        for lab in s.get("labels", []):
            self._label(cr, lab.get("text_en" if lang == "en" else "text", lab["text"]), lab["x"], lab["y"], a,
                        lab.get("size", 44), GOLD if lab.get("gold") else WHITE)

    # ---------- words ----------
    def _cover(self, cr, t):
        cover = self.tl.get("cover") or {}
        end = self.shots[0]["start"] + narration.LEAD_IN
        a = 1 - ramp(t, end - 0.8, end)
        if a <= 0 or not cover.get("title"):
            return
        W, H, u = self.W, self.H, self.u
        shade = cairo.LinearGradient(0, 0, 0, H * 0.5) if self.portrait else cairo.LinearGradient(0, H, 0, H * 0.55)
        shade.add_color_stop_rgba(0, 0, 0, 0, 0.75 * a)
        shade.add_color_stop_rgba(1, 0, 0, 0, 0)
        cr.set_source(shade)
        cr.paint()
        cx = W * PW["x"] if self.portrait else W / 2
        rows, size = quote_lines(cr, cover["title"], W * (PW["title_width"] if self.portrait else 0.8),
                                 (140 if self.portrait else 96) * u)
        # portrait: where the 「一笔」 film puts it (story/render.py); landscape: below the robot's feet, where
        # subtitles go later
        top = H * PW["title_top"] if self.portrait else H * 0.86 - len(rows) * size * 1.3
        for n, row in enumerate(rows):
            text(cr, row, size, cx, top + size * 0.65 + n * size * 1.3, GOLD, a=a, weight=cairo.FONT_WEIGHT_BOLD, glow=a)
        if cover.get("subtitle"):
            text(cr, cover["subtitle"], (52 if self.portrait else 44) * u, cx, top + len(rows) * size * 1.3 + 40 * u,
                 WHITE, a=a * 0.95)

    show_cover = True        # the title card over the first seconds
    show_quotes = True       # the gold quote lines

    def _words(self, cr, i, t):
        W, H, u = self.W, self.H, self.u
        portrait = self.portrait
        if self.show_cover:
            self._cover(cr, t)
        for j in (i - 1, i):
            if not self.show_quotes or j < 0 or not self.shots[j].get("quote"):
                continue
            q = self.shots[j]
            t0, t1 = q["quote_at"], max(q["end"], q["quote_at"] + 2.6)
            a = ramp(t, t0, t0 + 0.7) * (1 - ramp(t, t1 - 0.3, t1 + 0.5))
            if a <= 0:
                continue
            rise = (1 - ramp(t, t0, t0 + 1.0)) * 24 * u
            rows, size = quote_lines(cr, q["quote"], W * (PW["width"] if portrait else 0.86), (92 if portrait else 84) * u)
            y = H * (PW["quote"] if portrait else 0.10) + rise
            for n, row in enumerate(rows):
                text(cr, row, size, W * PW["x"] if portrait else W / 2, y + n * size * 1.3, GOLD, a=a,
                     weight=cairo.FONT_WEIGHT_BOLD, glow=a)
        shot = self.shots[i]
        if shot.get("corner"):
            a = ramp(t, shot["start"], shot["start"] + 0.6) * (1 - ramp(t, shot["end"] - 0.4, shot["end"]))
            x, y = (W * PW["corner"][0], H * PW["corner"][1]) if portrait else (110 * u, 110 * u)
            circle(cr, x, y, 44 * u, 3 * u, GOLD, a=a)
            number = str("①②③④⑤".index(shot["corner"]) + 1)
            text(cr, number, 50 * u, x, y - 2 * u, GOLD, a=a, weight=cairo.FONT_WEIGHT_BOLD, shadow=False)
        for j in (i - 1, i, i + 1):
            if not 0 <= j < len(self.shots):
                continue
            keys = self.shots[j].get("highlight", [])
            for sub in self.shots[j]["subs"]:
                if sub["start"] <= t <= sub["end"]:
                    a = ramp(t, sub["start"], sub["start"] + 0.12) * (1 - ramp(t, sub["end"] - 0.12, sub["end"]))
                    size = SUB_SIZE["portrait" if portrait else "landscape"] * u
                    rows, size = fit_rows(cr, sub["text"], size, W * (PW["width"] if portrait else 0.82), keep=keys)
                    base = H * (PW["sub"] if portrait else 0.895) - (len(rows) - 1) * size * 1.3
                    for n, row in enumerate(rows):
                        parts = [(s, GOLD if gold else WHITE) for s, gold in runs(row, keys)]
                        text_runs(cr, parts, size, W * PW["x"] if portrait else W / 2, base + n * size * 1.3, a=a,
                                  outline=0.14)

    # ---------- a frame ----------
    def draw(self, cr, t, lang):
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        i = self.shot_at(t)
        s = self.shots[i]
        prev_differs = i > 0 and self._last_frame(i - 1) != s["frame"]
        w = ramp(t, s["start"], s["start"] + FADE) if prev_differs else 1.0
        if w < 1:
            self._shot_picture(cr, i - 1, t)
        self._shot_picture(cr, i, t, w)
        self._dust(cr, t)
        self._chart(cr, i, t, lang)
        self._labels(cr, i, t, lang)
        self._words(cr, i, t)


def _render_part(args):
    folder, timeline, W, H, lang, fps, first, last, out = args
    film = Film(Path(folder), timeline, W, H)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}",
                           "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                           "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    for f in range(first, last):
        cr = cairo.Context(surf)
        film.draw(cr, f / fps, lang)
        surf.flush()
        ff.stdin.write(bytes(surf.get_data()))
    ff.stdin.close()
    assert ff.wait() == 0
    return out


def still(folder, timeline, W, H, lang, t, out):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    Film(folder, timeline, W, H).draw(cairo.Context(surf), t, lang)
    surf.write_to_png(str(out))


def sheet(folder, timeline, W, H, lang, out, cols=6):
    """One frame per shot (70% through it), for checking."""
    film = Film(folder, timeline, W, H)
    shots = timeline["shots"]
    tw, th = W // 4, H // 4
    rows = math.ceil(len(shots) / cols)
    big = cairo.ImageSurface(cairo.FORMAT_ARGB32, tw * cols, th * rows)
    sc = cairo.Context(big)
    frame = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    for n, s in enumerate(shots):
        film.draw(cairo.Context(frame), s["start"] + (s["end"] - s["start"]) * 0.7, lang)
        sc.save()
        sc.translate((n % cols) * tw, (n // cols) * th)
        sc.scale(0.25, 0.25)
        sc.set_source_surface(frame, 0, 0)
        sc.paint()
        sc.restore()
        text(sc, str(s["id"]), 26, (n % cols) * tw + 24, (n // cols) * th + 24, GOLD)
    big.write_to_png(str(out))


def merged_timeline(folder: Path, lang: str) -> dict:
    """The narration timeline with this episode's robot fields (frame, chart, labels) from storyboard.json."""
    tag = "" if lang == "zh" else f"_{lang}"
    tl = json.loads((folder / f"timeline{tag}.json").read_text())
    sb = json.loads((folder / "storyboard.json").read_text())
    for t, s in zip(tl["shots"], sb["shots"]):
        for key in ("frame", "frame_end", "chart", "labels"):
            if key in s:
                t[key] = s[key]
    return tl


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("--lang", choices=["zh", "en", "all"], default="all")
    ap.add_argument("--preview", action="store_true", help="half size, 15 fps")
    ap.add_argument("--sheet", action="store_true", help="only the per-shot check sheet")
    args = ap.parse_args(argv)
    folder = args.folder.resolve()
    from vagent.audio.mix import mix
    from vagent.render.engine import embed_artwork
    for lang in (["zh", "en"] if args.lang == "all" else [args.lang]):
        tag = "" if lang == "zh" else f"_{lang}"
        name, W, H = FORMATS[lang]
        tl = merged_timeline(folder, lang)
        sheet(folder, tl, W, H, lang, folder / f"robot_sheet{tag}_{name}.png")
        print("wrote", folder / f"robot_sheet{tag}_{name}.png", flush=True)
        if args.sheet:
            continue
        cover_png = folder / f"robot_cover{tag}_{name}.png"
        still(folder, tl, W, H, lang, 0.0, cover_png)
        final, stats = mix(folder / "build" / f"voice{tag}.wav", tl["duration"], 19, folder / "build" / f"robot_{lang}",
                           music=configmod.music())
        print(f"mix {stats['final_lufs']} LUFS", flush=True)
        fps = FPS
        if args.preview:
            W, H, fps = W // 2, H // 2, 15
        frames = int(math.ceil(tl["duration"] * fps))
        out = folder / (f"robot_preview{tag}_{name}.mp4" if args.preview else f"robot{tag}_{name}.mp4")
        workers = 4
        with tempfile.TemporaryDirectory(prefix="robot-") as tmp:
            cuts = [frames * k // workers for k in range(workers + 1)]
            jobs = [(str(folder), tl, W, H, lang, fps, cuts[k], cuts[k + 1], f"{tmp}/part{k}.mp4") for k in range(workers)]
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
