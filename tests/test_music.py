"""Background music follows config audio.music in every style (classic, story, robot); default is off."""
from pathlib import Path

from vagent import config as configmod

ROOT = Path(__file__).resolve().parents[1]


def test_music_follows_config(tmp_path):
    missing = tmp_path / "no_local.yaml"
    assert configmod.music(configmod.load(local_path=missing)) is False
    on = tmp_path / "local.yaml"
    on.write_text("audio: {music: true}\n", encoding="utf-8")
    assert configmod.music(configmod.load(local_path=on)) is True


def test_renderers_do_not_force_music():
    for rel in ("story/render.py", "robotfilm/robot_story.py", "robotfilm/compose.py"):
        assert "music=True" not in (ROOT / rel).read_text(encoding="utf-8"), rel
