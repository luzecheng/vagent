"""Clean a raw script, split it into spoken sentences, and estimate duration."""
from __future__ import annotations

from dataclasses import dataclass, field
import re

HAN = re.compile(r"[一-鿿]")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-.%$]*")
END = "。！？；!?;"
QUOTES = {"“": "", "”": "", "‘": "", "’": "", '"': "", "「": "", "」": "", "『": "", "』": ""}
ZH_SYMBOLS = re.compile(r"\s*([+＋=＝])\s*")   # Chinese voices skip or garble these, so they are read as words
ZH_SYMBOL_WORDS = {"+": "加", "＋": "加", "=": "等于", "＝": "等于"}


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
    """One sentence per terminal punctuation mark; blank lines and line breaks are paragraph hints."""
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
        for line in paragraph.split("\n"):
            line = line.strip()
            if not line:
                continue
            parts = re.findall(rf"[^{END}]+[{END}]+|[^{END}]+$", line)
            units.extend(part.strip() for part in parts if part.strip())
        for u_index, unit in enumerate(units):
            sid += 1
            kind = "question" if unit.endswith(("？", "?")) else "lead" if unit.endswith(("：", ":")) else "statement"
            script.sentences.append(Sentence(sid, unit, p_index, kind=kind,
                                             ends_paragraph=(not single_lines and u_index == len(units) - 1)))
    return script


def spoken_text(text: str, lang: str) -> str:
    """Text handed to TTS: quotes removed (they are not pronounced); in Chinese, + and = spelled out."""
    for mark, repl in QUOTES.items():
        text = text.replace(mark, repl)
    if lang == "zh":
        text = ZH_SYMBOLS.sub(lambda m: ZH_SYMBOL_WORDS[m.group(1)], text)
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
