import pytest

from vagent.script import parse


@pytest.fixture(autouse=True)
def _no_personal_spoken_rules(tmp_path, monkeypatch):
    """Tests never read the user's own config/zh_spoken.yaml."""
    monkeypatch.setattr(parse, "SPOKEN_FILE", tmp_path / "no_zh_spoken.yaml")
