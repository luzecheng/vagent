"""Whisper forced alignment for engines that do not report timings (e.g. CosyVoice).

Per sentence clip: transcribe with word timestamps, match the recognised units
to the script's units, give matched units their recognised times, and
interpolate the rest between matched neighbours.

The clip is transcribed without a prompt first.  Giving Whisper the sentence as
initial prompt steers it toward the right characters on some clips, but on
others it makes it hallucinate (seen: "请点赞、订阅、打赏" over a plain sentence,
5% matched, half the sentence squeezed into 0.3 s).  So the prompted pass only
runs when the plain one misses characters, and the better match wins.

Whisper also tends to start a word right where the previous one ended, so a
pause between two words is counted as part of the second.  A unit whose span
holds a clear pause in the waveform therefore starts where that pause ends.
"""
from __future__ import annotations

from difflib import SequenceMatcher
import re

import numpy as np
from scipy.signal import resample_poly

from ..tts.base import SR, Unit, speech_bounds, text_units

HAN = re.compile(r"[一-鿿]")
ALIGN_REV = 3   # bump when alignment changes: cached sentences with an older rev are re-aligned from their audio


def _simplify(text: str) -> str:
    try:
        import zhconv

        return zhconv.convert(text, "zh-cn")
    except ImportError:
        return text


def _recognised_units(audio: np.ndarray, text: str, lang: str, prompt: bool) -> list[tuple[str, float, float]]:
    from ..qa.asr import _model

    clip = resample_poly(audio, 16000, SR).astype(np.float32)
    segments, _ = _model("small").transcribe(clip, language=lang, word_timestamps=True, beam_size=5,
                                              initial_prompt=text if prompt else None,
                                              condition_on_previous_text=False)
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


PAUSE_S = 0.15   # silence at least this long, inside one unit's span, is a pause before it


def _pauses(audio: np.ndarray, threshold: float = 0.01) -> list[tuple[float, float]]:
    """(start, end) of every stretch of near silence at least PAUSE_S long."""
    frame = int(0.01 * SR)
    n = len(audio) // frame
    if not n:
        return []
    rms = np.sqrt(np.mean(audio[:n * frame].astype(np.float64).reshape(n, frame) ** 2, axis=1))
    out, run = [], None
    for k, quiet in enumerate(np.append(rms < threshold, False)):
        if quiet and run is None:
            run = k
        elif not quiet and run is not None:
            if (k - run) * 0.01 >= PAUSE_S:
                out.append((run * 0.01, k * 0.01))
            run = None
    return out


def _match(reference: list[str], heard: list[tuple[str, float, float]]):
    """Recognised times for the reference units Whisper heard (None for the rest), and the matched fraction."""
    times: list[tuple[float, float] | None] = [None] * len(reference)
    matcher = SequenceMatcher(None, [r.lower() for r in reference], [h[0] for h in heard], autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            _, start, end = heard[block.b + k]
            times[block.a + k] = (start, end)
    return times, sum(t is not None for t in times) / len(reference)


def align(audio: np.ndarray, text: str, lang: str) -> tuple[list[Unit], float]:
    """Returns (units, matched fraction)."""
    reference = text_units(text, lang)
    if not reference:
        return [], 1.0
    times, matched = _match(reference, _recognised_units(audio, text, lang, prompt=False))
    if matched < 1.0:
        prompted = _match(reference, _recognised_units(audio, text, lang, prompt=True))
        if prompted[1] > matched:
            times, matched = prompted
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
    pauses = _pauses(audio)
    for i, (start, end) in enumerate(times):
        inside = [b for a, b in pauses if start <= a and b < end]
        if inside:
            times[i] = (inside[-1], end)
    units, previous_end = [], first
    for piece, (start, end) in zip(reference, times):
        start = max(start, previous_end)
        end = max(end, start + 0.04)
        units.append(Unit(piece, round(start, 3), round(end, 3)))
        previous_end = end
    return units, matched
