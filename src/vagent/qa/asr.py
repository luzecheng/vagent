"""Whisper round trip: transcribe narration back to text and compare with the script.

This is the automatic "listening" check: it catches skipped, garbled, or
misread words. It cannot judge how natural a voice sounds.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
import re

import numpy as np
from scipy.signal import resample_poly

PUNCT = re.compile(r"[\s，。？！、；：,.?!;:\"'“”‘’…\-—()（）《》〈〉【】「」『』]")


@lru_cache(maxsize=2)
def _model(size: str = "small"):
    from faster_whisper import WhisperModel

    return WhisperModel(size, device="cpu", compute_type="int8")


ASR_MODEL = "large-v3-turbo"  # accurate enough on short Chinese clips; "small" misheard too often


def transcribe(audio: np.ndarray, sr: int, lang: str, size: str = ASR_MODEL) -> str:
    if sr != 16000:
        audio = resample_poly(audio, 16000, sr).astype(np.float32)
    # No initial prompt: a prompt sentence can leak into short transcripts (seen: "普通话" appearing).
    segments, _ = _model(size).transcribe(audio, language=lang, beam_size=5, vad_filter=False,
                                          condition_on_previous_text=False)
    return "".join(s.text for s in segments).strip()


COMPARE_REV = 4  # bump when normalise / error_rate change: cached check results embed their outcome
ZH_DIGITS = str.maketrans("0123456789", "零一二三四五六七八九")
# characters that sound the same: Whisper picks one of them at random, so they compare equal
ZH_HOMOPHONES = str.maketrans("她它祂地得", "他他他的的")


def normalise(text: str, lang: str) -> str:
    text = PUNCT.sub("", text)
    if lang == "zh":
        try:
            import zhconv  # optional: traditional -> simplified

            text = zhconv.convert(text, "zh-cn")
        except ImportError:
            pass
        # digits and Chinese numerals compare equal digit for digit (Whisper writes "一九八二年" as "1982年")
        text = text.translate(ZH_DIGITS).translate(ZH_HOMOPHONES)
    return text.lower()


def _tokens(text: str, lang: str) -> list[str]:
    if lang == "zh":
        return list(normalise(text, lang))
    return [w for w in (PUNCT.sub("", word) for word in text.lower().split()) if w]


def error_rate(reference: str, hypothesis: str, lang: str) -> float:
    """Character error rate (zh) / word error rate (en) via edit distance."""
    ref, hyp = _tokens(reference, lang), _tokens(hypothesis, lang)
    if not ref:
        return 0.0
    d = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        prev, d[0] = d[0], i
        for j, h in enumerate(hyp, 1):
            prev, d[j] = d[j], min(d[j] + 1, d[j - 1] + 1, prev + (r != h))
    return d[len(hyp)] / len(ref)


def mismatches(reference: str, hypothesis: str, lang: str) -> list[str]:
    ref, hyp = normalise(reference, lang), normalise(hypothesis, lang)
    out = []
    for tag, a, b, c, d in SequenceMatcher(None, ref, hyp).get_opcodes():
        if tag != "equal":
            out.append(f"{tag}: “{ref[a:b]}” → “{hyp[c:d]}”")
    return out
