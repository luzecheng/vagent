"""Blind voice audition: same passage, several engines/voices, anonymised labels.

Writes <dir>/sample_A.wav ... plus audition.md (what to listen for, objective
Whisper error rate and speaking rate per sample) and a sealed key file
(audition_key.json) mapping labels to engines.
"""
from __future__ import annotations

import json
from pathlib import Path
import random

import numpy as np
import soundfile as sf

from .script.parse import split, spoken_text, units
from .tts import get_provider
from .tts.base import SR

PASSAGE = """你是不是也这样：每年都立很多目标，到了年底，一个都没完成？
问题往往不在意志力，而在目标太大。
小到什么程度？
小到你今天状态再差，也能做到。
有人会说：这么少，有什么用？
用处不在当天，而在不间断。
一页书不起眼，可一年下来，就是好几本书。"""

CANDIDATES = [
    {"provider": "kokoro", "model": "v1.1-zh", "voice": "zm_010"},
    {"provider": "kokoro", "model": "v1.1-zh", "voice": "zm_029"},
    {"provider": "kokoro", "model": "v1.1-zh", "voice": "zm_054"},
    {"provider": "kokoro", "model": "v1.1-zh", "voice": "zm_080"},
    {"provider": "cosyvoice", "model": "cosyvoice-300m-sft", "voice": "sft:中文男"},
    {"provider": "cosyvoice", "model": "cosyvoice2", "voice": "cv2:male_ref"},
]


def run(out_dir: Path, config: dict, log, candidates=None, seed: int = 7) -> Path:
    from .qa.asr import error_rate, mismatches, transcribe

    out_dir.mkdir(parents=True, exist_ok=True)
    script = split(PASSAGE)
    candidates = list(candidates or CANDIDATES)
    labels = [chr(ord("A") + i) for i in range(len(candidates))]
    random.Random(seed).shuffle(candidates)
    key, rows = {}, []
    reference = "".join(spoken_text(s.text, "zh") for s in script.sentences)
    han, _ = units(reference)
    for label, spec in zip(labels, candidates):
        provider = get_provider(spec, config["paths"]["models"])
        pieces = []
        for sentence in script.sentences:
            speech = provider.synth(spoken_text(sentence.text, "zh"), "zh", spec["voice"], 1.0)
            pieces += [speech.audio, np.zeros(int(0.4 * SR), np.float32)]
        if hasattr(provider, "close"):
            provider.close()  # free the model before the next candidate loads its own
        audio = np.concatenate(pieces)
        audio = audio / max(1e-6, float(np.max(np.abs(audio)))) * 0.89
        sf.write(out_dir / f"sample_{label}.wav", audio, SR)
        heard = transcribe(audio, SR, "zh")
        cer = error_rate(reference, heard, "zh")
        rows.append((label, len(audio) / SR, han / (len(audio) / SR), cer, mismatches(reference, heard, "zh")[:4]))
        key[label] = spec
        log.event("audition", f"sample {label}: {len(audio) / SR:.1f}s, CER {cer:.1%}")
    (out_dir / "audition_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = ["# 中文音色盲听", "", "同一段文字，每个样本只换了声音。请先只听，不要打开 audition_key.json。", "",
             "听的时候注意：像不像真人口播；问句的语调；停顿是否自然；有没有电音、吞字、怪异重音。", "",
             "| 样本 | 时长 | 语速（字/秒） | Whisper 回听误差 | 回听差异（前几处） |", "|---|---|---|---|---|"]
    for label, seconds, rate, cer, diffs in rows:
        lines.append(f"| {label} | {seconds:.1f}s | {rate:.2f} | {cer:.1%} | {'；'.join(diffs) or '无'} |")
    lines += ["", "说明：回听误差只说明“听不听得清”，不代表自然度；"
              "Whisper 本身也会把同音字写错，个位数百分比基本可以忽略。"]
    (out_dir / "audition.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_dir
