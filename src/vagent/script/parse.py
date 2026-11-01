"""Clean a raw script, split it into spoken sentences, and estimate duration."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re

import yaml

from ..config import PROJECT

HAN = re.compile(r"[一-鿿]")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-.%$]*")
END = "。！？；!?;"
CONTINUES = ("，", "、", ",", "——", "—", "--")   # a line ending in one of these runs on into the next line
QUOTES = {"“": "", "”": "", "‘": "", "’": "", '"': "", "「": "", "」": "", "『": "", "』": ""}
ZH_SYMBOLS = re.compile(r"\s*([+＋=＝])\s*")   # Chinese voices skip or garble these, so they are read as words
ZH_SYMBOL_WORDS = {"+": "加", "＋": "加", "=": "等于", "＝": "等于"}
ZH_ACRONYM = re.compile(r"(?<![A-Za-z])[A-Z]{2,5}(?![A-Za-z])")  # read as one word ("AI" -> "爱") unless spaced
ZH_YEAR = re.compile(r"(?<!\d)(\d{4})\s*年")  # a year is said digit by digit, not as a cardinal number
ZH_DIGITS = dict(zip("0123456789", "零一二三四五六七八九"))
ZH_DECIMAL = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?![\d.])")  # 3.2 is 三点二, not "三 二"; 1.2.3 is not a decimal
ZH_DASH = re.compile(r"\s*(?:——|—|--)\s*")   # a dash is a pause, not a syllable (a hyphen as in 2020-2021 stays)
# This machine's respellings for the Chinese voice ("phrase: what to say"), e.g. a comma where the voice groups
# characters wrongly. Personal (git-ignored); missing means no rules.
SPOKEN_FILE = PROJECT / "config/zh_spoken.yaml"
_spoken_cache: dict = {}


@dataclass
class Sentence:
    id: int
    text: str                 # display text (what subtitles show)
    paragraph: int            # 0-based paragraph index
    ends_paragraph: bool = False
    kind: str = "statement"   # statement | question | lead (ends with a colon)

    @property
    def pause_kind(self) -> str:
        if self.ends_paragraph:
            return "paragraph"
        return {"question": "question", "lead": "colon"}.get(self.kind, "sentence")


@dataclass
class Script:
    raw: str
    sentences: list[Sentence] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.sentences)


def clean(raw: str) -> str:
    """Normalise whitespace and punctuation without changing wording."""
    text = raw.replace("\r\n", "\n").replace("　", " ")
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)          # markdown headings
    text = re.sub(r"^\s*[-*>]\s+", "", text, flags=re.M)        # list / quote markers
    text = re.sub(r"[*_`]{1,3}", "", text)                      # emphasis markers
    text = text.replace("...", "…")
    if HAN.search(text):
        text = re.sub(r"(?<!\d),(?!\d)", "，", text)  # keep 1,000 intact
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split(raw: str) -> Script:
    """One sentence per terminal punctuation mark; blank lines are paragraph breaks.

    A line break ends a sentence too, unless the line ends in a comma or a dash: then the sentence continues on the
    next line and is voiced in one take (voicing the clause alone gives it a final, cut-off cadence).
    """
    text = clean(raw)
    script = Script(raw=raw)
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    single_lines = len(paragraphs) == 1
    if single_lines:
        # One sentence per line is common in scripts; treat each line as its own paragraph-less unit.
        paragraphs = [text]
    sid = 0
    for p_index, paragraph in enumerate(paragraphs):
        units: list[str] = []
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        joined: list[str] = []
        for line in lines:
            if joined and joined[-1].endswith(CONTINUES):
                joined[-1] += (" " if joined[-1].endswith(",") else "") + line
            else:
                joined.append(line)
        for line in joined:
            parts = re.findall(rf"[^{END}]+[{END}]+|[^{END}]+$", line)
            units.extend(part.strip() for part in parts if part.strip())
        for u_index, unit in enumerate(units):
            sid += 1
            kind = "question" if unit.endswith(("？", "?")) else "lead" if unit.endswith(("：", ":")) else "statement"
            script.sentences.append(Sentence(sid, unit, p_index, kind=kind,
                                             ends_paragraph=(not single_lines and u_index == len(units) - 1)))
    return script


def _zh_rules() -> list[tuple[str, str]]:
    """Rules from SPOKEN_FILE, longest phrase first; reread whenever the file changes."""
    path = Path(SPOKEN_FILE)
    try:
        stamp = path.stat().st_mtime_ns
    except FileNotFoundError:
        return []
    if _spoken_cache.get("key") != (path, stamp):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
            raise ValueError(f"{path.name}: every line must be `phrase: what to say` (both text)")
        _spoken_cache.update(key=(path, stamp), rules=sorted(data.items(), key=lambda kv: -len(kv[0])))
    return _spoken_cache["rules"]


def _respell(text: str, rules: list[tuple[str, str]]) -> str:
    """Apply the rules in one left-to-right pass, longest match first, so a replacement is never rewritten."""
    if not rules:
        return text
    pattern = re.compile("|".join(re.escape(phrase) for phrase, _ in rules))
    lookup = dict(rules)
    return pattern.sub(lambda m: lookup[m.group()], text)


def spoken_text(text: str, lang: str) -> str:
    """Text handed to TTS: quotes removed (they are not pronounced); in Chinese, this machine's respellings
    (SPOKEN_FILE) applied, + and = spelled out, dashes read as a pause, capital-letter acronyms spelled letter
    by letter, years and the digits after a decimal point read one by one. Years are read before the
    respellings, so a rule like "8年: 八年" cannot break "2018年". Subtitles keep the author's text."""
    for mark, repl in QUOTES.items():
        text = text.replace(mark, repl)
    if lang == "zh":
        text = ZH_YEAR.sub(lambda m: "".join(ZH_DIGITS[d] for d in m.group(1)) + "年", text)
        text = ZH_DECIMAL.sub(lambda m: m.group(1) + "点" + "".join(ZH_DIGITS[d] for d in m.group(2)), text)
        text = _respell(text, _zh_rules())
        text = ZH_SYMBOLS.sub(lambda m: ZH_SYMBOL_WORDS[m.group(1)], text)
        text = ZH_DASH.sub("，", text)
        text = ZH_ACRONYM.sub(lambda m: " ".join(m.group()), text)
    return text


def units(text: str) -> tuple[int, int]:
    """(Han characters, Latin/number words) — the two quantities speaking rate depends on."""
    return len(HAN.findall(text)), len(WORD.findall(text))


def estimate_seconds(script: Script, lang: str, config: dict) -> float:
    rate = config["tts"]["rate"]
    pauses = config["tts"]["pause_s"]
    total = 0.0
    for sentence in script.sentences:
        han, words = units(sentence.text)
        if lang == "zh":
            total += han / rate["zh_chars_per_s"] + words / rate["en_words_per_s"]
        else:
            total += (words or han) / rate["en_words_per_s"]
        total += pauses[sentence.pause_kind]
    return round(total, 1)
