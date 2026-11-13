"""Scene component library.

Each component = a pydantic parameter model (used for storyboard validation)
+ a draw function `draw(canvas, t, params, ctx)`, t = seconds since the scene
started.  `ctx.reveals` holds local times at which successive items should
appear (taken from the narration), so lists reveal in sync with the voice.

Data red line: numeric charts only plot values that come from the script
(the planner must cite them); without values a chart is drawn as an
unlabelled schematic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from . import icons
from .canvas import Canvas, appear, clamp, ease_out, mix
from .theme import Theme, Variant


@dataclass
class Ctx:
    theme: Theme
    variant: Variant
    dur: float
    reveals: list[float] = field(default_factory=list)
    scale: float = 1.0  # global text scale; the engine lowers it when a scene would overflow

    @property
    def lang(self) -> str:
        return self.theme.lang

    def reveal(self, i: int, default_gap: float = 0.9) -> float:
        if i < len(self.reveals):
            return self.reveals[i]
        last = self.reveals[-1] if self.reveals else 0.2
        return last + (i - len(self.reveals) + 1) * default_gap


def _rise(t: float, t0: float, dist: float = 40) -> tuple[float, float]:
    k = appear(t, t0, 0.55)
    return k, (1 - k) * dist


# ---------------------------------------------------------------- parameter models
def _icon_field():
    return Field("", description="optional icon name from the icon list; '' for none")


def _icons_field():
    return Field(default_factory=list, description="optional icon names from the icon list, one per item; [] for none")


def _check_icons(entries: list, names: list[str], what: str) -> None:
    if len(names) > len(entries):
        raise ValueError(f"more icons than {what} ({len(names)} > {len(entries)})")


class Hook(BaseModel):
    text: str = Field(description="The most striking line of the script, verbatim or lightly trimmed (<= 22 zh chars / 60 en chars)")
    sub: str = ""
    layout: Literal[0, 1] = 0
    icon: str = _icon_field()


class Keyword(BaseModel):
    word: str = Field(description="1-6 zh chars / 1-3 en words")
    caption: str = ""
    layout: Literal[0, 1] = 0
    icon: str = _icon_field()


class Card(BaseModel):
    title: str
    text: str = ""
    mark: Literal["check", "warn"] = "check"
    icon: str = Field("", description="optional icon name from the icon list, shown instead of the mark symbol")


class CompareCards(BaseModel):
    left: Card
    right: Card


class Trend(BaseModel):
    direction: Literal["up", "down", "volatile_up", "volatile_down", "flat"] = "up"
    values: list[float] = Field(default_factory=list, description="ONLY numbers stated in the script; else empty")
    value_source_sentence: int | None = None
    start_label: str = ""
    end_label: str = ""
    caption: str = ""


class ShortVsLong(BaseModel):
    short_label: str
    short_text: str = ""
    long_label: str
    long_text: str = ""


class TimelineItem(BaseModel):
    label: str
    text: str = ""
    icon: str = _icon_field()


class Timeline(BaseModel):
    items: list[TimelineItem] = Field(min_length=2, max_length=5)


class Bar(BaseModel):
    label: str
    value: float | None = Field(None, description="ONLY a number stated in the script")


class Bars(BaseModel):
    items: list[Bar] = Field(min_length=2, max_length=5)
    caption: str = ""
    value_source_sentence: int | None = None


class BigNumber(BaseModel):
    value: str = Field(description="exactly as in the script, e.g. '80%' or '10 年'")
    caption: str = ""
    value_source_sentence: int


class Quote(BaseModel):
    text: str
    attribution: str = ""


class Checklist(BaseModel):
    title: str = ""
    items: list[str] = Field(min_length=2, max_length=5)
    icons: list[str] = _icons_field()
    mode: Literal["numbered", "ticks"] = Field("numbered", description="'ticks': each item is ticked off as it is said")

    @model_validator(mode="after")
    def _icons_fit(self):
        _check_icons(self.items, self.icons, "items")
        return self


class Strike(BaseModel):
    old: str
    new: str


class ThreeThings(BaseModel):
    title: str
    items: list[str] = Field(min_length=3, max_length=3)
    icons: list[str] = _icons_field()

    @model_validator(mode="after")
    def _icons_fit(self):
        _check_icons(self.items, self.icons, "items")
        return self


class QuestionStack(BaseModel):
    questions: list[str] = Field(min_length=2, max_length=5)


class ChoiceConsequence(BaseModel):
    choices: list[str] = Field(min_length=1, max_length=3)
    consequence: str
    note: str = ""


class Punchline(BaseModel):
    text: str
    highlight: str = Field("", description="substring of text to colour in the accent colour")


class Pan(BaseModel):
    label: str = Field(description="what lies on this side, 2-8 zh chars / 1-3 en words")
    icon: str = _icon_field()


class Balance(BaseModel):
    left: Pan
    right: Pan
    heavier: Literal["left", "right", "even"] = Field("even", description="the side the beam tips down to")
    caption: str = ""


class Cycle(BaseModel):
    steps: list[str] = Field(min_length=3, max_length=4, description="steps of the loop, in order, 2-6 zh chars each")
    icons: list[str] = _icons_field()
    center: str = Field("", description="optional short label in the middle of the loop")

    @model_validator(mode="after")
    def _icons_fit(self):
        _check_icons(self.steps, self.icons, "steps")
        return self


class Speech(BaseModel):
    who: Literal["me", "other"] = Field(description="'me' = the narrator / inner voice (right), 'other' = left")
    text: str


class Dialogue(BaseModel):
    lines: list[Speech] = Field(min_length=2, max_length=4)


# ---------------------------------------------------------------- helpers
def _area(ctx: Ctx):
    box = ctx.variant.content
    return box.x, box.y, box.w, box.h, box.x + box.w / 2, box.y + box.h / 2


def _block(c: Canvas, ctx: Ctx, text: str, weight: str, size: float, w: float, h: float, x: float, y: float,
           color, alpha: float, align: str = "center", max_lines: int = 3, min_size: float = 30, under=None):
    font = ctx.theme.font(weight)
    fitted = c.fit(text, font, w, h, size * ctx.scale, min_size=min_size * ctx.scale, max_lines=max_lines)
    return c.text_block(fitted, font, x, y, color, align, alpha, under)


def _block_mid(c: Canvas, ctx: Ctx, text: str, weight: str, size: float, w: float, h: float, x: float,
               mid_y: float, color, alpha: float, align: str = "left", max_lines: int = 2, min_size: float = 30,
               under=None):
    """Like _block, but vertically centred on mid_y."""
    font = ctx.theme.font(weight)
    fitted = c.fit(text, font, w, h, size * ctx.scale, min_size=min_size * ctx.scale, max_lines=max_lines)
    return c.text_block(fitted, font, x, mid_y - fitted.height / 2, color, align, alpha, under)


def _top_for(ctx: Ctx, group_h: float, bias: float = 0.42) -> float:
    """Top y that places a group of height group_h slightly above the content centre."""
    box = ctx.variant.content
    return box.y + max(0.0, (box.h - group_h) * bias)


# a slightly uneven tick, in units of the box size, centred on the box
TICK = ((-0.34, 0.02), (-0.2, 0.15), (-0.06, 0.3), (0.08, 0.1), (0.24, -0.14), (0.4, -0.38))


def _draw_on(t: float, t0: float, dur: float = 0.8) -> float:
    """Stroke progress for an icon drawn on from t0."""
    return ease_out((t - t0) / dur)


def _icon_at(items_icons: list[str], i: int) -> str:
    return items_icons[i] if i < len(items_icons) else ""


def _ordinal(i: int, lang: str) -> str:
    return ["第一", "第二", "第三", "第四", "第五"][i] if lang == "zh" else ["One", "Two", "Three", "Four", "Five"][i]


# ---------------------------------------------------------------- components
def hook(c: Canvas, t: float, p: Hook, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    bar = appear(t, 0.0, 0.5)
    font = th.font("black")
    fitted = c.fit(p.text, font, w * 0.92, h * 0.5, 100 if ctx.lang == "zh" else 88, min_size=48, max_lines=3)
    icon_h = 200 if p.icon else 0
    group = fitted.height + (110 if p.sub else 0) + 40 + icon_h
    top = _top_for(ctx, group) + icon_h
    if p.layout == 0:
        if p.icon:
            icons.draw(c, p.icon, cx, top - icon_h + 40, 150, th.accent, _draw_on(t, 0.0, 0.9))
        c.rect(cx - 60 * bar, top - 40, 120 * bar, 8, r=4, fill=th.accent)
        box = c.text_block_kinetic(fitted, font, cx, top, th.text, t, 0.1)
        if p.sub:
            _block(c, ctx, p.sub, "medium", 40, w * 0.85, 120, cx, box.bottom + 40, th.muted, appear(t, 0.7))
    else:
        fitted = c.fit(p.text, font, w * 0.86, h * 0.5, 96 if ctx.lang == "zh" else 84, min_size=48, max_lines=3)
        if p.icon:
            icons.draw(c, p.icon, x + 50 + 70, top - icon_h + 60, 140, th.accent, _draw_on(t, 0.0, 0.9))
        c.rect(x + 10, top, 10, fitted.height * bar, r=5, fill=th.accent)
        box = c.text_block_kinetic(fitted, font, x + 50, top, th.text, t, 0.1, align="left")
        if p.sub:
            _block(c, ctx, p.sub, "medium", 38, w * 0.8, 120, x + 50, box.bottom + 36, th.muted, appear(t, 0.7),
                   align="left")


def keyword(c: Canvas, t: float, p: Keyword, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    font = th.font("black")
    fitted = c.fit(p.word, font, w * 0.9, h * 0.35, 140 * ctx.scale, min_size=60 * ctx.scale, max_lines=2)
    if p.icon:
        icons.draw(c, p.icon, cx, cy - h * 0.16 - 130, 160, th.text, _draw_on(t, 0.0, 0.9))
    box = c.text_block_kinetic(fitted, font, cx, cy - h * 0.16, th.accent, t, 0.1, step=0.08, dur=0.45, rise=0.45)
    sweep = appear(t, 0.1 + 0.08 * len(p.word) + 0.2, 0.6)
    c.rect(cx - box.w / 2, box.bottom + 18, box.w * sweep, 8, r=4, fill=th.accent, alpha=0.9)
    if p.caption:
        _block(c, ctx, p.caption, "medium", 42, w * 0.85, 160, cx, box.bottom + 60, th.text, appear(t, 0.8))


def compare_cards(c: Canvas, t: float, p: CompareCards, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    card_h = min(h * 0.42, 400)
    first = _top_for(ctx, 2 * card_h + 40, 0.5)
    for i, card in enumerate((p.left, p.right)):
        k, dy = _rise(t, ctx.reveal(i, 1.2))
        top = first + i * (card_h + 40) + dy
        color = th.positive if card.mark == "check" else th.negative
        c.rect(x, top, w, card_h, r=28, fill=th.surface, outline=mix(th.surface, color, 0.8), width=3, alpha=k)
        disc = mix(th.surface, color, 0.25)
        c.circle(x + 80, top + 80, 40, fill=disc, alpha=k, under=th.surface)
        if card.icon:
            icons.draw(c, card.icon, x + 80, top + 80, 48, color, _draw_on(t, ctx.reveal(i, 1.2) + 0.1), k, disc)
        elif card.mark == "check":
            c.check(x + 80, top + 80, 44, color, 7, k, under=th.surface)
        else:
            c.bang(x + 80, top + 80, 64, color, k, under=th.surface)
        title = _block(c, ctx, card.title, "bold", 52, w - 200, 140, x + 150, top + 48, th.text, k, align="left",
                       max_lines=2, under=th.surface)
        if card.text:
            _block(c, ctx, card.text, "regular", 38, w - 120, card_h - (title.bottom - top) - 50, x + 60,
                   title.bottom + 24, th.muted, k, align="left", max_lines=3, under=th.surface)


def _series(direction: str, n: int = 60) -> list[float]:
    pts = []
    for i in range(n):
        u = i / (n - 1)
        base = {"up": u, "down": 1 - u, "flat": 0.5, "volatile_up": u, "volatile_down": 1 - u}[direction]
        wobble = 0.12 * math.sin(u * 13) * (1 - 0.5 * u) if direction.startswith("volatile") else 0.02 * math.sin(u * 7)
        pts.append(clamp(0.1 + 0.8 * base + wobble, 0, 1))
    return pts


def trend(c: Canvas, t: float, p: Trend, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    left, top, cw, ch = x + 20, y + h * 0.15, w - 40, h * 0.5
    k = appear(t, 0.0, 0.4)
    c.line([(left, top + ch), (left + cw, top + ch)], th.muted, 3, k * 0.6)
    c.line([(left, top), (left, top + ch)], th.muted, 3, k * 0.6)
    values = p.values or _series(p.direction)
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pts = [(left + cw * i / (len(values) - 1), top + ch - ch * ((v - lo) / span) * 0.9 - ch * 0.05)
           for i, v in enumerate(values)]
    progress = clamp((t - 0.3) / 1.6)
    shown = max(2, int(len(pts) * progress))
    color = th.negative if p.direction in ("down", "volatile_down") else th.positive
    c.line(pts[:shown], color, 6, k)
    if progress > 0:
        c.circle(*pts[shown - 1], 10, fill=color, alpha=k)
    if p.values:  # real values from the script: label first and last exactly as given
        for idx in (0, len(values) - 1):
            label = f"{values[idx]:g}"
            c.text(pts[idx][0], pts[idx][1] - 36, label, th.font("bold"), 34, th.text, alpha=appear(t, 1.8))
    if p.start_label:
        c.text(left, top + ch + 40, p.start_label, th.font("medium"), 32, th.muted, anchor="lm", alpha=k)
    if p.end_label:
        c.text(left + cw, top + ch + 40, p.end_label, th.font("medium"), 32, th.muted, anchor="rm", alpha=k)
    if p.caption:
        _block(c, ctx, p.caption, "bold", 50, w, 200, cx, top + ch + 100, th.text, appear(t, 1.2))


def short_vs_long(c: Canvas, t: float, p: ShortVsLong, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    for i, (label, text, kind) in enumerate(((p.short_label, p.short_text, "short"),
                                            (p.long_label, p.long_text, "long"))):
        k, dy = _rise(t, ctx.reveal(i, 1.5))
        top = y + h * 0.04 + i * h * 0.48 + dy
        color = th.negative if kind == "short" else th.positive
        c.text(x, top + 30, label, th.font("bold"), 50, color, anchor="lm", alpha=k)
        chart_top, chart_h = top + 80, h * 0.2
        n = 50
        pts = []
        for j in range(n):
            u = j / (n - 1)
            if kind == "short":
                v = 0.5 + 0.38 * math.sin(u * 19) * math.cos(u * 7)
            else:
                v = 0.15 + 0.7 * u + 0.05 * math.sin(u * 9)
            pts.append((x + w * u, chart_top + chart_h * (1 - v)))
        shown = max(2, int(n * clamp((t - ctx.reveal(i, 1.5) - 0.2) / 1.2)))
        c.line(pts[:shown], color, 5, k)
        if text:
            _block(c, ctx, text, "regular", 36, w, 110, x, chart_top + chart_h + 24, th.text, k, align="left",
                   max_lines=2)


def timeline(c: Canvas, t: float, p: Timeline, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    n = len(p.items)
    rail_x = x + 40
    step = min(h / n, 300)
    first = _top_for(ctx, (n - 1) * step + 120) + 30
    grow = appear(t, 0.0, 1.0)
    c.line([(rail_x, first), (rail_x, first + (n - 1) * step * grow)], th.muted, 4, 0.8)
    for i, item in enumerate(p.items):
        k, dy = _rise(t, ctx.reveal(i, 1.0), 24)
        top = first + i * step
        if item.icon:
            disc = mix(th.background, th.accent, 0.22)
            c.circle(rail_x, top, 32, fill=disc, outline=th.accent, width=3, alpha=k)
            icons.draw(c, item.icon, rail_x, top, 38, th.accent, _draw_on(t, ctx.reveal(i, 1.0)), k, disc)
        else:
            c.circle(rail_x, top, 18, fill=th.accent, alpha=k)
        c.text(rail_x + 50, top, item.label, th.font("bold"), 54, th.accent, anchor="lm", alpha=k)
        if item.text:
            _block(c, ctx, item.text, "regular", 44, w - 110, step - 70, rail_x + 50, top + 44 + dy, th.text, k,
                   align="left", max_lines=2)


def bars(c: Canvas, t: float, p: Bars, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    n = len(p.items)
    real = all(item.value is not None for item in p.items)
    values = [item.value for item in p.items] if real else [0.35 + 0.6 * (i + 1) / n for i in range(n)]
    top_v = max(values) or 1.0
    base_y, max_h = y + h * 0.7, h * 0.55
    gap = 40
    bw = (w - gap * (n - 1)) / n
    for i, (item, value) in enumerate(zip(p.items, values)):
        k = appear(t, ctx.reveal(i, 0.5), 0.8)
        bh = max_h * value / top_v * k
        left = x + i * (bw + gap)
        color = th.accent if i == values.index(max(values)) else th.positive
        c.rect(left, base_y - bh, bw, bh, r=12, fill=color, alpha=min(1, k * 2))
        c.text(left + bw / 2, base_y + 44, item.label, th.font("medium"), 34, th.text, alpha=min(1, k * 2))
        if real and k > 0.6:
            c.text(left + bw / 2, base_y - bh - 34, f"{item.value:g}", th.font("bold"), 38, th.text,
                   alpha=appear(t, ctx.reveal(i, 0.5) + 0.6))
    if not real:  # data red line: no numbers from the script, so say this is a schematic
        c.text(x + w, y + 20, "示意图" if ctx.lang == "zh" else "Illustrative", th.font("medium"), 30, th.muted,
               anchor="rm", alpha=appear(t, 0.2))
    if p.caption:
        _block(c, ctx, p.caption, "bold", 48, w, 160, cx, base_y + 110, th.text, appear(t, 1.0))


def _counting(value: str, progress: float) -> str:
    """`value` with its number counted up to `progress` (0..1), same format; text without a number is unchanged."""
    m = re.match(r"^(\D*?)(\d[\d,]*(?:\.\d+)?)(.*)$", value, re.S)
    if not m or progress >= 1:
        return value
    digits = m.group(2)
    decimals = len(digits.split(".")[1]) if "." in digits else 0
    current = float(digits.replace(",", "")) * progress
    shown = f"{current:,.{decimals}f}" if "," in digits else f"{current:.{decimals}f}"
    return m.group(1) + shown + m.group(3)


def big_number(c: Canvas, t: float, p: BigNumber, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    k = appear(t, 0.05, 0.6)
    font = th.font("black")
    # sized for the final value, then counted up to it (the settled frame shows exactly the script's value)
    fitted = c.fit(p.value, font, w, h * 0.4, 220 * ctx.scale, min_size=90 * ctx.scale, max_lines=1)
    top = cy - h * 0.25
    shown = _counting(p.value, ease_out(clamp((t - 0.1) / 1.1)))
    c.text(cx, top + fitted.line_height / 2, shown, font, fitted.size * (0.9 + 0.1 * k), th.accent, alpha=k)
    if p.caption:
        _block(c, ctx, p.caption, "medium", 46, w * 0.9, 200, cx, top + fitted.height + 40, th.text, appear(t, 0.6))


def quote(c: Canvas, t: float, p: Quote, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    k = appear(t, 0.0, 0.4)
    font = th.font("bold")
    fitted = c.fit(p.text, font, w - 60, h * 0.6, 68, min_size=40, max_lines=5)
    top = _top_for(ctx, fitted.height + 140)
    c.text(x + 20, top + 20, "“", th.font("black"), 200, th.accent, anchor="lm", alpha=k * 0.9, record=False)
    box = c.text_block_kinetic(fitted, font, x + 40, top + 110, th.text, t, 0.25, align="left", step=0.02,
                               dur=0.3, rise=0.2)
    if p.attribution:
        c.text(x + 40, box.bottom + 50, "— " + p.attribution, th.font("medium"), 36, th.muted, anchor="lm",
               alpha=appear(t, 0.8))


def checklist(c: Canvas, t: float, p: Checklist, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    step = min((h - 200) / len(p.items), 190)
    top = _top_for(ctx, len(p.items) * step + (170 if p.title else 0))
    if p.title:
        box = _block(c, ctx, p.title, "black", 64, w, 150, x, top, th.text, appear(t, 0.0), align="left", max_lines=2)
        top = box.bottom + 60
    for i, item in enumerate(p.items):
        k, dy = _rise(t, ctx.reveal(i, 0.9), 24)
        row = top + i * step + dy
        if p.mode == "ticks":
            # an empty box, then a hand-drawn tick as the item is said
            c.rect(x + 6, row + 6, 68, 68, r=14, outline=mix(th.background, th.muted, 0.8), width=4, alpha=k)
            drawn = ease_out((t - ctx.reveal(i, 0.9) - 0.15) / 0.45)
            if drawn > 0:
                pts = [(x + 40 + u * 66, row + 40 + v * 66) for u, v in icons.partial(TICK, drawn)]
                c.line(pts, th.positive, 9, k)
                c.circle(*pts[0], 4.5, fill=th.positive, alpha=k)
                c.circle(*pts[-1], 4.5, fill=th.positive, alpha=k)
            _block_mid(c, ctx, item, "medium", 52, w - 120, step - 20, x + 110, row + 40, th.text, k)
            continue
        disc = mix(th.background, th.positive, 0.25)
        c.circle(x + 40, row + 40, 38, fill=disc, alpha=k)
        if _icon_at(p.icons, i):
            icons.draw(c, p.icons[i], x + 40, row + 40, 44, th.positive, _draw_on(t, ctx.reveal(i, 0.9)), k, disc)
        else:
            c.text(x + 40, row + 40, str(i + 1), th.font("bold"), 42, th.positive, alpha=k, record=False)
        _block_mid(c, ctx, item, "medium", 52, w - 120, step - 20, x + 110, row + 40, th.text, k)


def strike(c: Canvas, t: float, p: Strike, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    k = appear(t, 0.0, 0.5)
    old = _block(c, ctx, p.old, "bold", 64, w, h * 0.3, cx, _top_for(ctx, h * 0.5), th.muted, k, max_lines=2)
    cut = clamp((t - ctx.reveal(0, 1.0)) / 0.5)
    if cut > 0:
        for i in range(len(c.records[-1].text.split(" / "))):
            ly = old.y + (i + 0.55) * old.h / max(1, len(c.records[-1].text.split(" / ")))
            c.line([(old.x - 10, ly), (old.x - 10 + (old.w + 20) * cut, ly)], th.negative, 7)
    k2, dy = _rise(t, ctx.reveal(1, 1.6))
    _block(c, ctx, p.new, "black", 76, w, h * 0.35, cx, old.bottom + 120 + dy, th.accent, k2, max_lines=3)


def three_things(c: Canvas, t: float, p: ThreeThings, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    title = _block(c, ctx, p.title, "black", 64, w, 170, cx, y + 10, th.text, appear(t, 0.0), max_lines=2)
    top = title.bottom + 60
    step = (y + h - top) / 3
    current = max([i for i in range(3) if t >= ctx.reveal(i, 1.5)] or [-1])
    for i, item in enumerate(p.items):
        k, dy = _rise(t, ctx.reveal(i, 1.5), 30)
        row = top + i * step + dy
        active = i == current
        fill = mix(th.surface, th.accent, 0.12) if active else th.surface
        c.rect(x, row, w, step - 30, r=24, fill=fill, outline=th.accent if active else None, width=3, alpha=k)
        c.text(x + 40, row + (step - 30) / 2, _ordinal(i, ctx.lang), th.font("black"), 48, th.accent, anchor="lm",
               alpha=k, under=fill)
        label_w = c.measure(_ordinal(i, ctx.lang), th.font("black"), 48) + 80
        icon_w = 0
        if _icon_at(p.icons, i):
            icon_w = 110
            icons.draw(c, p.icons[i], x + w - 74, row + (step - 30) / 2, 76, th.accent if active else th.text,
                       _draw_on(t, ctx.reveal(i, 1.5) + 0.2), k, fill)
        _block_mid(c, ctx, item, "bold", 54, w - label_w - 40 - icon_w, step - 60, x + label_w, row + (step - 30) / 2,
                   th.text, k, under=fill)


def question_stack(c: Canvas, t: float, p: QuestionStack, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    n = len(p.questions)
    step = min(h / n, 230)
    first = _top_for(ctx, n * step, 0.5)
    current = max([i for i in range(n) if t >= ctx.reveal(i, 1.2)] or [-1])
    for i, q in enumerate(p.questions):
        t0 = ctx.reveal(i, 1.2)
        k = appear(t, t0, 0.35)
        pop = 1 + 0.06 * math.sin(clamp((t - t0) / 0.35) * math.pi)
        row = first + i * step
        active = i == current
        border = th.accent if active else mix(th.surface, th.muted, 0.4)
        indent = 0 if i % 2 == 0 else 60
        bw = (w - 60) * pop
        c.rect(x + indent, row, bw, step - 34, r=26, fill=th.surface, outline=border, width=3, alpha=k)
        c.text(x + indent + 50, row + (step - 34) / 2, "?", th.font("black"), 56, th.accent, alpha=k, under=th.surface)
        _block_mid(c, ctx, q, "bold" if active else "medium", 48, bw - 130, step - 60, x + indent + 100,
                   row + (step - 34) / 2, th.text if active else th.muted, k, under=th.surface)


def choice_consequence(c: Canvas, t: float, p: ChoiceConsequence, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    n = len(p.choices)
    chip_h = 120
    first = _top_for(ctx, n * (chip_h + 26) + 420)
    for i, choice in enumerate(p.choices):
        k, dy = _rise(t, ctx.reveal(i, 1.0), 20)
        top = first + i * (chip_h + 26) + dy
        c.rect(x, top, w, chip_h, r=60, fill=th.surface, outline=mix(th.surface, th.text, 0.35), width=2, alpha=k)
        _block_mid(c, ctx, choice, "medium", 46, w - 100, chip_h - 20, cx, top + chip_h / 2, th.text, k,
                   align="center", max_lines=1, under=th.surface)
    arrow_top = first + n * (chip_h + 26) + 10
    k = appear(t, ctx.reveal(n, 1.2), 0.5)
    c.arrow((cx, arrow_top), (cx, arrow_top + 110 * k + 1), th.accent, 6, 26, k)
    k2, dy = _rise(t, ctx.reveal(n, 1.2) + 0.3, 24)
    box = _block(c, ctx, p.consequence, "black", 64, w, 260, cx, arrow_top + 150 + dy, th.accent, k2, max_lines=3)
    if p.note:
        _block(c, ctx, p.note, "medium", 38, w, 140, cx, box.bottom + 30, th.muted, appear(t, ctx.reveal(n, 1.2) + 0.8))


def punchline(c: Canvas, t: float, p: Punchline, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    font = th.font("black")
    fitted = c.fit(p.text, font, w * 0.95, h * 0.6, 100 * ctx.scale, min_size=50 * ctx.scale, max_lines=4)
    top = cy - fitted.height / 2 - h * 0.06
    landed = 0.1 + 0.045 * len(p.text) + 0.25  # every glyph has popped in
    span = None
    if p.highlight:
        for li, line in enumerate(fitted.lines):
            idx = line.find(p.highlight)
            if idx >= 0:
                left = cx - fitted.widths[li] / 2 + c.measure(line[:idx], font, fitted.size)
                span = (li, left, c.measure(p.highlight, font, fitted.size))
                break
    marker = mix(th.background, th.accent, 0.28)
    if span:
        # highlighter pen: a gold band sweeps under the phrase once the sentence has landed
        li, left, span_w = span
        sweep = appear(t, landed, 0.5)
        band_top = top + li * fitted.line_height + fitted.line_height * 0.16
        c.rect(left - 10, band_top, (span_w + 20) * sweep, fitted.line_height * 0.7, r=12, fill=marker,
               alpha=min(1.0, sweep * 3))
    c.text_block_kinetic(fitted, font, cx, top, th.text, t, 0.1)
    if span:
        c.text(left, top + li * fitted.line_height + fitted.line_height / 2, p.highlight, font, fitted.size,
               th.accent, anchor="lm", alpha=appear(t, landed + 0.3, 0.4), under=marker, record=False)


def balance(c: Canvas, t: float, p: Balance, ctx: Ctx):
    """A beam on a post; each pan drops in with its label, then the beam tips (with a damped swing)."""
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    # drawn extent: the raised beam end ~50 px above the pivot down to the base (+post), then the caption
    group = 520 + (130 if p.caption else 0)
    pivot_y = _top_for(ctx, group, 0.5) + 50
    half = w * 0.33
    post = 470
    k0 = appear(t, 0.0, 0.5)
    # post and base
    c.line([(cx, pivot_y), (cx, pivot_y + post)], mix(th.background, th.muted, 0.9), 10, k0)
    c.rect(cx - 130, pivot_y + post - 4, 260, 20, r=10, fill=mix(th.background, th.muted, 0.9), alpha=k0)
    # tilt once both pans are on (screen y grows downwards: a positive angle tips the left end down)
    target = {"left": 1, "right": -1, "even": 0}[p.heavier] * math.radians(9)
    u = max(0.0, t - (ctx.reveal(1, 1.0) + 0.5))
    angle = target * (1 - math.exp(-3.2 * u) * math.cos(7.5 * u)) if u > 0 else 0.0
    ends = [(cx - half * math.cos(angle), pivot_y + half * math.sin(angle)),
            (cx + half * math.cos(angle), pivot_y - half * math.sin(angle))]
    c.line(ends, th.text, 9, k0)
    c.circle(cx, pivot_y, 16, fill=th.accent, alpha=k0)
    for i, (pan, (ex, ey)) in enumerate(zip((p.left, p.right), ends)):
        k, dy = _rise(t, ctx.reveal(i, 1.0), -50)  # drops in from above
        plate_y = ey + 210 + dy
        rope = mix(th.background, th.muted, 0.7)
        c.line([(ex, ey), (ex - 125, plate_y)], rope, 3, k)
        c.line([(ex, ey), (ex + 125, plate_y)], rope, 3, k)
        heavy = (p.heavier == "left" and i == 0) or (p.heavier == "right" and i == 1)
        colour = th.accent if heavy else th.positive
        c.rect(ex - 140, plate_y - 5, 280, 16, r=8, fill=colour, alpha=k)
        if pan.icon:
            icons.draw(c, pan.icon, ex, plate_y - 78, 104, colour, _draw_on(t, ctx.reveal(i, 1.0) + 0.1), k)
        _block(c, ctx, pan.label, "bold", 50, 260, 130, ex, plate_y + 34, th.text, k, max_lines=2, min_size=28)
    if p.caption:
        _block(c, ctx, p.caption, "bold", 54, w, 150, cx, pivot_y + post + 50, th.text,
               appear(t, ctx.reveal(1, 1.0) + 1.0))


def cycle(c: Canvas, t: float, p: Cycle, ctx: Ctx):
    """Steps on a ring; arrows draw from step to step and close the loop, then a light runs round it."""
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    n = len(p.steps)
    node_r, label_h = 62, 110
    radius = min(230.0, (h - 2 * (node_r + 20 + label_h)) / 2, w / 2 - 190)
    ccy = y + h / 2
    angles = [-math.pi / 2 + 2 * math.pi * i / n for i in range(n)]
    pos = [(cx + radius * math.cos(a), ccy + radius * math.sin(a)) for a in angles]
    gap = (node_r + 14) / radius  # arrows stop short of the nodes
    ring = mix(th.background, th.muted, 0.35)
    k0 = appear(t, 0.0, 0.5)
    c.circle(cx, ccy, radius, outline=ring, width=3, alpha=k0)
    last = ctx.reveal(n - 1, 1.2)
    for i in range(n):
        t0 = ctx.reveal(i, 1.2) + 0.3 if i < n - 1 else last + 0.6  # the closing arrow comes last
        prog = ease_out((t - t0) / 0.6)
        a0, a1 = angles[i] + gap, angles[i] + 2 * math.pi / n - gap
        if prog > 0:
            steps = 24
            arc = [(cx + radius * math.cos(a0 + (a1 - a0) * j / steps), ccy + radius * math.sin(a0 + (a1 - a0) * j / steps))
                   for j in range(int(steps * prog) + 1)]
            if len(arc) > 1:
                c.line(arc[:-1], th.accent, 6)
                c.arrow(arc[-2], arc[-1], th.accent, 6, 22)
    if t > last + 1.2:  # a light circling the closed loop
        a = angles[0] + (t - last - 1.2) * 1.6
        c.circle(cx + radius * math.cos(a), ccy + radius * math.sin(a), 11, fill=th.accent, alpha=0.9)
    current = max([i for i in range(n) if t >= ctx.reveal(i, 1.2)] or [-1])
    for i, (step, (px, py)) in enumerate(zip(p.steps, pos)):
        k = appear(t, ctx.reveal(i, 1.2), 0.4)
        active = i == current
        fill = mix(th.surface, th.accent, 0.16) if active else th.surface
        c.circle(px, py, node_r * (0.7 + 0.3 * k), fill=fill, outline=th.accent if active else ring, width=4, alpha=k)
        if _icon_at(p.icons, i):
            icons.draw(c, p.icons[i], px, py, 58, th.accent if active else th.text,
                       _draw_on(t, ctx.reveal(i, 1.2) + 0.1, 0.6), k, fill)
        else:
            c.text(px, py, str(i + 1), th.font("black"), 52, th.accent, alpha=k, under=fill, record=False)
        top_node = abs(py - (ccy - radius)) < 1
        font = th.font("bold")
        fitted = c.fit(step, font, 250, label_h, 44 * ctx.scale, min_size=28 * ctx.scale, max_lines=2)
        label_y = py - node_r - 16 - fitted.height if top_node else py + node_r + 16
        # a backing chip: side labels sit where the ring and its arrows pass
        c.rect(px - fitted.width / 2 - 14, label_y - 6, fitted.width + 28, fitted.height + 12, r=14,
               fill=th.background, alpha=k)
        c.text_block(fitted, font, px, label_y, th.text if active else th.muted, "center", k)
    if p.center:
        _block(c, ctx, p.center, "black", 52, 2 * (radius - node_r) - 40, 140, cx, ccy - 40, th.accent,
               appear(t, last + 1.0), max_lines=2, min_size=30)


def dialogue(c: Canvas, t: float, p: Dialogue, ctx: Ctx):
    """Chat bubbles popping in turn: 'other' on the left, 'me' (narrator) on the right in the accent colour."""
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    font = th.font("bold")
    avatar, pad, gap = 46, 34, 44
    bubble_w = w - 2 * avatar - 40
    fits = [c.fit(line.text, font, bubble_w - 2 * pad, 300, 52 * ctx.scale, min_size=28 * ctx.scale, max_lines=3)
            for line in p.lines]
    heights = [f.height + 2 * pad for f in fits]
    top = _top_for(ctx, sum(heights) + gap * (len(fits) - 1), 0.5)
    for i, (line, fitted, bh) in enumerate(zip(p.lines, fits, heights)):
        k, dy = _rise(t, ctx.reveal(i, 1.0), 30)
        me = line.who == "me"
        bw = fitted.width + 2 * pad
        fill = mix(th.background, th.accent, 0.92) if me else th.surface
        text_colour = th.background if me else th.text
        row = top + dy
        av_x = x + w - avatar if me else x + avatar
        left = av_x - avatar - 20 - bw if me else av_x + avatar + 20
        c.circle(av_x, row + bh - avatar, avatar, fill=mix(th.background, th.accent if me else th.positive, 0.25),
                 alpha=k)
        icons.draw(c, "mood-smile" if me else "user", av_x, row + bh - avatar, 52, th.accent if me else th.positive,
                   1.0, k, mix(th.background, th.accent if me else th.positive, 0.25))
        c.rect(left, row, bw, bh, r=30, fill=fill, alpha=k)
        tail_x = left + bw if me else left  # a small tail pointing at the speaker
        c.polygon([(tail_x - 20 if me else tail_x + 20, row + bh - 34), (tail_x + 14 if me else tail_x - 14, row + bh - 6),
                   (tail_x - 34 if me else tail_x + 34, row + bh - 10)], fill, alpha=k)
        c.text_block(fitted, font, left + pad, row + pad, text_colour, "left", k, under=fill)
        top += bh + gap


REGISTRY = {
    "hook": (hook, Hook), "keyword": (keyword, Keyword), "compare_cards": (compare_cards, CompareCards),
    "trend": (trend, Trend), "short_vs_long": (short_vs_long, ShortVsLong), "timeline": (timeline, Timeline),
    "bars": (bars, Bars), "big_number": (big_number, BigNumber), "quote": (quote, Quote),
    "checklist": (checklist, Checklist), "strike": (strike, Strike), "three_things": (three_things, ThreeThings),
    "question_stack": (question_stack, QuestionStack), "choice_consequence": (choice_consequence, ChoiceConsequence),
    "punchline": (punchline, Punchline), "balance": (balance, Balance), "cycle": (cycle, Cycle),
    "dialogue": (dialogue, Dialogue),
}





# ---------------------------------------------------------------- internal (not offered to the planner)
class EndCard(BaseModel):
    disclaimer: str = ""
    account: str = ""


def end_card(c: Canvas, t: float, p: EndCard, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    if p.account:
        c.text(cx, cy - 60, p.account, th.font("bold"), 44, th.text, alpha=appear(t, 0.1, 0.5))
    if p.disclaimer:
        k = appear(t, 0.15, 0.5)
        c.rect(cx - 40, cy + 10, 80, 4, r=2, fill=th.muted, alpha=k)
        _block(c, ctx, p.disclaimer, "medium", 46, w * 0.9, 200, cx, cy + 40, th.text, k, max_lines=2)


INTERNAL = {"end_card": (end_card, EndCard)}


def draw(c: Canvas, name: str, t: float, params: dict, ctx: Ctx) -> None:
    fn, model = REGISTRY.get(name) or INTERNAL[name]
    fn(c, t, model.model_validate(params), ctx)
