"""The output tidy-up keeps the two videos and publish notes, trashes what vagent generated, and never throws away
a file it does not recognise (2026-11-11: it trashed a night-sky photo the user had put in robot2/review)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("clean_output", ROOT / "skill/make-video/clean_output.py")
clean_output = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clean_output)


def test_keeps_videos_and_user_files_trashes_generated(tmp_path, monkeypatch):
    d = tmp_path / "2026-11-11_x"
    for rel in ("publish_notes.md", "storyboard.json", "build/voice.wav", "robot2/robot2_portrait.mp4",
                "robot2/robot2_en_landscape.mp4", "robot2/beats.py", "robot2/frames/道具图_v1.png",
                "robot2/review/sheet_portrait.png", "robot2/review/30424733d2f451c15ba796faa1a34c2c.jpg"):
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text("x")
    trashed = []
    monkeypatch.setattr(clean_output.subprocess, "run", lambda cmd, check: trashed.extend(Path(p) for p in cmd[1:])
                        or [p.unlink() for p in map(Path, cmd[1:])])
    clean_output.clean(d, go=True)
    left = sorted(p.relative_to(d).as_posix() for p in d.rglob("*") if p.is_file())
    assert left == ["publish_notes.md", "robot2/review/30424733d2f451c15ba796faa1a34c2c.jpg",
                    "robot2_en_landscape.mp4", "robot2_portrait.mp4"]
    assert not any(p.name.endswith(".jpg") for p in trashed)
