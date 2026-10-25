"""Small text helpers shared across stages."""
from __future__ import annotations

HALF_TO_FULL = {",": "，", "?": "？", "!": "！", ":": "：", ";": "；", ".": "。"}


def zh_punct(value):
    """Full-width punctuation after Chinese characters (LLM output sometimes uses ',' and '?')."""
    if isinstance(value, str):
        out = []
        for i, ch in enumerate(value):
            prev_han = i > 0 and "一" <= value[i - 1] <= "鿿"
            out.append(HALF_TO_FULL[ch] if ch in HALF_TO_FULL and prev_han else ch)
        return "".join(out)
    if isinstance(value, dict):
        return {k: zh_punct(v) for k, v in value.items()}
    if isinstance(value, list):
        return [zh_punct(v) for v in value]
    return value
