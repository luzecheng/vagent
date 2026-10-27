"""Video engine.

1. Each scene renders to its own clip (PIL frames -> ffmpeg), cached by a hash
   of everything that affects its pixels, in parallel across scenes. Frames get
   the shared motion layer (camera push, transitions, light field; see motion.py).
2. Each subtitle screen renders to one transparent PNG (cheap).
3. One ffmpeg pass concatenates the clips, overlays every subtitle PNG during
   its time window (plus an optional watermark), and muxes the audio.
Changing only subtitles re-runs step 2-3; changing one scene re-renders only
that clip.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass, field, replace
import json
import os
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

from .. import cache as cachemod
from . import motion
from .canvas import Canvas
from .components import Ctx, draw
from .theme import Box, Theme, Variant

ENGINE_REV = 4


def _code_fingerprint() -> str:
    """Hash of the drawing code: editing a component, the canvas or the theme invalidates cached clips."""
    import hashlib

    here = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for name in ("components.py", "canvas.py", "theme.py", "engine.py", "motion.py"):
        digest.update((here / name).read_bytes())
    return digest.hexdigest()[:16]


CODE = _code_fingerprint()


@dataclass
class SceneSpec:
    id: str
    component: str
    params: dict
    start: float
    end: float
    reveals: list[float] = field(default_factory=list)  # absolute times
    scale: float = 1.0                                   # text scale chosen by fit_scene()


@dataclass
class SubtitleImage:
    path: str
    start: float
    end: float
    x: int
    y: int
    lines: list[str]
    box: Box
    size: float


def _scene_key(scene: SceneSpec, theme: Theme, variant: Variant, fps: int) -> str:
    local = [round(r - scene.start, 3) for r in scene.reveals]
    # the light field depends on the absolute start time, so a scene that moved re-renders
    return cachemod.key(ENGINE_REV, CODE, scene.component, scene.params, round(scene.start, 3),
                        round(scene.end - scene.start, 3), local, round(scene.scale, 3), asdict(theme),
                        asdict(variant), fps)


def render_frame(scene: SceneSpec, t_local: float, theme: Theme, variant: Variant) -> tuple[Image.Image, list]:
    duration = scene.end - scene.start
    canvas = Canvas(variant.width, variant.height, theme.background)
    centre = motion.pivot(variant.content)
    # lay out in a content area shrunk by the camera push, so the push never carries text past the real edge
    layout = replace(variant, content=motion.scale_box(variant.content, 1 / (1 + motion.PUSH), centre))
    ctx = Ctx(theme, layout, duration, [r - scene.start for r in scene.reveals], scene.scale)
    draw(canvas, scene.component, t_local, scene.params, ctx)
    scale, alpha = motion.zoom_alpha(t_local, duration)
    image = motion.transform(canvas.img, scale, centre, variant.width, variant.height, theme.background)
    if alpha < 1.0:
        image = Image.blend(Image.new("RGB", image.size, theme.background), image, max(0.0, alpha))
    light = motion.light_field(scene.start + t_local, variant.width, variant.height,
                               {"accent": theme.accent, "positive": theme.positive})
    records = [replace(r, box=motion.scale_box(r.box, scale, centre)) for r in canvas.records]
    return motion.add_light(image, light), records


def fit_scene(scene: SceneSpec, theme: Theme, variant: Variant) -> list[str]:
    """Auto-fix: shrink the scene's text until every block sits inside the content area.

    Probes the fully revealed frame; returns a note for the report when it had to shrink.
    """
    from ..qa.layout import outside

    probe_t = max(0.0, scene.end - scene.start - motion.LEAVE - 0.05)
    for scale in (1.0, 0.9, 0.8, 0.7, 0.6, 0.5):
        scene.scale = scale
        _, records = render_frame(scene, probe_t, theme, variant)
        bad = outside(records, variant.content)
        if not bad:
            return [] if scale == 1.0 else [f"scene {scene.id}: text scaled to {scale:.0%} to fit"]
    return [f"scene {scene.id}: still overflowing at 50% text scale: {bad}"]


def _render_clip(job) -> tuple[str, str, list]:
    scene, theme, variant, fps, path = job
    frames = max(1, round((scene.end - scene.start) * fps))
    tmp = path + ".tmp.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s",
           f"{variant.width}x{variant.height}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "16", "-pix_fmt", "yuv420p", tmp]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    records = []
    for n in range(frames):
        image, recs = render_frame(scene, n / fps, theme, variant)
        if n == frames // 2 or n == frames - int(motion.LEAVE * fps) - 1:  # mid-scene and fully revealed frames
            records.extend((r.text, asdict(r.box), r.font, r.size) for r in recs)
        proc.stdin.write(image.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed while encoding scene {scene.id}")
    os.replace(tmp, path)
    return scene.id, path, records


def render_scenes(scenes: list[SceneSpec], theme: Theme, variant: Variant, fps: int, cache_root: str,
                  log, workers: int | None = None) -> list[dict]:
    """Return [{"id", "path", "records"}] for every scene, rendering only those not cached."""
    store = cachemod.Cache(cache_root, f"scenes/{variant.name}")
    results, jobs = {}, []
    for scene in scenes:
        for note in fit_scene(scene, theme, variant):
            log.event("render", note, autofix=True)
        digest = _scene_key(scene, theme, variant, fps)
        path = str(store.path(digest, ".mp4"))
        meta = store.get_json(digest)
        if meta is not None and Path(path).exists():
            results[scene.id] = {"id": scene.id, "path": path, "records": meta["records"], "cached": True}
        else:
            jobs.append((scene, theme, variant, fps, path))
    if jobs:
        workers = workers or max(1, min(len(jobs), (os.cpu_count() or 2) - 1))
        with ProcessPoolExecutor(workers) as pool:
            for scene_id, path, records in pool.map(_render_clip, jobs):
                digest = Path(path).stem
                store.put_json(digest, {"records": records})
                results[scene_id] = {"id": scene_id, "path": path, "records": records, "cached": False}
    log.event("render", f"{variant.name}: {len(scenes)} scenes ({len(jobs)} rendered, {len(scenes) - len(jobs)} cached)")
    return [results[s.id] for s in scenes]


# ---------------------------------------------------------------- subtitles
def subtitle_images(screens: list[dict], theme: Theme, variant: Variant, out_dir: Path) -> list[SubtitleImage]:
    out_dir.mkdir(parents=True, exist_ok=True)
    band = variant.subtitles
    font_path = theme.font("bold")
    base = 60 if theme.lang == "zh" else 52
    stroke = 7
    images = []
    for i, screen in enumerate(screens):
        size = base
        while True:
            font = ImageFont.truetype(font_path, size)
            widths = [font.getlength(line) for line in screen["lines"]]
            if max(widths) <= band.w - 2 * stroke or size <= 34:
                break
            size -= 2
        line_h = int(size * 1.32)
        width = int(max(widths) + 2 * stroke + 8)
        height = int(line_h * len(screen["lines"]) + 2 * stroke + 8)
        img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        for li, line in enumerate(screen["lines"]):
            d.text((width / 2, stroke + 4 + li * line_h + line_h / 2), line, font=font, anchor="mm",
                   fill=theme.text + (255,), stroke_width=stroke, stroke_fill=(0, 0, 0, 235))
        x = int(band.x + (band.w - width) / 2)
        y = int(band.bottom - height)  # bottom-anchored inside the band
        path = out_dir / f"sub_{i:03d}.png"
        img.save(path)
        images.append(SubtitleImage(str(path), screen["start"], screen["end"], x, y, screen["lines"],
                                    Box(x, y, width, height), size))
    return images


def watermark_image(text: str, theme: Theme, variant: Variant, out_dir: Path) -> tuple[str, int, int] | None:
    if not text:
        return None
    font = ImageFont.truetype(theme.font("medium"), 30)
    w = int(font.getlength(text)) + 8
    img = Image.new("RGBA", (w, 44), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((4, 22), text, font=font, anchor="lm", fill=theme.muted + (170,))
    path = out_dir / "watermark.png"
    img.save(path)
    return str(path), int(variant.safe.right - w), int(variant.safe.y)


# ---------------------------------------------------------------- final composite
def still_clip(image: Path, seconds: float, fps: int, out: Path) -> Path:
    """A clip showing one image, encoded like the scene clips so they concatenate cleanly."""
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(fps), "-i", str(image),
                    "-frames:v", str(max(1, round(seconds * fps))), "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "16", "-pix_fmt", "yuv420p", "-r", str(fps), str(out)], check=True)
    return out


def embed_artwork(video: Path, image: Path) -> None:
    """Store the cover inside the MP4 as its artwork (Finder / players show it as the file's picture)."""
    tmp = video.with_suffix(".art.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-i", str(image), "-map", "0", "-map", "1",
                    "-c", "copy", "-disposition:v:1", "attached_pic", "-movflags", "+faststart", str(tmp)], check=True)
    os.replace(tmp, video)


def composite(clips: list[dict], subtitles: list[SubtitleImage], audio: Path, out: Path, variant: Variant,
              fps: int, work: Path, watermark=None, duration: float | None = None) -> None:
    work.mkdir(parents=True, exist_ok=True)
    listing = work / "clips.txt"
    # concat resolves relative paths against the listing's own folder, so list absolute, quote-escaped paths
    entries = [str(Path(c["path"]).resolve()).replace("'", "'\\''") for c in clips]
    listing.write_text("".join(f"file '{e}'\n" for e in entries), encoding="utf-8")
    inputs = ["-f", "concat", "-safe", "0", "-i", str(listing), "-i", str(audio)]
    overlays = list(subtitles)
    for sub in overlays:
        inputs += ["-i", sub.path]
    filters, last = [], "0:v"
    for index, sub in enumerate(overlays):
        tag = f"v{index}"
        filters.append(f"[{last}][{index + 2}:v]overlay=x={sub.x}:y={sub.y}:"
                       f"enable='between(t,{sub.start:.3f},{sub.end:.3f})'[{tag}]")
        last = tag
    if watermark:
        path, wx, wy = watermark
        inputs += ["-i", path]
        filters.append(f"[{last}][{len(overlays) + 2}:v]overlay=x={wx}:y={wy}[wm]")
        last = "wm"
    graph = work / "filters.txt"
    graph.write_text(";\n".join(filters) if filters else f"[0:v]null[out]", encoding="utf-8")
    final_label = last if filters else "out"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-/filter_complex", str(graph),
           "-map", f"[{final_label}]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
           "-pix_fmt", "yuv420p", "-r", str(fps), "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd.append(str(out))
    subprocess.run(cmd, check=True)
    (work / "subtitles.json").write_text(json.dumps([asdict(s) for s in subtitles], ensure_ascii=False, default=str),
                                         encoding="utf-8")
