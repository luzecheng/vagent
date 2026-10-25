"""Drawing surface for scenes (2x supersampled) with automatic text fitting.

Every text block drawn is recorded (text, box, font file) so QA can verify
safe areas, overflow and glyph coverage on exactly what was rendered.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math
import re

from PIL import Image, ImageDraw, ImageFont

from .theme import Box

S = 2
CLOSERS = set("，。、；：？！”’）》」』,.;:?!)%")
ZH_PARTICLES = set("的了着过吗呢吧啊呀嘛么地得")
EN_FUNCTION = {"a", "an", "the", "of", "in", "to", "for", "and", "or", "but", "with", "at", "on", "by", "from",
               "as", "your", "my", "our", "their", "this", "that", "is", "are", "not"}
OPENERS = set("“‘（《「『(")


@lru_cache(maxsize=256)
def _font(path: str, px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, px)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def ease_out(x: float) -> float:
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_in_out(x: float) -> float:
    x = clamp(x)
    return x * x * (3 - 2 * x)


def appear(t: float, t0: float, dur: float = 0.5) -> float:
    return ease_out((t - t0) / dur)


def mix(a, b, k: float):
    k = clamp(k)
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))


@dataclass
class TextRecord:
    text: str
    box: Box
    font: str
    size: float


@dataclass
class Fitted:
    lines: list[str]
    size: float
    line_height: float
    widths: list[float]

    @property
    def height(self) -> float:
        return self.line_height * len(self.lines)

    @property
    def width(self) -> float:
        return max(self.widths) if self.widths else 0.0


def _tokens(text: str) -> list[str]:
    """Wrap units: jieba words for Chinese, whitespace words for Latin."""
    if re.search(r"[一-鿿]", text):
        import jieba

        out: list[str] = []
        for word in jieba.lcut(text):
            if out and (word[0] in CLOSERS or out[-1][-1] in OPENERS):
                out[-1] += word  # never start a line with closing punctuation
            else:
                out.append(word)
        return out
    words = text.split(" ")
    return [w + (" " if i < len(words) - 1 else "") for i, w in enumerate(words)]


class Canvas:
    def __init__(self, width: int, height: int, background):
        self.width, self.height = width, height
        self.bg = background
        self.img = Image.new("RGB", (width * S, height * S), background)
        self.d = ImageDraw.Draw(self.img)
        self.records: list[TextRecord] = []

    # colour with opacity over the background (scenes are composed on a flat background)
    def c(self, color, alpha: float = 1.0, under=None):
        surface = mix(self.bg, under, alpha) if under is not None else self.bg
        return mix(surface, color, alpha)

    def measure(self, text: str, font: str, size: float) -> float:
        return self.d.textlength(text, font=_font(font, int(size * S))) / S

    def fit(self, text: str, font: str, box_w: float, box_h: float, size: float, min_size: float = 28,
            max_lines: int = 3, leading: float = 1.25) -> Fitted:
        """Largest size <= `size` at which `text` breaks into <= max_lines balanced lines inside the box.

        Line breaks are chosen by a small dynamic program: lines as even as possible, breaks after
        punctuation preferred, never a line starting with a Chinese particle, never an English line
        ending on a function word.
        """
        tokens = _tokens(text)
        current = size
        while True:
            lines = self._break(tokens, font, current, box_w)
            widths = [self.measure(l, font, current) for l in lines]
            fits = (len(lines) <= max_lines and max(widths, default=0) <= box_w + 0.5
                    and len(lines) * current * leading <= box_h)
            if fits:
                return Fitted(lines, current, current * leading, widths)
            if current <= min_size:
                # last resort: allow extra lines, then go below min_size, rather than overflow
                if max_lines < 8 and len(lines) * current * leading <= box_h:
                    max_lines += 1
                    continue
                if current <= 18:
                    return Fitted(lines, current, current * leading, widths)
                min_size = 18
            current = max(min_size, current * 0.93)

    def _break(self, tokens: list[str], font: str, size: float, box_w: float) -> list[str]:
        n = len(tokens)
        inf = float("inf")
        best, back = [inf] * (n + 1), [0] * (n + 1)
        best[0] = 0.0
        for j in range(1, n + 1):
            for i in range(j - 1, -1, -1):
                line = "".join(tokens[i:j]).strip()
                w = self.measure(line, font, size)
                if w > box_w and j - i > 1:
                    break
                if j == n:
                    penalty = 0.0
                elif tokens[j - 1].rstrip()[-1:] in CLOSERS:
                    penalty = 0.0
                elif tokens[j][:1] in ZH_PARTICLES:
                    penalty = inf
                elif tokens[j - 1].strip().lower() in EN_FUNCTION:
                    penalty = 30.0
                else:
                    penalty = 8.0 if re.search(r"[\u4e00-\u9fff]", tokens[j - 1]) else 2.0
                slack = ((box_w - w) / box_w) ** 2 * 40
                if j == n and j - i == 1 and n > 1 and not re.search(r"[\u4e00-\u9fff]", line):
                    slack += 25  # avoid a lone last English word
                cost = best[i] + slack + penalty + 6
                if cost < best[j]:
                    best[j], back[j] = cost, i
        lines, j = [], n
        while j > 0:
            lines.append("".join(tokens[back[j]:j]).strip())
            j = back[j]
        return lines[::-1]

    def text_block(self, fitted: Fitted, font: str, x: float, y: float, color, align: str = "center",
                   alpha: float = 1.0, under=None, record: bool = True) -> Box:
        """Draw fitted lines; (x, y) is the top-left (align=left) or top-centre (align=center)."""
        if alpha <= 0.004:
            return Box(x, y, 0, 0)
        f = _font(font, int(fitted.size * S))
        top = y
        for line, w in zip(fitted.lines, fitted.widths):
            left = x - w / 2 if align == "center" else x
            self.d.text((left * S, (top + fitted.line_height / 2) * S), line, font=f,
                        fill=self.c(color, alpha, under), anchor="lm")
            top += fitted.line_height
        width = fitted.width
        box = Box(x - width / 2 if align == "center" else x, y, width, fitted.height)
        if record:
            self.records.append(TextRecord(" / ".join(fitted.lines), box, font, fitted.size))
        return box

    def text(self, x, y, s, font, size, color, anchor="mm", alpha=1.0, under=None, record=True):
        if alpha <= 0.004 or not s:
            return
        f = _font(font, int(size * S))
        self.d.text((x * S, y * S), s, font=f, fill=self.c(color, alpha, under), anchor=anchor)
        if record:
            l, t, r, b = self.d.textbbox((x * S, y * S), s, font=f, anchor=anchor)
            self.records.append(TextRecord(s, Box(l / S, t / S, (r - l) / S, (b - t) / S), font, size))

    # ------------------------------------------------------------ shapes
    def rect(self, x, y, w, h, r=0, fill=None, outline=None, width=2, alpha=1.0, under=None):
        if alpha <= 0.004:
            return
        self.d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=r * S,
                                 fill=self.c(fill, alpha, under) if fill else None,
                                 outline=self.c(outline, alpha, under) if outline else None,
                                 width=max(1, int(width * S)))

    def circle(self, cx, cy, r, fill=None, outline=None, width=2, alpha=1.0, under=None):
        if alpha <= 0.004:
            return
        self.d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S],
                       fill=self.c(fill, alpha, under) if fill else None,
                       outline=self.c(outline, alpha, under) if outline else None, width=max(1, int(width * S)))

    def line(self, pts, color, width=3, alpha=1.0, under=None):
        if alpha <= 0.004 or len(pts) < 2:
            return
        self.d.line([(x * S, y * S) for x, y in pts], fill=self.c(color, alpha, under), width=max(1, int(width * S)),
                    joint="curve")

    def polygon(self, pts, fill, alpha=1.0, under=None):
        if alpha <= 0.004:
            return
        self.d.polygon([(x * S, y * S) for x, y in pts], fill=self.c(fill, alpha, under))

    def arrow(self, a, b, color, width=4, head=18, alpha=1.0, under=None):
        self.line([a, b], color, width, alpha, under)
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        p1 = (b[0] - head * math.cos(ang - 0.45), b[1] - head * math.sin(ang - 0.45))
        p2 = (b[0] - head * math.cos(ang + 0.45), b[1] - head * math.sin(ang + 0.45))
        self.polygon([b, p1, p2], color, alpha, under)

    def check(self, cx, cy, size, color, width=6, alpha=1.0, under=None):
        self.line([(cx - size * 0.42, cy), (cx - size * 0.1, cy + size * 0.3), (cx + size * 0.45, cy - size * 0.32)],
                  color, width, alpha, under)

    def bang(self, cx, cy, size, color, alpha=1.0, under=None):
        """'!' mark drawn as shapes (independent of font glyphs)."""
        self.rect(cx - size * 0.07, cy - size * 0.42, size * 0.14, size * 0.55, r=size * 0.07, fill=color,
                  alpha=alpha, under=under)
        self.circle(cx, cy + size * 0.32, size * 0.08, fill=color, alpha=alpha, under=under)

    def finish(self) -> Image.Image:
        return self.img.resize((self.width, self.height), Image.LANCZOS)
