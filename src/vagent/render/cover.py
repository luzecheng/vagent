"""Covers: cover_zh.png (3:4, 1080x1440, WeChat Channels) and cover_en.png (9:16, 1080x1920, X)."""
from __future__ import annotations

from pathlib import Path

from .canvas import Canvas, mix
from .theme import Box, Theme


def render_cover(title: str, subtitle: str, theme: Theme, size: tuple[int, int], out: Path, account: str = "",
                 area: Box | None = None) -> list:
    """`area`: where text may go. Covers for upload use a centred box (feeds crop them differently);
    the cover frame inside a video uses that video's safe content area (clear of platform buttons)."""
    width, height = size
    c = Canvas(width, height, theme.background)
    # large faint accent shape for presence in the feed
    c.circle(width * 0.92, height * 0.18, width * 0.42, fill=mix(theme.background, theme.accent, 0.10))
    c.circle(width * 0.92, height * 0.18, width * 0.25, fill=mix(theme.background, theme.accent, 0.16))
    # text stays in a centred safe box (feeds crop covers differently)
    safe = area or Box(width * 0.09, height * 0.2, width * 0.82, height * 0.6)
    title_font = theme.font("black")
    base = 240 if theme.lang == "zh" else 170
    # prefer two lines at up to 20% smaller over three lines at full size
    fitted = c.fit(title, title_font, safe.w, safe.h * 0.66, base, min_size=base * 0.8, max_lines=2)
    if len(fitted.lines) > 2 or fitted.width > safe.w:
        fitted = c.fit(title, title_font, safe.w, safe.h * 0.66, base, min_size=72, max_lines=3)
    sub_fitted = c.fit(subtitle, theme.font("bold"), safe.w, safe.h * 0.22, 64 if theme.lang == "zh" else 56,
                       min_size=36, max_lines=2) if subtitle else None
    group = fitted.height + (sub_fitted.height + 60 if sub_fitted else 0) + 80
    top = safe.y + (safe.h - group) / 2
    c.rect(safe.x, top, 180, 16, r=8, fill=theme.accent)
    box = c.text_block(fitted, title_font, safe.x, top + 64, theme.text, "left")
    if sub_fitted:
        c.text_block(sub_fitted, theme.font("bold"), safe.x, box.bottom + 48, theme.accent, "left")
    if account:
        c.text(safe.x, safe.bottom - 30 if area else height * 0.9, account, theme.font("bold"), 40, theme.muted,
               anchor="lm")
    c.finish().save(out)
    return c.records
