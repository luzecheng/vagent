"""Narration: synthesize each sentence separately (cached), join with natural pauses.

Returns a timeline with sentence- and unit-level timestamps in the final track.
Duration policy (config.duration):
  <= target_max_s            fine
  target_max_s..hard_cap_s   fine, flagged as long in the report
  > hard_cap_s               try a speed-up of at most max_speedup; if it still does not fit,
                             the status is OVER_LIMIT (the pipeline pauses) unless allow_long.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import cache as cachemod
from ..script.parse import Script, spoken_text
from ..tts import get_provider
from ..tts.base import SR, Speech, Unit


@dataclass
class Narration:
    lang: str
    audio: np.ndarray
    timeline: dict
    status: str           # OK | LONG | OVER_LIMIT
    speed: float

    @property
    def duration(self) -> float:
        return len(self.audio) / SR


def _synth_cached(provider, text: str, lang: str, voice: str, speed: float, cache: cachemod.Cache) -> Speech:
    digest = cachemod.key(provider.cache_identity(), lang, voice, round(speed, 3), text)
    meta = cache.get_json(digest)
    wav = cache.path(digest, ".wav")
    if meta and wav.exists():
        audio, _ = sf.read(wav, dtype="float32")
        speech = Speech(audio, [Unit(**u) for u in meta["units"]], meta["exact"], meta["engine"], meta["notes"])
        if speech.exact or meta.get("align_rev") == _align_rev():
            return speech
        # aligned by an older version: re-time the cached audio (the voice itself stays as it is)
        speech.notes = [n for n in speech.notes if not n.startswith("Whisper-aligned")]
        _align(speech, text, lang)
        _store(cache, digest, speech)
        return speech
    speech = provider.synth(text, lang, voice, speed)
    if not speech.exact:
        _align(speech, text, lang)
    sf.write(wav, speech.audio, SR)
    # continue with exactly what later runs will read back (16-bit), so fresh and cached runs agree bit for bit
    speech.audio, _ = sf.read(wav, dtype="float32")
    _store(cache, digest, speech)
    return speech


def _align_rev() -> int:
    from ..subtitles.align import ALIGN_REV

    return ALIGN_REV


def _align(speech: Speech, text: str, lang: str) -> None:
    from ..subtitles import align as alignmod

    units, matched = alignmod.align(speech.audio, text, lang)
    speech.units = units
    speech.notes.append(f"Whisper-aligned ({matched:.0%} of units matched)")


def _store(cache: cachemod.Cache, digest: str, speech: Speech) -> None:
    meta = {"units": [u.__dict__ for u in speech.units], "exact": speech.exact,
            "engine": speech.engine, "notes": speech.notes}
    if not speech.exact:
        meta["align_rev"] = _align_rev()
    cache.put_json(digest, meta)


def _assemble(script: Script, lang: str, spec: dict, config: dict, speed: float, log) -> tuple[np.ndarray, dict]:
    provider = get_provider(spec, config["paths"]["models"])
    cache = cachemod.Cache(config["paths"]["cache"], f"tts/{lang}")
    pauses = config["tts"]["pause_s"]
    # the video opens on its cover for cover_intro_s; speech starts 0.25 s after that
    lead = 0.25 + config["video"].get("cover_intro_s", 0.0)
    pieces = [np.zeros(int(lead * SR), np.float32)]
    cursor = lead
    sentences = []
    for sentence in script.sentences:
        speech = _synth_cached(provider, spoken_text(sentence.text, lang), lang, spec["voice"], speed, cache)
        units = [{"text": u.text, "start": round(cursor + u.start, 3), "end": round(cursor + u.end, 3)}
                 for u in speech.units]
        sentences.append({
            "id": sentence.id, "text": sentence.text, "paragraph": sentence.paragraph,
            "start": round(cursor + (speech.units[0].start if speech.units else 0.0), 3),
            "end": round(cursor + (speech.units[-1].end if speech.units else speech.duration), 3),
            "clip_start": round(cursor, 3), "clip_end": round(cursor + speech.duration, 3),
            "units": units, "exact": speech.exact, "engine": speech.engine, "notes": speech.notes,
        })
        pieces.append(speech.audio)
        cursor += speech.duration
        gap = pauses[sentence.pause_kind]
        pieces.append(np.zeros(int(gap * SR), np.float32))
        cursor += int(gap * SR) / SR
    audio = np.concatenate(pieces)
    log.event("tts", f"{lang}: {len(sentences)} sentences, {len(audio) / SR:.1f}s at speed {speed}")
    return audio, {"lang": lang, "voice": spec["voice"], "provider": spec["provider"], "speed": speed,
                   "duration": round(len(audio) / SR, 3), "sentences": sentences}


def narrate(script: Script, lang: str, config: dict, log) -> Narration:
    spec = dict(config["tts"][lang])
    limits = config["duration"]
    speed = float(spec.get("speed", 1.0))
    audio, timeline = _assemble(script, lang, spec, config, speed, log)
    duration = len(audio) / SR
    if duration > limits["hard_cap_s"] and not limits.get("allow_long"):
        needed = speed * duration / (limits["hard_cap_s"] - 0.5)
        if needed <= limits["max_speedup"]:
            log.event("tts", f"{lang}: {duration:.1f}s over cap; re-synthesizing at speed {needed:.3f}", autofix=True)
            audio, timeline = _assemble(script, lang, spec, config, round(needed, 3), log)
            speed = round(needed, 3)
            duration = len(audio) / SR
    if duration > limits["hard_cap_s"]:
        status = "LONG" if limits.get("allow_long") else "OVER_LIMIT"
    elif duration > limits["target_max_s"]:
        status = "LONG"
    else:
        status = "OK"
    timeline["status"] = status
    return Narration(lang, audio, timeline, status, speed)


def save(narration: Narration, directory: Path, stem: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{stem}.wav"
    sf.write(path, narration.audio, SR)
    return path
