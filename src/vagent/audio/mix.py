"""Final audio: voice normalised to about -16 LUFS, optional ducked music well below it, fades, limiter."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

import numpy as np
import soundfile as sf

from .music import SR, compose, duck_gain

VOICE_LUFS = -16.0
MUSIC_BELOW_VOICE_LU = 14.0  # music sits this far under the voice before ducking


def _loudness(path: Path) -> dict:
    text = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null",
                           "-"], capture_output=True, text=True).stderr
    return json.loads(text[text.rfind("{"):text.rfind("}") + 1])


def _integrated(path: Path) -> float:
    text = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-filter_complex", "ebur128=peak=true", "-f", "null",
                           "-"], capture_output=True, text=True).stderr
    summary = text[text.rfind("Summary:"):]
    return float(re.search(r"I:\s+(-?[\d.]+)", summary).group(1))


def normalise_voice(voice_wav: Path, out: Path) -> Path:
    m = _loudness(voice_wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(voice_wav), "-af",
                    f"loudnorm=I={VOICE_LUFS}:TP=-2:LRA=11:linear=true:measured_I={m['input_i']}:"
                    f"measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                    f"offset={m['target_offset']}", "-ar", str(SR), "-ac", "1", str(out)], check=True)
    return out


def _music_bed(voice: np.ndarray, duration: float, seed: int, work: Path) -> np.ndarray:
    n = len(voice)
    music = compose(duration, seed)[:n]
    music_path = work / "music_raw.wav"
    sf.write(music_path, music, SR)
    gain = 10 ** ((VOICE_LUFS - MUSIC_BELOW_VOICE_LU - _integrated(music_path)) / 20)
    music = music * gain * duck_gain(voice, n)[:, None]
    fade_in, fade_out = int(1.5 * SR), int(2.5 * SR)
    music[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
    music[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None]
    return music


def mix(voice_wav: Path, duration: float, seed: int, work: Path, music: bool = True) -> tuple[Path, dict]:
    """Return (final_mix.wav, stats).  The final file is measured and corrected to VOICE_LUFS.

    music=False gives a voice-only track (config `audio.music`)."""
    work.mkdir(parents=True, exist_ok=True)
    voice_path = normalise_voice(voice_wav, work / "voice_norm.wav")
    voice, _ = sf.read(voice_path, dtype="float32")
    n = int(duration * SR)
    voice = np.pad(voice, (0, max(0, n - len(voice))))[:n]
    # mono voice into stereo at -3 dB per channel keeps its loudness unchanged (R128 sums channel energy)
    premix = (voice * np.float32(1 / np.sqrt(2)))[:, None].repeat(2, axis=1)
    bed = _music_bed(voice, duration, seed, work) if music else None
    if bed is not None:
        premix = premix + bed
    pre_path = work / "premix.wav"
    sf.write(pre_path, premix.astype(np.float32), SR)
    correction = VOICE_LUFS - _integrated(pre_path)
    out = work / "final_mix.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(pre_path), "-af",
                    f"volume={correction:.2f}dB,alimiter=limit=0.84:level=false:attack=5:release=50",
                    "-ar", str(SR), str(out)], check=True)
    music_lufs = None
    if bed is not None:
        sf.write(work / "music.wav", bed.astype(np.float32), SR)
        music_lufs = round(_integrated(work / "music.wav") + correction, 1)
    stats = {"target_lufs": VOICE_LUFS, "final_lufs": _integrated(out), "music_lufs": music_lufs,
             "correction_db": round(correction, 2), "peak_dbtp": _true_peak(out)}
    return out, stats


def _true_peak(path: Path) -> float:
    text = subprocess.run(["ffmpeg", "-nostats", "-i", str(path), "-filter_complex", "ebur128=peak=true", "-f", "null",
                           "-"], capture_output=True, text=True).stderr
    summary = text[text.rfind("Summary:"):]
    return float(re.search(r"Peak:\s+(-?[\d.]+)", summary).group(1))
