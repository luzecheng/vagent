"""Layout checks on exactly what was drawn: safe area, overflow, and glyph coverage."""
from __future__ import annotations

from functools import lru_cache

from ..render.theme import Box


@lru_cache(maxsize=16)
def _cmap(font_path: str) -> frozenset[int]:
    from fontTools.ttLib import TTFont

    font = TTFont(font_path, fontNumber=0, lazy=True)
    return frozenset(font.getBestCmap().keys())


def missing_glyphs(text: str, font_path: str) -> list[str]:
    """Characters the font cannot draw (they would render as tofu boxes)."""
    cmap = _cmap(font_path)
    return sorted({ch for ch in text if not ch.isspace() and ord(ch) not in cmap and ch != "/"})


def outside(records, area: Box, tolerance: float = 1.0) -> list[str]:
    """Text blocks whose box leaves `area` (records: (text, box_dict, font, size) or TextRecord)."""
    bad = []
    for record in records:
        text, box = (record.text, record.box) if hasattr(record, "box") else (record[0], Box(**record[1]))
        if not area.contains(box, tolerance):
            bad.append(text)
    return bad
