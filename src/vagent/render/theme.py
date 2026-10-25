"""Visual theme from brand.yaml: colours, font files, and the safe areas per output variant."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

FONT_DIRS = [Path.home() / "Library/Fonts", Path("/Library/Fonts")]
FONT_FILES = {
    "Inter": {"regular": "Inter-Regular.otf", "medium": "Inter-Medium.otf", "bold": "Inter-Bold.otf",
              "black": "Inter-Black.otf"},
    "Noto Sans CJK SC": {"regular": "NotoSansCJKsc-Regular.otf", "medium": "NotoSansCJKsc-Medium.otf",
                         "bold": "NotoSansCJKsc-Bold.otf", "black": "NotoSansCJKsc-Black.otf"},
}


def hex_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=32)
def font_path(family: str, weight: str) -> str:
    name = FONT_FILES[family][weight]
    for directory in FONT_DIRS:
        if (directory / name).exists():
            return str(directory / name)
    raise FileNotFoundError(f"font {family} {weight} ({name}) not installed; run ./install.sh")


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.y + self.h

    def contains(self, other: "Box", tolerance: float = 0.5) -> bool:
        return (other.x >= self.x - tolerance and other.y >= self.y - tolerance
                and other.right <= self.right + tolerance and other.bottom <= self.bottom + tolerance)


@dataclass
class Variant:
    """One output format: size plus where content and subtitles may go."""
    name: str
    width: int
    height: int
    safe: Box            # everything must stay inside
    content: Box         # scene graphics
    subtitles: Box       # subtitle band (bottom-anchored inside)


def variant(name: str, width: int = 1080, height: int = 1920) -> Variant:
    if width < height:
        top, bottom = 0.15 * height, 0.85 * height
        left, right = 0.06 * width, 0.94 * width
        if name == "zh_shipinhao":
            # WeChat Channels overlays like/comment buttons on the right and account info at the bottom
            right = 0.86 * width
            bottom = 0.80 * height
        safe = Box(left, top, right - left, bottom - top)
        subtitles = Box(left, bottom - 0.16 * height, right - left, 0.16 * height)
        content = Box(left, top, right - left, subtitles.y - 0.02 * height - top)
    else:  # 16:9
        safe = Box(0.06 * width, 0.08 * height, 0.88 * width, 0.84 * height)
        subtitles = Box(safe.x, safe.bottom - 0.2 * height, safe.w, 0.2 * height)
        content = Box(safe.x, safe.y, safe.w, subtitles.y - 0.02 * height - safe.y)
    return Variant(name, width, height, safe, content, subtitles)


@dataclass
class Theme:
    lang: str
    background: tuple
    surface: tuple
    text: tuple
    muted: tuple
    accent: tuple
    positive: tuple
    negative: tuple
    family: str
    watermark: str = ""
    extra: dict = field(default_factory=dict)

    def font(self, weight: str = "regular") -> str:
        return font_path(self.family, weight)


def theme(config: dict, lang: str) -> Theme:
    brand = config.get("brand", {})
    colors = {k: hex_rgb(v) for k, v in brand.get("colors", {}).items()}
    fonts = brand.get("fonts", {"en": "Inter", "zh": "Noto Sans CJK SC"})
    return Theme(lang=lang, background=colors.get("background", (14, 17, 22)), surface=colors.get("surface", (23, 27, 34)),
                 text=colors.get("text", (242, 244, 247)), muted=colors.get("muted", (138, 147, 163)),
                 accent=colors.get("accent", (232, 181, 71)), positive=colors.get("positive", (60, 200, 192)),
                 negative=colors.get("negative", (255, 111, 97)), family=fonts[lang],
                 watermark=(brand.get("account") or {}).get("watermark", ""))
