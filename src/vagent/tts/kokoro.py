"""Kokoro (ONNX) provider: English v1.0 voices and Chinese v1.1-zh voices, fully local.

Timings are exact: kokoro-onnx reports when every phoneme is spoken.
  zh: misaki ZHG2P v1.1 ends each syllable with a tone digit (1-5), so the
      n-th tone digit closes the n-th Han character.
  en: word boundaries are the space phonemes.
If the units cannot be matched one-to-one (e.g. digits read out as several
syllables), the sentence falls back to proportional timing and says so.
"""
from __future__ import annotations

from functools import cached_property
import hashlib
from pathlib import Path
import re

import numpy as np

from .base import HAN, SR, Speech, Unit, proportional_timings, text_units

MODELS = {
    "v1.0": ("kokoro-v1.0.onnx", "voices-v1.0.bin"),
    "v1.1-zh": ("kokoro-v1.1-zh.onnx", "voices-v1.1-zh.bin"),
}
TONE = set("12345")
MARKS = {"a": "āáǎà", "e": "ēéěè", "i": "īíǐì", "o": "ōóǒò", "u": "ūúǔù", "ü": "ǖǘǚǜ"}


def tone_mark(syllable: str) -> str:
    """'zhu4' -> 'zhù', 'lv4' -> 'lǜ', neutral 'de5' -> 'de' (pypinyin's TONE style)."""
    body, tone = (syllable[:-1], int(syllable[-1])) if syllable[-1].isdigit() else (syllable, 5)
    body = body.replace("v", "ü")
    if tone == 5:
        return body
    for vowel in ("a", "e"):
        if vowel in body:
            return body.replace(vowel, MARKS[vowel][tone - 1], 1)
    if "ou" in body:
        return body.replace("o", MARKS["o"][tone - 1], 1)
    for index in range(len(body) - 1, -1, -1):
        if body[index] in MARKS:
            return body[:index] + MARKS[body[index]][tone - 1] + body[index + 1:]
    return body


def load_pronunciations(path: Path) -> dict[str, list[str]]:
    import yaml

    if not path.exists():
        return {}
    entries = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    table = {}
    for phrase, reading in entries.items():
        syllables = str(reading).split()
        if len(syllables) != len(phrase):
            raise ValueError(f"zh_pronunciation: {phrase} has {len(phrase)} characters but {len(syllables)} syllables")
        table[phrase] = syllables
    return table
PUNCT = set(",.!?;:—…\"'()，。！？；：、")


class KokoroProvider:
    name = "kokoro"

    def __init__(self, models_dir: str | Path, model: str, pronunciations: Path | None = None):
        self.model = model
        self.models_dir = Path(models_dir)
        self.pronunciations = load_pronunciations(pronunciations) if pronunciations else {}

    def cache_identity(self) -> dict:
        lexicon = hashlib.sha256(repr(sorted(self.pronunciations.items())).encode()).hexdigest()[:12]
        return {"provider": self.name, "model": self.model, "rev": 2, "lexicon": lexicon}

    @cached_property
    def engine(self):
        from kokoro_onnx import Kokoro

        onnx, voices = MODELS[self.model]
        return Kokoro(str(self.models_dir / onnx), str(self.models_dir / voices))

    @cached_property
    def zh_g2p(self):
        import jieba
        from misaki import zh
        from pypinyin import load_phrases_dict

        # misaki segments with jieba and reads each word with pypinyin: keep every override phrase as one
        # word and give pypinyin its reading; misaki's tone-sandhi rules still apply on top.
        for phrase in self.pronunciations:
            jieba.add_word(phrase, freq=2_000_000)
        load_phrases_dict({p: [[tone_mark(s)] for s in syl] for p, syl in self.pronunciations.items()})
        return zh.ZHG2P(version="1.1")

    def voices(self) -> list[str]:
        return sorted(self.engine.get_voices())

    def synth(self, text: str, lang: str, voice: str, speed: float) -> Speech:
        if lang == "zh":
            return self._synth_zh(text, voice, speed)
        audio, sr, timings = self.engine.create_timed(text, voice=voice, speed=speed, lang="en-us")
        assert sr == SR
        units, exact = self._en_units(text, timings)
        return Speech(np.asarray(audio, dtype=np.float32), units, exact, engine=f"kokoro-{self.model}:{voice}")

    # ---------------------------------------------------------------- zh
    def _synth_zh(self, text: str, voice: str, speed: float) -> Speech:
        phonemes, _ = self.zh_g2p(text)
        audio, sr, timings = self.engine.create_timed(phonemes, voice=voice, speed=speed, is_phonemes=True)
        assert sr == SR
        audio = np.asarray(audio, dtype=np.float32)
        chars = text_units(text, "zh")
        syllable_ends = [t for t in timings if t.phoneme in TONE]
        if chars and all(HAN.fullmatch(c) for c in chars) and len(syllable_ends) == len(chars):
            units, start = [], None
            phoneme_iter = iter(timings)
            for char, close in zip(chars, syllable_ends):
                # the syllable starts at the first non-pause phoneme after the previous tone digit
                for t in phoneme_iter:
                    if t.phoneme not in PUNCT and t.phoneme != " " and t.phoneme != "/":
                        start = t.start
                        break
                units.append(Unit(char, round(start, 3), round(close.end, 3)))
                for t in phoneme_iter:  # advance to the closing tone digit
                    if t is close:
                        break
            return Speech(audio, units, True, engine=f"kokoro-{self.model}:{voice}")
        notes = [f"syllables {len(syllable_ends)} != units {len(chars)}; proportional timing"]
        first, last = _bounds(timings, len(audio) / SR)
        return Speech(audio, proportional_timings(text, "zh", first, last), False,
                      engine=f"kokoro-{self.model}:{voice}", notes=notes)

    # ---------------------------------------------------------------- en
    @staticmethod
    def _en_units(text: str, timings) -> tuple[list[Unit], bool]:
        words = text_units(text, "en")
        groups: list[list] = [[]]
        for t in timings:
            if t.phoneme == " ":
                if groups[-1]:
                    groups.append([])
            elif t.phoneme not in PUNCT:
                groups[-1].append(t)
        groups = [g for g in groups if g]
        if len(groups) == len(words):
            return [Unit(w, round(g[0].start, 3), round(g[-1].end, 3)) for w, g in zip(words, groups)], True
        first, last = _bounds(timings, timings[-1].end if timings else 0.0)
        return proportional_timings(text, "en", first, last), False


def _bounds(timings, fallback_end: float) -> tuple[float, float]:
    spoken = [t for t in timings if t.phoneme not in PUNCT and t.phoneme.strip()]
    if not spoken:
        return 0.0, fallback_end
    return spoken[0].start, spoken[-1].end
