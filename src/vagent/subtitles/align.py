"""Whisper forced alignment for engines that do not report timings (e.g. CosyVoice).

Per sentence clip: transcribe with word timestamps (the sentence itself is
the prompt, which steers recognition toward the right characters), match the
recognised units to the script's units, give matched units their recognised
times, and interpolate the rest between matched neighbours.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re

import numpy as np
from scipy.signal import resample_poly

from ..tts.base import SR, Unit, speech_bounds, text_units

HAN = re.compile(r"[一-鿿]")


def _simplify(text: str) -> str:
    try:
        import zhconv

        return zhconv.convert(text, "zh-cn")
    except ImportError:
        return text


def _recognised_units(audio: np.ndarray, text: str, lang: str) -> list[tuple[str, float, float]]:
    from ..qa.asr import _model

    clip = resample_poly(audio, 16000, SR).astype(np.float32)
    segments, _ = _model("small").transcribe(clip, language=lang, word_timestamps=True, beam_size=5,
                                              initial_prompt=text, condition_on_previous_text=False)
    out = []
    for segment in segments:
        for word in segment.words or []:
            token = _simplify(word.word.strip())
            pieces = text_units(token, lang)
            if not pieces:
                continue
            step = (word.end - word.start) / len(pieces)
            for i, piece in enumerate(pieces):
                out.append((piece.lower(), word.start + i * step, word.start + (i + 1) * step))
    return out


def align(audio: np.ndarray, text: str, lang: str) -> tuple[list[Unit], float]:
    """Returns (units, matched fraction)."""
    reference = text_units(text, lang)
    if not reference:
        return [], 1.0
    heard = _recognised_units(audio, text, lang)
    times: list[tuple[float, float] | None] = [None] * len(reference)
    matcher = SequenceMatcher(None, [r.lower() for r in reference], [h[0] for h in heard], autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            _, start, end = heard[block.b + k]
            times[block.a + k] = (start, end)
    matched = sum(t is not None for t in times) / len(reference)
    first, last = speech_bounds(audio)
    # interpolate gaps between known anchors (sentence edges come from the waveform)
    anchors = [(-1, first, first)] + [(i, t[0], t[1]) for i, t in enumerate(times) if t] + [(len(reference), last, last)]
    for (i0, _, end0), (i1, start1, _) in zip(anchors, anchors[1:]):
        gap = i1 - i0 - 1
        if gap <= 0:
            continue
        span = max(0.0, start1 - end0)
        for k in range(gap):
            times[i0 + 1 + k] = (end0 + span * k / gap, end0 + span * (k + 1) / gap)
    units, previous_end = [], first
    for piece, (start, end) in zip(reference, times):
        start = max(start, previous_end)
        end = max(end, start + 0.04)
        units.append(Unit(piece, round(start, 3), round(end, 3)))
        previous_end = end
    return units, matched
