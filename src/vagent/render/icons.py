"""Line icons (Tabler Icons outline set, MIT licence: see icons/LICENSE) turned into polylines.

As polylines an icon can be drawn on stroke by stroke (`progress` 0..1). Only the SVG features the
outline set uses are supported: <path> elements with M L H V C S Q T A Z commands (absolute and relative).
"""
from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path
import re

from .canvas import Canvas

ICON_DIR = Path(__file__).with_name("icons")
VIEWBOX = 24.0
STROKE = 2.0  # stroke width in viewBox units
NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
ARGS = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7, "z": 0}

Point = tuple[float, float]


@lru_cache(maxsize=1)
def names() -> frozenset[str]:
    return frozenset(p.stem for p in ICON_DIR.glob("*.svg"))


def _numbers(body: str, command: str) -> list[float]:
    """Arguments of one command; arc flags may be written without separators ("a1 1 0 01 1 1")."""
    if command.lower() != "a":
        return [float(x) for x in NUMBER.findall(body)]
    out: list[float] = []
    i = 0
    while i < len(body):
        if body[i] in " ,\t\n":
            i += 1
            continue
        if len(out) % 7 in (3, 4):  # large-arc and sweep flags are single digits
            out.append(float(body[i]))
            i += 1
            continue
        m = NUMBER.match(body, i)
        if not m:
            raise ValueError(f"bad arc data: {body!r}")
        out.append(float(m.group()))
        i = m.end()
    return out


def _arc(p0: Point, rx: float, ry: float, phi_deg: float, large: bool, sweep: bool, p1: Point) -> list[Point]:
    """Points along an SVG elliptical arc (endpoint parametrisation, SVG spec F.6.5), excluding p0."""
    if rx == 0 or ry == 0 or p0 == p1:
        return [p1]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(phi_deg)
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (p0[0] - p1[0]) / 2, (p0[1] - p1[1]) / 2
    x1, y1 = cos * dx + sin * dy, -sin * dx + cos * dy
    scale = (x1 * x1) / (rx * rx) + (y1 * y1) / (ry * ry)
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx * rx * ry * ry - rx * rx * y1 * y1 - ry * ry * x1 * x1
    den = rx * rx * y1 * y1 + ry * ry * x1 * x1
    coef = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cx1, cy1 = coef * rx * y1 / ry, -coef * ry * x1 / rx
    cx = cos * cx1 - sin * cy1 + (p0[0] + p1[0]) / 2
    cy = sin * cx1 + cos * cy1 + (p0[1] + p1[1]) / 2

    def angle(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    theta = angle(1, 0, (x1 - cx1) / rx, (y1 - cy1) / ry)
    delta = angle((x1 - cx1) / rx, (y1 - cy1) / ry, (-x1 - cx1) / rx, (-y1 - cy1) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(2, int(abs(delta) / math.radians(10)))
    pts = []
    for i in range(1, steps + 1):
        a = theta + delta * i / steps
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        pts.append((cos * ex - sin * ey + cx, sin * ex + cos * ey + cy))
    pts[-1] = p1
    return pts


def _bezier(points: list[Point], steps: int = 12) -> list[Point]:
    """Points along a quadratic or cubic Bezier given its control points, excluding the start."""
    out = []
    for i in range(1, steps + 1):
        u = i / steps
        pts = list(points)
        while len(pts) > 1:
            pts = [(a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u) for a, b in zip(pts, pts[1:])]
        out.append(pts[0])
    return out


def parse_path(d: str) -> list[list[Point]]:
    """SVG path data -> list of polylines (one per subpath), in viewBox units."""
    strokes: list[list[Point]] = []
    current: list[Point] = []
    pos = start = (0.0, 0.0)
    last_ctrl: Point | None = None
    last_cmd = ""
    for command, body in re.findall(r"([MmLlHhVvCcSsQqTtAaZz])([^MmLlHhVvCcSsQqTtAaZz]*)", d):
        lower, rel = command.lower(), command.islower()
        values = _numbers(body, command)
        size = ARGS[lower]
        groups = [values[i:i + size] for i in range(0, len(values), size)] if size else [[]]
        for gi, g in enumerate(groups):
            if size and len(g) < size:
                raise ValueError(f"truncated '{command}' arguments in {d!r}")
            ox, oy = pos if rel else (0.0, 0.0)
            if lower == "m" and gi == 0:
                if len(current) > 1:
                    strokes.append(current)
                pos = start = (g[0] + ox, g[1] + oy)
                current = [pos]
                last_ctrl = None
                continue
            if lower in ("m", "l"):  # extra pairs after a moveto are linetos
                pos = (g[0] + ox, g[1] + oy)
                current.append(pos)
                last_ctrl = None
            elif lower == "h":
                pos = (g[0] + ox, pos[1])
                current.append(pos)
                last_ctrl = None
            elif lower == "v":
                pos = (pos[0], g[0] + (pos[1] if rel else 0.0))
                current.append(pos)
                last_ctrl = None
            elif lower in ("c", "s"):
                if lower == "c":
                    c1 = (g[0] + ox, g[1] + oy)
                    c2, end = (g[2] + ox, g[3] + oy), (g[4] + ox, g[5] + oy)
                else:
                    c1 = (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1]) if last_cmd in "cs" and last_ctrl else pos
                    c2, end = (g[0] + ox, g[1] + oy), (g[2] + ox, g[3] + oy)
                current.extend(_bezier([pos, c1, c2, end]))
                last_ctrl, pos = c2, end
            elif lower in ("q", "t"):
                if lower == "q":
                    c1, end = (g[0] + ox, g[1] + oy), (g[2] + ox, g[3] + oy)
                else:
                    c1 = (2 * pos[0] - last_ctrl[0], 2 * pos[1] - last_ctrl[1]) if last_cmd in "qt" and last_ctrl else pos
                    end = (g[0] + ox, g[1] + oy)
                current.extend(_bezier([pos, c1, end]))
                last_ctrl, pos = c1, end
            elif lower == "a":
                end = (g[5] + ox, g[6] + oy)
                current.extend(_arc(pos, g[0], g[1], g[2], bool(g[3]), bool(g[4]), end))
                pos = end
                last_ctrl = None
            elif lower == "z":
                if current and current[-1] != start:
                    current.append(start)
                if len(current) > 1:
                    strokes.append(current)
                pos, current = start, [start]
                last_ctrl = None
            last_cmd = lower
        last_cmd = lower
    if len(current) > 1:
        strokes.append(current)
    return strokes


@lru_cache(maxsize=256)
def strokes(name: str) -> tuple[tuple[Point, ...], ...]:
    """The icon's strokes as polylines in viewBox units (the invisible 'stroke="none"' frame is skipped)."""
    if name not in names():
        raise KeyError(f"unknown icon {name!r}")
    svg = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8")
    out = []
    for attrs in re.findall(r"<path\b([^>]*)/?>", svg):
        if 'stroke="none"' in attrs:
            continue
        d = re.search(r'\bd="([^"]+)"', attrs)
        if d:
            out.extend(tuple(s) for s in parse_path(d.group(1)))
    return tuple(out)


def _partial(line: tuple[Point, ...], progress: float) -> list[Point]:
    """The first `progress` fraction of a polyline, by length."""
    if progress >= 1:
        return list(line)
    lengths = [math.dist(a, b) for a, b in zip(line, line[1:])]
    target = sum(lengths) * progress
    out = [line[0]]
    for (a, b), seg in zip(zip(line, line[1:]), lengths):
        if target <= seg:
            if seg > 0:
                k = target / seg
                out.append((a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k))
            return out
        out.append(b)
        target -= seg
    return out


def draw(c: Canvas, name: str, cx: float, cy: float, size: float, color, progress: float = 1.0,
         alpha: float = 1.0, under=None) -> None:
    """Draw the icon centred on (cx, cy), `size` px wide; all strokes draw on together as progress goes 0 -> 1."""
    if progress <= 0 or alpha <= 0.004:
        return
    k = size / VIEWBOX
    width = STROKE * k
    for line in strokes(name):
        pts = [(cx + (x - VIEWBOX / 2) * k, cy + (y - VIEWBOX / 2) * k) for x, y in _partial(line, progress)]
        if len(pts) > 1:
            c.line(pts, color, width, alpha, under)
        for px, py in (pts[0], pts[-1]):  # round caps
            c.circle(px, py, width / 2, fill=color, alpha=alpha, under=under)
