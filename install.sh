#!/usr/bin/env bash
# One-step setup for vagent on macOS (Apple silicon or Intel).
#   ./install.sh                  core: ffmpeg, fonts, Python env, Kokoro models, Whisper
#   ./install.sh --with-cosyvoice also the optional CosyVoice engine (~5 GB, slow on CPU-only Macs)
set -euo pipefail
cd "$(dirname "$0")"
WITH_COSY=0
[ "${1:-}" = "--with-cosyvoice" ] && WITH_COSY=1

command -v brew >/dev/null || { echo "Homebrew is required: https://brew.sh"; exit 1; }
command -v ffmpeg >/dev/null || brew install ffmpeg
brew list --cask font-inter >/dev/null 2>&1 || brew install --cask font-inter
brew list --cask font-noto-sans-cjk-sc >/dev/null 2>&1 || brew install --cask font-noto-sans-cjk-sc

# Python 3.11-3.13: spaCy (needed by the English phonemizer) has no build for newer versions yet
supported() { "$1" -c 'import sys; sys.exit(not (3, 11) <= sys.version_info[:2] <= (3, 13))' 2>/dev/null; }
PY=""
for candidate in ${PYTHON:-} python3.12 python3.11 python3.13 python3; do
  if command -v "$candidate" >/dev/null && supported "$candidate"; then PY=$candidate; break; fi
done
if [ -z "$PY" ]; then
  echo "No Python 3.11-3.13 found; installing python@3.12 with Homebrew"
  brew install python@3.12
  PY="$(brew --prefix python@3.12)/bin/python3.12"
fi
echo "Using $("$PY" --version) ($(command -v "$PY"))"
if [ -d .venv ] && ! supported .venv/bin/python; then
  echo "Recreating .venv: it was built with an unsupported Python"
  rm -rf .venv
fi
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -e ".[asr,test]" zhconv

mkdir -p models
BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1
for f in kokoro-v1.0.onnx voices-v1.0.bin kokoro-v1.1-zh.onnx voices-v1.1-zh.bin; do
  [ -f "models/$f" ] || curl -L --fail -o "models/$f" "$BASE/$f"
done
# Whisper (ASR round-trip check) downloads its model on first use; warm it now.
.venv/bin/python -c "from faster_whisper import WhisperModel; WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')"

if [ "$WITH_COSY" = 1 ]; then
  mkdir -p engines
  [ -d engines/cosyvoice ] || git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git engines/cosyvoice
  ( cd engines/cosyvoice && [ -d .venv ] || "$PY" -m venv .venv )
  engines/cosyvoice/.venv/bin/pip install -q "torch==2.3.1" "torchaudio==2.3.1" "numpy==1.26.4" conformer==0.3.2 \
    diffusers==0.29.0 hydra-core==1.3.2 HyperPyYAML==1.2.3 inflect==7.3.1 librosa==0.10.2 lightning==2.2.4 \
    modelscope==1.20.0 omegaconf==2.3.0 onnx==1.16.0 onnxruntime==1.18.0 "openai-whisper>=20240930" "protobuf==4.25" \
    pyarrow==18.1.0 "pydantic==2.7.0" pyworld==0.3.4 soundfile transformers==4.51.3 x-transformers==2.11.24 \
    wetext==0.0.4 huggingface_hub
  engines/cosyvoice/.venv/bin/python - <<'PYEOF'
from huggingface_hub import snapshot_download
for repo in ("FunAudioLLM/CosyVoice2-0.5B", "FunAudioLLM/CosyVoice-300M-SFT"):
    snapshot_download(repo_id=repo, local_dir=f"engines/cosyvoice/pretrained_models/{repo.split('/')[1]}")
PYEOF
fi

# /make-video in Claude Code: link the skill (kept in this project) into the user's skills folder
mkdir -p inbox "$HOME/.claude/skills"
if [ ! -e "$HOME/.claude/skills/make-video" ]; then
  ln -s "$PWD/skill/make-video" "$HOME/.claude/skills/make-video"
fi

[ -f .env ] || printf '# machine-local settings\n# VAGENT_CLAUDE_PROXY=http://127.0.0.1:7890\n' > .env
.venv/bin/vagent doctor
