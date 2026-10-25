"""TTS provider registry. Add a provider by implementing tts.base.Provider and registering it here."""
from __future__ import annotations

from .base import Provider, Speech, Unit  # noqa: F401


def get_provider(spec: dict, models_dir: str) -> Provider:
    name = spec["provider"]
    if name == "kokoro":
        from .kokoro import KokoroProvider

        from ..config import PROJECT

        return KokoroProvider(models_dir, spec.get("model", "v1.0"), PROJECT / "config/zh_pronunciation.yaml")
    if name == "cosyvoice":
        from .cosyvoice import CosyVoiceProvider

        return CosyVoiceProvider(spec.get("model", "cosyvoice2"))
    raise ValueError(f"unknown TTS provider: {name}")
