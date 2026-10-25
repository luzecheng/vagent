"""Per-sentence Whisper round trip on a finished narration track."""
from __future__ import annotations

import numpy as np

from ..tts.base import SR
from .asr import error_rate, mismatches, transcribe

FLAG = {"zh": 0.15, "en": 0.2}


def check(audio: np.ndarray, timeline: dict, lang: str) -> dict:
    rows, flagged = [], []
    for sentence in timeline["sentences"]:
        a, b = int(sentence["clip_start"] * SR), int(sentence["clip_end"] * SR)
        heard = transcribe(audio[a:b], SR, lang)
        rate = error_rate(sentence["text"], heard, lang)
        row = {"id": sentence["id"], "text": sentence["text"], "heard": heard, "error_rate": round(rate, 3)}
        rows.append(row)
        if rate > FLAG[lang]:
            flagged.append({**row, "diff": mismatches(sentence["text"], heard, lang)[:4]})
    total = sum(len(r["text"]) for r in rows) or 1
    weighted = sum(r["error_rate"] * len(r["text"]) for r in rows) / total
    return {"lang": lang, "overall_error_rate": round(weighted, 3), "flagged": flagged, "sentences": rows}


def markdown(result: dict) -> str:
    name = "字错误率" if result["lang"] == "zh" else "word error rate"
    lines = [f"## {result['lang']} 回听检查", "", f"- 整体{name}：{result['overall_error_rate']:.1%}",
             f"- 需要试听确认的句子：{len(result['flagged'])} 句", ""]
    for row in result["flagged"]:
        lines.append(f"- 第 {row['id']} 句（{row['error_rate']:.0%}）：原文“{row['text']}” / 听到“{row['heard']}”")
    if result["flagged"]:
        lines += ["", "注意：Whisper 自己也会写错同音字或标点，被标出的句子不一定真的读错，请试听确认。"]
    return "\n".join(lines) + "\n"
