"""CosyVoice provider: talks to engines/cosyvoice_worker.py running in its own environment.

CosyVoice exposes no durations, so this provider returns proportional timings
inside the audible span (exact=False); subtitles.align refines them with
Whisper word timestamps when faster-whisper is installed.
"""
from __future__ import annotations

import atexit
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from ..config import PROJECT
from .base import SR, Speech, proportional_timings, speech_bounds

WORKER = PROJECT / "engines/cosyvoice_worker.py"
PYTHON = PROJECT / "engines/cosyvoice/.venv/bin/python"


class CosyVoiceProvider:
    name = "cosyvoice"

    def __init__(self, model: str = "cosyvoice2"):
        self.model = model
        self._proc: subprocess.Popen | None = None

    def cache_identity(self) -> dict:
        return {"provider": self.name, "model": self.model, "rev": 1}

    def available(self) -> bool:
        return PYTHON.exists() and WORKER.exists()

    def _worker(self) -> subprocess.Popen:
        if self._proc is None or self._proc.poll() is not None:
            self._proc = subprocess.Popen([str(PYTHON), str(WORKER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, text=True, bufsize=1)
            atexit.register(self.close)
        return self._proc

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.stdin.close()
            try:
                self._proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def synth(self, text: str, lang: str, voice: str, speed: float) -> Speech:
        with tempfile.TemporaryDirectory(prefix="vagent-cv-") as tmp:
            out = Path(tmp) / "clip.wav"
            proc = self._worker()
            proc.stdin.write(json.dumps({"text": text, "voice": voice, "speed": speed, "out": str(out)},
                                        ensure_ascii=False) + "\n")
            proc.stdin.flush()
            reply = json.loads(proc.stdout.readline() or '{"ok": false, "error": "worker exited"}')
            if not reply.get("ok"):
                raise RuntimeError(f"CosyVoice failed: {reply.get('error')}")
            audio, rate = sf.read(out, dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if rate != SR:
            audio = resample_poly(audio, SR, rate).astype(np.float32)
        start, end = speech_bounds(audio)
        return Speech(audio, proportional_timings(text, lang, start, end), False, engine=f"cosyvoice:{voice}",
                      notes=["timing from audible span; refine with Whisper alignment"])
