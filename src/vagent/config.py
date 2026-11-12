"""Layered configuration: config/default.yaml <- brand.yaml <- config/local.yaml <- command-line overrides.

config/local.yaml is git-ignored: per-machine choices (e.g. the CosyVoice voice) that should not be published."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

PROJECT = Path(__file__).resolve().parents[2]


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _brand_overrides(brand: dict) -> dict:
    """brand.yaml uses a few friendly top-level keys; map them onto config paths."""
    mapped: dict[str, Any] = {"brand": brand}
    voices = brand.get("voices") or {}
    if voices:
        mapped["tts"] = {lang: {"voice": voice} for lang, voice in voices.items()}
    if brand.get("duration"):
        mapped["duration"] = brand["duration"]
    return mapped


def load(overrides: dict | None = None, brand_path: Path | None = None, local_path: Path | None = None) -> dict:
    config = yaml.safe_load((PROJECT / "config/default.yaml").read_text(encoding="utf-8"))
    brand_file = brand_path or PROJECT / "brand.yaml"
    if brand_file.exists():
        config = _merge(config, _brand_overrides(yaml.safe_load(brand_file.read_text(encoding="utf-8")) or {}))
    local_file = local_path or PROJECT / "config/local.yaml"
    if local_file.exists():
        config = _merge(config, yaml.safe_load(local_file.read_text(encoding="utf-8")) or {})
    config = _merge(config, overrides or {})
    for key, value in config["paths"].items():
        path = Path(value)
        config["paths"][key] = str(path if path.is_absolute() else PROJECT / path)
    return config


def music(config: dict | None = None) -> bool:
    """Whether to lay background music under the voice-over (config audio.music; off unless set)."""
    return bool(((config if config is not None else load()).get("audio") or {}).get("music", False))
