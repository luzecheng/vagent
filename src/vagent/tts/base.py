"""TTS provider interface.

A provider turns one sentence into audio plus per-unit timings, where a unit
is one Han character (zh) or one word (en).  Exact timings come from the
engine when it exposes them; otherwise `proportional_timings` spreads the
sentence duration by character count and the result is marked inexact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Protocol

import numpy as np

SR = 24000
HAN = re.compile(r"[一-鿿]")
EN_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-.%$]*")


@dataclass
class Unit:
    text: str
    start: float
    end: float


@dataclass
class Speech:
    audio: np.ndarray          # mono float32 at SR
    units: list[Unit]          # characters (zh) or words (en), in order
    exact: bool                # True when timings come from the engine's own durations
    engine: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return len(self.audio) / SR


class Provider(Protocol):
    name: str

    def synth(self, text: str, lang: str, voice: str, speed: float) -> Speech: ...

    def cache_identity(self) -> dict: ...


def text_units(text: str, lang: str) -> list[str]:
    """Timing units in reading order: Han characters and Latin words (zh), words (en)."""
    if lang == "en":
        return EN_WORD.findall(text)
    return re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9][A-Za-z0-9'’\-.%$]*", text)


def proportional_timings(text: str, lang: str, start: float, end: float) -> list[Unit]:
    units = text_units(text, lang)
    if not units:
        return []
    weights = [1.0 if HAN.fullmatch(u) else max(1.0, len(u) / 2.5) for u in units]
    total = sum(weights)
    out, cursor = [], start
    for unit, weight in zip(units, weights):
        step = (end - start) * weight / total
        out.append(Unit(unit, round(cursor, 3), round(cursor + step, 3)))
        cursor += step
    return out


def speech_bounds(audio: np.ndarray, threshold: float = 0.01) -> tuple[float, float]:
    """First and last moment the waveform is clearly audible."""
    frame = int(0.01 * SR)
    if len(audio) < frame:
        return 0.0, len(audio) / SR
    rms = np.sqrt(np.convolve(audio.astype(np.float64) ** 2, np.ones(frame) / frame, mode="same"))
    loud = np.flatnonzero(rms > threshold)
    if not len(loud):
        return 0.0, len(audio) / SR
    return loud[0] / SR, loud[-1] / SR
