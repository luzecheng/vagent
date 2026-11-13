"""CosyVoice worker, run with engines/cosyvoice/.venv/bin/python.

Reads one JSON request per line on stdin, writes one JSON reply per line on stdout:
  {"text": "...", "voice": "sft:中文男" | "cv2:<prompt name>", "speed": 1.0, "out": "/path.wav"}
  -> {"ok": true, "sample_rate": 24000, "seconds": 3.2} | {"ok": false, "error": "..."}

Voices
  sft:<speaker>     CosyVoice-300M-SFT built-in speaker (e.g. 中文男)
  cv2:<name>        CosyVoice2-0.5B zero-shot, prompt audio prompts/<name>.wav + prompts/<name>.txt
  cv2x:<name>       the same voice speaking another language than its prompt (cross-lingual: prompt text unused)
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

ROOT = Path(__file__).resolve().parent / "cosyvoice"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "third_party/Matcha-TTS"))

import torch  # noqa: E402
import torchaudio  # noqa: E402

_models = {}
# CPU by default: on Apple-silicon MPS this model produced corrupted audio (verified 2026-10-25:
# full-scale noise from CosyVoice2, garbled words from the SFT model). MPS stays opt-in for testing.
DEVICE = os.environ.get("VAGENT_COSYVOICE_DEVICE", "cpu")


def _to_device(engine):
    """CosyVoice only chooses CUDA or CPU; move it onto Apple's GPU when available."""
    if DEVICE == "cpu":
        return engine
    device = torch.device(DEVICE)
    for part in ("llm", "flow", "hift"):
        getattr(engine.model, part).to(device)
    engine.model.device = device
    engine.frontend.device = device
    return engine


def model(kind: str):
    if kind not in _models:
        if kind == "sft":
            from cosyvoice.cli.cosyvoice import CosyVoice

            _models[kind] = _to_device(CosyVoice(str(ROOT / "pretrained_models/CosyVoice-300M-SFT"), load_jit=False,
                                                 fp16=False))
        else:
            from cosyvoice.cli.cosyvoice import CosyVoice2

            _models[kind] = _to_device(CosyVoice2(str(ROOT / "pretrained_models/CosyVoice2-0.5B"), load_jit=False,
                                                  load_trt=False, fp16=False))
    return _models[kind]


def synth(request: dict) -> dict:
    kind, _, name = request["voice"].partition(":")
    engine = model("sft" if kind == "sft" else "cv2")   # cv2 and cv2x share one loaded model
    speed = float(request.get("speed", 1.0))
    if kind == "sft":
        chunks = engine.inference_sft(request["text"], name, stream=False, speed=speed)
    else:
        prompt_dir = Path(__file__).resolve().parent / "prompts"
        prompt_wav = str(prompt_dir / f"{name}.wav")
        if kind == "cv2x":
            chunks = engine.inference_cross_lingual(request["text"], prompt_wav, stream=False, speed=speed)
        else:
            prompt_text = (prompt_dir / f"{name}.txt").read_text(encoding="utf-8").strip()
            chunks = engine.inference_zero_shot(request["text"], prompt_text, prompt_wav, stream=False, speed=speed)
    audio = torch.cat([chunk["tts_speech"] for chunk in chunks], dim=1)
    torchaudio.save(request["out"], audio, engine.sample_rate)
    return {"ok": True, "sample_rate": engine.sample_rate, "seconds": audio.shape[1] / engine.sample_rate}


def main() -> None:
    torch.set_num_threads(4)
    replies = sys.stdout
    sys.stdout = sys.stderr  # libraries print progress to stdout; keep that channel for JSON replies only
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = synth(json.loads(line))
        except Exception as exc:  # report to the parent, keep serving
            reply = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        replies.write(json.dumps(reply, ensure_ascii=False) + "\n")
        replies.flush()


if __name__ == "__main__":
    main()
