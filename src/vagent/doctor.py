"""vagent doctor: check every dependency and say how to fix what is missing."""
from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess

from .config import PROJECT
from .llm.client import claude_binary

FONTS = {
    "Inter": ["~/Library/Fonts/Inter-Regular.otf", "/Library/Fonts/Inter-Regular.otf"],
    "Noto Sans CJK SC": ["~/Library/Fonts/NotoSansCJKsc-Regular.otf", "/Library/Fonts/NotoSansCJKsc-Regular.otf"],
}


def _font(name: str) -> str | None:
    for candidate in FONTS[name]:
        path = Path(candidate).expanduser()
        if path.exists():
            return str(path)
    return None


ESPEAK_MAX_PATH = 150  # espeak-ng stores its data path in a 160-byte buffer and appends file names to it


def espeak_path_ok(data_path: str) -> bool:
    return len(data_path.encode("utf-8")) <= ESPEAK_MAX_PATH


def check(config: dict) -> int:
    rows = []

    def item(ok: bool, name: str, detail: str, fix: str = ""):
        rows.append((ok, name, detail, fix))

    ffmpeg = shutil.which("ffmpeg")
    item(bool(ffmpeg), "ffmpeg", ffmpeg or "not found", "brew install ffmpeg")
    models = Path(config["paths"]["models"])
    for name in ("kokoro-v1.0.onnx", "voices-v1.0.bin", "kokoro-v1.1-zh.onnx", "voices-v1.1-zh.bin"):
        path = models / name
        item(path.exists(), f"model {name}", str(path) if path.exists() else "missing", "./install.sh")
    for font in FONTS:
        found = _font(font)
        item(bool(found), f"font {font}", found or "missing", "brew install --cask font-inter font-noto-sans-cjk-sc")
    claude = claude_binary()
    ok = Path(claude).exists()
    detail = claude
    if ok:
        try:
            detail += "  " + subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            ok, detail = False, f"{claude} does not run"
    item(ok, "Claude Code CLI (storyboard LLM)", detail, "install Claude Code and log in, or set VAGENT_CLAUDE_BIN")
    cosy = PROJECT / "engines/cosyvoice/.venv/bin/python"
    used = any(spec.get("provider") == "cosyvoice" for spec in config["tts"].values() if isinstance(spec, dict))
    item(cosy.exists(), "CosyVoice engine" + (" (configured voice)" if used else " (optional)"),
         str(cosy) if cosy.exists() else "not installed",
         "./install.sh --with-cosyvoice")
    try:
        import faster_whisper  # noqa: F401

        item(True, "faster-whisper (ASR check)", "installed")
    except ImportError:
        item(False, "faster-whisper (ASR check)", "missing", ".venv/bin/pip install faster-whisper")
    try:
        import espeakng_loader

        data = espeakng_loader.get_data_path()
        item(espeak_path_ok(data), "espeak-ng data path (English voice)",
             f"{len(data)} characters" if espeak_path_ok(data) else f"{len(data)} characters, longer than espeak-ng accepts",
             f"move the vagent folder somewhere shorter (e.g. ~/vagent) and rerun ./install.sh")
    except ImportError:
        item(False, "espeak-ng (English voice)", "missing", "./install.sh")
    inbox = Path(config["paths"]["inbox"])
    item(inbox.is_dir() and os.access(inbox, os.W_OK), "inbox folder", str(inbox), f"mkdir -p {inbox}")
    skill = Path.home() / ".claude/skills/make-video/SKILL.md"
    item(skill.exists(), "/make-video skill (optional)", str(skill) if skill.exists() else "not linked",
         f"ln -s {PROJECT / 'skill/make-video'} {skill.parent}")
    width = max(len(r[1]) for r in rows)
    failed = 0
    for ok, name, detail, fix in rows:
        mark = "OK " if ok else "!! "
        print(f"{mark} {name:<{width}}  {detail}" + ("" if ok else f"\n    fix: {fix}"))
        failed += 0 if ok or "optional" in name else 1
    print("\nall required dependencies present" if not failed else f"\n{failed} required item(s) missing")
    return 1 if failed else 0
