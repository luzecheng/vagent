"""Motion shared by every scene: a slowly drifting light field, a camera push and scene transitions.

Components draw on a flat background exactly as before; the engine then
- scales the frame about the content centre (camera push, zoom in/out on scene changes),
- blends towards the flat background at scene edges,
- adds the light field on top. It is additive and a function of the video's absolute time,
  so it flows on across scene cuts instead of restarting with each scene.
"""
from __future__ import annotations

from functools import lru_cache
import math

import numpy as np
from PIL import Image

from .canvas import clamp, ease_in_out, ease_out
from .theme import Box

PUSH = 0.022        # slow push-in across a scene (2.2 %)
ENTER = 0.42        # seconds: the new scene grows in from ENTER_SCALE
ENTER_SCALE = 0.94
LEAVE = 0.28        # seconds: the old scene fades while growing by LEAVE_GROW
LEAVE_GROW = 0.05
FIELD_SCALE = 8     # the light field is computed at 1/8 resolution and upscaled (it is very soft)

# (colour key, strength, radius as a fraction of the width, path speeds and phases)
LIGHTS = (("accent", 0.11, 0.55, (0.11, 0.07), (0.0, 1.3)),
          ("positive", 0.08, 0.60, (0.08, 0.05), (2.1, 4.0)),
          ("cool", 0.07, 0.50, (0.05, 0.09), (4.2, 0.7)))
COOL = (90, 120, 255)


def zoom_alpha(t: float, dur: float) -> tuple[float, float]:
    """Scale factor and opacity of the scene at local time t."""
    push = 1 + PUSH * ease_in_out(t / dur if dur > 0 else 1.0)
    enter = ease_out(t / ENTER)
    leave = 1 - clamp((dur - t) / LEAVE)          # 0 until the last LEAVE seconds, then -> 1
    scale = push * (ENTER_SCALE + (1 - ENTER_SCALE) * enter) * (1 + LEAVE_GROW * leave * leave)
    alpha = min(clamp(t / ENTER * 1.6), clamp((dur - t) / LEAVE))
    return scale, alpha


def pivot(content: Box) -> tuple[float, float]:
    return content.x + content.w / 2, content.y + content.h / 2


def transform(frame: Image.Image, scale: float, centre: tuple[float, float], width: int, height: int,
              background) -> Image.Image:
    """Scale a (possibly supersampled) frame about `centre` (output pixels) into a width x height image."""
    ss = frame.width / width
    if abs(scale - 1.0) < 1e-4:
        return frame.resize((width, height), Image.LANCZOS) if ss != 1 else frame
    cx, cy = centre
    if scale > 1:
        # crop the region that maps onto the output, then resize it up to full size
        w, h = width / scale, height / scale
        left, top = cx - cx / scale, cy - cy / scale
        box = (left * ss, top * ss, (left + w) * ss, (top + h) * ss)
        return frame.resize((width, height), Image.LANCZOS, box=box)
    small = frame.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.LANCZOS)
    out = Image.new("RGB", (width, height), background)
    out.paste(small, (round(cx - cx * scale), round(cy - cy * scale)))
    return out


def scale_box(box: Box, scale: float, centre: tuple[float, float]) -> Box:
    cx, cy = centre
    return Box(cx + (box.x - cx) * scale, cy + (box.y - cy) * scale, box.w * scale, box.h * scale)


@lru_cache(maxsize=8)
def _grid(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    w, h = max(2, width // FIELD_SCALE), max(2, height // FIELD_SCALE)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float32)
    return xs / (w - 1), ys / (h - 1) * (height / width)


def light_field(t: float, width: int, height: int, colours: dict) -> np.ndarray:
    """Additive RGB light (uint8, full size) at absolute time t: soft blobs drifting on slow Lissajous paths."""
    xs, ys = _grid(width, height)
    aspect = height / width
    field = np.zeros(xs.shape + (3,), np.float32)
    for key, strength, radius, (sx, sy), (px, py) in LIGHTS:
        colour = np.array(COOL if key == "cool" else colours[key], np.float32)
        bx = 0.5 + 0.38 * math.sin(sx * t + px)
        by = aspect * (0.5 + 0.36 * math.cos(sy * t + py))
        d2 = (xs - bx) ** 2 + (ys - by) ** 2
        field += np.exp(-d2 / (2 * (radius * 0.5) ** 2))[..., None] * colour * strength
    small = Image.fromarray(np.clip(field, 0, 255).astype(np.uint8))
    return np.asarray(small.resize((width, height), Image.BILINEAR))


def add_light(image: Image.Image, light: np.ndarray) -> Image.Image:
    out = np.asarray(image).astype(np.uint16) + light
    return Image.fromarray(np.minimum(out, 255).astype(np.uint8))
