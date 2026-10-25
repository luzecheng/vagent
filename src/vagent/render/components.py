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
from typing import Literal

from pydantic import BaseModel, Field

from .canvas import Canvas, appear, clamp, ease_in_out, mix
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
class Hook(BaseModel):
    text: str = Field(description="The most striking line of the script, verbatim or lightly trimmed (<= 22 zh chars / 60 en chars)")
    sub: str = ""
    layout: Literal[0, 1] = 0


class Keyword(BaseModel):
    word: str = Field(description="1-6 zh chars / 1-3 en words")
    caption: str = ""
    layout: Literal[0, 1] = 0


class Card(BaseModel):
    title: str
    text: str = ""
    mark: Literal["check", "warn"] = "check"


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


class Strike(BaseModel):
    old: str
    new: str


class ThreeThings(BaseModel):
    title: str
    items: list[str] = Field(min_length=3, max_length=3)


class QuestionStack(BaseModel):
    questions: list[str] = Field(min_length=2, max_length=5)


class ChoiceConsequence(BaseModel):
    choices: list[str] = Field(min_length=1, max_length=3)
    consequence: str
    note: str = ""


class Punchline(BaseModel):
    text: str
    highlight: str = Field("", description="substring of text to colour in the accent colour")


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


def _ordinal(i: int, lang: str) -> str:
    return ["第一", "第二", "第三", "第四", "第五"][i] if lang == "zh" else ["One", "Two", "Three", "Four", "Five"][i]


# ---------------------------------------------------------------- components
def hook(c: Canvas, t: float, p: Hook, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    k, dy = _rise(t, 0.1)
    bar = appear(t, 0.0, 0.5)
    font = th.font("black")
    fitted = c.fit(p.text, font, w * 0.92, h * 0.5, 100 if ctx.lang == "zh" else 88, min_size=48, max_lines=3)
    group = fitted.height + (110 if p.sub else 0) + 40
    top = _top_for(ctx, group)
    if p.layout == 0:
        c.rect(cx - 60 * bar, top - 40, 120 * bar, 8, r=4, fill=th.accent)
        box = c.text_block(fitted, font, cx, top + dy, th.text, "center", k)
        if p.sub:
            _block(c, ctx, p.sub, "medium", 40, w * 0.85, 120, cx, box.bottom + 40, th.muted, appear(t, 0.7))
    else:
        fitted = c.fit(p.text, font, w * 0.86, h * 0.5, 96 if ctx.lang == "zh" else 84, min_size=48, max_lines=3)
        c.rect(x + 10, top, 10, fitted.height * bar, r=5, fill=th.accent)
        box = c.text_block(fitted, font, x + 50, top + dy, th.text, "left", k)
        if p.sub:
            _block(c, ctx, p.sub, "medium", 38, w * 0.8, 120, x + 50, box.bottom + 36, th.muted, appear(t, 0.7),
                   align="left")


def keyword(c: Canvas, t: float, p: Keyword, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    k = appear(t, 0.1, 0.5)
    scale = 0.85 + 0.15 * k
    box = _block(c, ctx, p.word, "black", 140 * scale, w * 0.9, h * 0.35, cx, cy - h * 0.16, th.accent, k,
                 max_lines=2, min_size=60)
    sweep = appear(t, 0.45, 0.6)
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
        c.circle(x + 80, top + 80, 40, fill=mix(th.surface, color, 0.25), alpha=k, under=th.surface)
        if card.mark == "check":
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


def big_number(c: Canvas, t: float, p: BigNumber, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    k = appear(t, 0.05, 0.6)
    size = 220 * (0.9 + 0.1 * k)
    box = _block(c, ctx, p.value, "black", size, w, h * 0.4, cx, cy - h * 0.25, th.accent, k, max_lines=1,
                 min_size=90)
    if p.caption:
        _block(c, ctx, p.caption, "medium", 46, w * 0.9, 200, cx, box.bottom + 40, th.text, appear(t, 0.6))


def quote(c: Canvas, t: float, p: Quote, ctx: Ctx):
    x, y, w, h, cx, cy = _area(ctx)
    th = ctx.theme
    k, dy = _rise(t, 0.1, 30)
    font = th.font("bold")
    fitted = c.fit(p.text, font, w - 60, h * 0.6, 68, min_size=40, max_lines=5)
    top = _top_for(ctx, fitted.height + 140)
    c.text(x + 20, top + 20, "“", th.font("black"), 200, th.accent, anchor="lm", alpha=k * 0.9, record=False)
    box = c.text_block(fitted, font, x + 40, top + 110 + dy, th.text, "left", k)
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
        c.circle(x + 40, row + 40, 38, fill=mix(th.background, th.positive, 0.25), alpha=k)
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
        _block_mid(c, ctx, item, "bold", 54, w - label_w - 40, step - 60, x + label_w, row + (step - 30) / 2,
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
    k = appear(t, 0.1, 0.6)
    scale = 0.92 + 0.08 * ease_in_out(clamp(t / 0.8))
    font = th.font("black")
    fitted = c.fit(p.text, font, w * 0.95, h * 0.6, 100 * scale, min_size=50, max_lines=4)
    top = cy - fitted.height / 2 - h * 0.06
    c.text_block(fitted, font, cx, top, th.text, "center", k)
    if p.highlight and p.highlight in p.text:
        # recolour the highlighted span: redraw it in the accent colour on its line
        for li, line in enumerate(fitted.lines):
            idx = line.find(p.highlight)
            if idx < 0:
                continue
            left = cx - fitted.widths[li] / 2 + c.measure(line[:idx], font, fitted.size)
            c.text(left, top + li * fitted.line_height + fitted.line_height / 2, p.highlight, font, fitted.size,
                   th.accent, anchor="lm", alpha=appear(t, 0.6, 0.5), record=False)
            span_w = c.measure(p.highlight, font, fitted.size)
            c.rect(left, top + (li + 1) * fitted.line_height - 6, span_w * appear(t, 0.8, 0.6), 8, r=4,
                   fill=th.accent, alpha=k)
            break


REGISTRY = {
    "hook": (hook, Hook), "keyword": (keyword, Keyword), "compare_cards": (compare_cards, CompareCards),
    "trend": (trend, Trend), "short_vs_long": (short_vs_long, ShortVsLong), "timeline": (timeline, Timeline),
    "bars": (bars, Bars), "big_number": (big_number, BigNumber), "quote": (quote, Quote),
    "checklist": (checklist, Checklist), "strike": (strike, Strike), "three_things": (three_things, ThreeThings),
    "question_stack": (question_stack, QuestionStack), "choice_consequence": (choice_consequence, ChoiceConsequence),
    "punchline": (punchline, Punchline),
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
