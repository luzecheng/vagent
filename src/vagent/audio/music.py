"""Procedural ambient score: original, no samples, no third-party audio.

The key and chord progression are picked from a seed (the script hash), so
daily videos do not all share one loop.  Output: 48 kHz stereo float32.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
PROGRESSIONS = [  # semitone offsets from the root, voiced as 9th/7th chords
    [[0, 7, 15, 19, 22, 26], [-4, 3, 12, 15, 19, 24], [-9, 3, 10, 14, 19, 22], [-2, 5, 12, 14, 17, 19]],  # i-VI-III-VII
    [[0, 7, 16, 19, 23, 26], [-3, 4, 12, 16, 19, 23], [5, 12, 16, 21, 24, 28], [7, 14, 19, 23, 26, 28]],   # I-vi-IV-V
    [[0, 7, 15, 19, 22, 26], [5, 12, 15, 20, 24, 27], [-2, 5, 14, 17, 21, 24], [3, 10, 15, 19, 22, 26]],   # i-iv-VII-III
]
ROOTS = [45, 43, 47, 41, 48]  # A2, G2, B2, F2, C3


def _midi(n: float) -> float:
    return 440.0 * 2 ** ((n - 69) / 12)


def _env(n: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    env[:a] = np.linspace(0, 1, a) ** 2
    env[-r:] *= np.linspace(1, 0, r) ** 2
    return env


def compose(duration: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    progression = PROGRESSIONS[seed % len(PROGRESSIONS)]
    root = ROOTS[(seed // 7) % len(ROOTS)]
    bar = 8.0 + 2.0 * ((seed // 3) % 3) / 2  # 8-10 s per chord
    total = int(duration * SR)
    out = np.zeros((total, 2))
    t_bar = np.arange(int((bar + 4) * SR)) / SR
    for index in range(int(np.ceil(duration / bar)) + 1):
        start = int(index * bar * SR)
        if start >= total:
            break
        chord = [root + n for n in progression[index % 4]]
        seg = np.zeros((len(t_bar), 2))
        for note in chord:
            f = _midi(note)
            for side, detune in ((0, -0.003), (1, 0.003)):
                phase = rng.uniform(0, 2 * np.pi)
                tone = np.sin(2 * np.pi * f * (1 + detune) * t_bar + phase)
                tone += 0.15 * np.sin(2 * np.pi * 2 * f * (1 + detune) * t_bar + phase)
                seg[:, side] += (0.5 if note < root + 6 else 0.28) * tone
        seg *= _env(len(t_bar), 3.0, 4.0)[:, None]
        end = min(total, start + len(t_bar))
        out[start:end] += seg[:end - start]
        # sparse soft bell on the chord's top note, every half bar
        for half in range(2):
            b0 = start + int(half * bar / 2 * SR)
            if b0 >= total or rng.random() < 0.35:
                continue
            tb = np.arange(int(3.0 * SR)) / SR
            f = _midi(chord[-1 - half] + 12)
            bell = (np.sin(2 * np.pi * f * tb) + 0.2 * np.sin(2 * np.pi * 2.76 * f * tb)) * np.exp(-tb * 1.8) * 0.08
            e = min(total, b0 + len(tb))
            pan = 0.35 + 0.3 * rng.random()
            out[b0:e, 0] += (1 - pan) * bell[:e - b0]
            out[b0:e, 1] += pan * bell[:e - b0]
    out = sosfilt(butter(2, 1800, "low", fs=SR, output="sos"), out, axis=0)
    tail = out.copy()
    for delay, gain in ((0.113, 0.3), (0.171, 0.24), (0.239, 0.18), (0.317, 0.13)):
        d = int(delay * SR)
        tail[d:] += gain * out[:-d]
    tail /= np.max(np.abs(tail)) + 1e-9
    return tail.astype(np.float32)


def duck_gain(voice: np.ndarray, n: int, depth_db: float = 7.0) -> np.ndarray:
    """Per-sample gain lowering the music while the voice is audible (fast attack, slow release)."""
    frame = int(0.05 * SR)
    v = np.pad(voice[:n], (0, max(0, n - len(voice))))
    v = np.pad(v, (0, (-len(v)) % frame))
    rms = np.sqrt((v.reshape(-1, frame) ** 2).mean(axis=1))
    active = np.convolve((rms > 0.008).astype(float), np.ones(8), mode="full")[:len(rms)] > 0
    target = np.where(active, 10 ** (-depth_db / 20), 1.0)
    level, smooth = 1.0, np.empty_like(target)
    for i, value in enumerate(target):
        level += (0.35 if value < level else 0.06) * (value - level)
        smooth[i] = level
    return np.repeat(smooth, frame)[:n]
