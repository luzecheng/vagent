"""Semantic subtitle segmentation and timing.

Each sentence is broken into lines by a small dynamic program:
  * a line never exceeds max_chars (display width);
  * zh: breaks fall only between jieba words, never inside one;
  * en: never break right after a function word (a/the/of/in/to/...);
  * breaks at punctuation are free, other breaks cost a little;
  * lines are kept even (no full line followed by a one-word stub);
screens are chosen before lines: a long sentence is cut into the fewest,
evenly sized screens (at most two lines each), preferring cuts at punctuation,
and each screen is then broken into lines.  Screen times come from the
narration's unit timings.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

HAN = re.compile(r"[一-鿿]")
UNIT = re.compile(r"[一-鿿]|[A-Za-z0-9][A-Za-z0-9'’\-.%$]*")
ZH_DROP = "，。；、：,;:"
ZH_KEEP = "？！?!…"
QUOTES = "“”‘’\"「」『』"
EN_FUNCTION = {
    "a", "an", "the", "of", "in", "to", "for", "and", "or", "but", "with", "at", "on", "by", "from", "as",
    "into", "onto", "than", "that", "your", "my", "our", "their", "his", "her", "its", "this", "these", "those",
    "is", "are", "was", "were", "be", "not", "no", "so", "if", "who", "what", "you're", "it's", "we're",
}
ZH_NO_LINE_START = set("的了着过吗呢吧啊呀嘛么地得")
ZH_NO_LINE_END = {"把", "被", "在", "对", "和", "与", "给", "让", "向", "从", "跟", "为", "将", "就是", "是", "比", "当"}
INF = float("inf")


@dataclass
class Token:
    text: str
    units: int            # how many timing units this token covers
    soft_end: bool        # punctuation at its end: a natural break point


@dataclass
class Screen:
    lines: list[str]
    start: float
    end: float
    sentence_id: int


def tokens(text: str, lang: str) -> list[Token]:
    text = "".join(ch for ch in text if ch not in QUOTES)
    out: list[Token] = []
    if lang == "zh":
        import jieba

        for word in jieba.lcut(text):
            if not word.strip():
                continue
            if all(ch in ZH_DROP + ZH_KEEP for ch in word) and out:
                out[-1] = Token(out[-1].text + word, out[-1].units, True)
                continue
            out.append(Token(word, len(UNIT.findall(word)), False))
    else:
        for word in text.split():
            out.append(Token(word, len(UNIT.findall(word)), bool(re.search(r"[,.;:!?—]$", word))))
    return out


def display(line_tokens: list[Token], lang: str) -> str:
    if lang == "zh":
        text = "".join(t.text for t in line_tokens)
        text = re.sub(f"[{ZH_DROP}]+", " ", text).strip()
        return re.sub(r"\s+", " ", text)
    text = " ".join(t.text for t in line_tokens)
    return re.sub(r"[.;:]$", "", text)


def width(text: str, lang: str) -> float:
    if lang == "zh":
        return len(HAN.findall(text)) + 0.55 * len(re.findall(r"[A-Za-z0-9 ]", text)) + 0.5 * text.count("？")
    return float(len(text))


def break_lines(toks: list[Token], lang: str, max_chars: int) -> list[list[Token]]:
    n = len(toks)
    best = [INF] * (n + 1)
    back = [0] * (n + 1)
    best[0] = 0.0
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            line = display(toks[i:j], lang)
            w = width(line, lang)
            if w > max_chars and j - i > 1:
                break
            last = toks[j - 1]
            if j == n or last.soft_end:
                penalty = 0.0
            elif lang == "en" and last.text.lower().strip(",.") in EN_FUNCTION:
                penalty = INF
            elif lang == "zh" and (toks[j].text[0] in ZH_NO_LINE_START or last.text in ZH_NO_LINE_END):
                penalty = INF
            else:
                penalty = 30.0 if lang == "zh" else 20.0
            slack = (max_chars - w) ** 2 * 0.05  # the last line too: two even lines beat a full one plus a stub
            cost = best[i] + slack + penalty + 8.0  # each extra line costs a bit
            if cost < best[j]:
                best[j], back[j] = cost, i
    lines, j = [], n
    while j > 0:
        lines.append(toks[back[j]:j])
        j = back[j]
    return lines[::-1]


def _boundary_penalty(toks: list[Token], j: int, lang: str) -> float:
    """Cost of ending a screen after toks[j-1]."""
    last = toks[j - 1]
    if j == len(toks) or last.soft_end:
        return 0.0
    if lang == "en" and last.text.lower().strip(",.") in EN_FUNCTION:
        return 60.0
    if lang == "zh" and (toks[j].text[0] in ZH_NO_LINE_START or last.text in ZH_NO_LINE_END):
        return 60.0
    return 15.0


def screens_for_sentence(sentence: dict, lang: str, max_chars: int, max_lines: int = 2) -> list[Screen]:
    """Split a sentence into screens first (balanced, at natural pauses), then each screen into lines.

    Filling lines first and grouping them afterwards leaves fragments such as a
    lone "to win" screen when a sentence needs one line more than a screen holds.
    """
    toks = tokens(sentence["text"], lang)
    n = len(toks)
    total = width(display(toks, lang), lang)
    count = max(1, -(-total // (max_chars * max_lines)))   # fewest screens that could hold it
    target = total / count
    best = [INF] * (n + 1)
    back = [0] * (n + 1)
    lines_for: dict[tuple[int, int], list[list[Token]]] = {}
    best[0] = 0.0
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            lines = break_lines(toks[i:j], lang, max_chars)
            if len(lines) > max_lines and j - i > 1:
                break
            lines_for[(i, j)] = lines
            w = width(display(toks[i:j], lang), lang)
            balance = ((w - target) / max_chars) ** 2 * 8
            cost = best[i] + _boundary_penalty(toks, j, lang) + balance + 10.0  # each extra screen costs a bit
            if cost < best[j]:
                best[j], back[j] = cost, i
    groups, j = [], n
    while j > 0:
        groups.append((back[j], j))
        j = back[j]
    groups.reverse()
    units = sentence["units"]
    screens: list[Screen] = []
    cursor = 0
    for i, j in groups:
        used = sum(t.units for t in toks[i:j])
        first = units[min(cursor, len(units) - 1)] if units else None
        last = units[min(cursor + used, len(units)) - 1] if units else None
        cursor += used
        start = first["start"] if first else sentence["start"]
        end = last["end"] if last else sentence["end"]
        screens.append(Screen([display(line, lang) for line in lines_for[(i, j)]], start, end, sentence["id"]))
    return screens


def build(timeline: dict, lang: str, config: dict) -> list[Screen]:
    rules = config["subtitles"][lang]
    screens: list[Screen] = []
    for sentence in timeline["sentences"]:
        screens.extend(screens_for_sentence(sentence, lang, rules["max_chars_per_line"], rules["max_lines"]))
    # hold each screen briefly after its last word, but never into the next one
    for current, following in zip(screens, screens[1:]):
        current.end = round(min(current.end + 0.25, following.start - 0.04), 3)
    if screens:
        screens[-1].end = round(screens[-1].end + 0.4, 3)
    return screens


def srt(screens: list[Screen]) -> str:
    def stamp(x: float) -> str:
        ms = int(round(max(0.0, x) * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"

    blocks = [f"{i}\n{stamp(s.start)} --> {stamp(s.end)}\n" + "\n".join(s.lines) + "\n"
              for i, s in enumerate(screens, 1)]
    return "\n".join(blocks)
