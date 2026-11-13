import json
import os

import pytest

from vagent import pipeline
from vagent.inbox import AlreadyRunning, Lock, Watcher
from vagent.script import frontmatter
from vagent.script.parse import split


# ---------------------------------------------------------------- settings block and episodes
def test_front_matter_options_are_read_and_removed():
    options, body = frontmatter.split_front_matter("---\nallow_long: true\ndisclaimer: off\n---\n第一句。")
    assert options == {"allow_long": True, "disclaimer": "off"}
    assert body == "第一句。"
    assert frontmatter.overrides(options) == {"duration": {"allow_long": True}, "disclaimer_override": "off"}


def test_text_without_settings_is_untouched():
    raw = "第一句。\n---\n第二集。"
    assert frontmatter.split_front_matter(raw) == ({}, raw)
    # a script that opens with an episode break is not a settings block
    raw = "---\n第一集。\n---\n第二集。"
    assert frontmatter.split_front_matter(raw) == ({}, raw)


def test_unknown_or_bad_settings_are_rejected_with_a_clear_message():
    with pytest.raises(frontmatter.FrontMatterError, match="speed"):
        frontmatter.split_front_matter("---\nspeed: 2\n---\n正文。")
    with pytest.raises(frontmatter.FrontMatterError, match="true 或 false"):
        frontmatter.split_front_matter("---\nallow_long: maybe\n---\n正文。")


def test_episode_breaks_split_the_script_and_are_never_spoken():
    parts = frontmatter.episodes("第一集第一句。\n第一集第二句。\n\n---\n\n第二集。\n----\n")
    assert parts == ["第一集第一句。\n第一集第二句。", "第二集。"]
    assert all("-" not in s.text for p in parts for s in split(p).sentences)


def test_run_script_makes_one_folder_per_episode(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "_run_one", lambda text, config, out, stage: calls.append((text, out.name)) or
                        (3 if "长" in text else 0))
    code = pipeline.run_script("第一集。\n---\n第二集很长。", "x", {"paths": {"output": str(tmp_path)}}, out_dir=tmp_path)
    assert calls == [("第一集。", "part1"), ("第二集很长。", "part2")]
    assert code == 3   # any paused episode marks the task paused


def test_slug_keeps_chinese_file_names():
    assert pipeline.slug_for("", "小习惯 第1期") == "小习惯-第1期"
    assert pipeline.slug_for("abc", "stdin").startswith("script-")


# ---------------------------------------------------------------- watcher
def fake_runner(results):
    """Pretend pipeline: exit code chosen by file name; writes what the real one writes."""
    def run(script, out):
        out.mkdir(parents=True, exist_ok=True)
        code = results[script.stem]
        if code == "boom":
            raise RuntimeError("worker crashed")
        if code == 3:
            (out / "questions.md").write_text("# 需要你决定")
        if code == 0:
            (out / "report.md").write_text("🔴 = 发布前必须处理（2 项）")
        return code, "Traceback ... ValueError: bad" if code == 1 else ""
    return run


def _watcher(tmp_path, results):
    inbox, output = tmp_path / "inbox", tmp_path / "output"
    inbox.mkdir()
    return Watcher(inbox, output, runner=fake_runner(results)), inbox


def test_each_task_is_isolated_and_filed_by_result(tmp_path):
    watcher, inbox = _watcher(tmp_path, {"good": 0, "long": 3, "bad": 1, "crash": "boom", "after": 0})
    for name in ("good.txt", "long.md", "bad.txt", "crash.txt", "after.txt"):
        (inbox / name).write_text("一句话。")
    assert watcher.poll() == []                       # first scan only notes the sizes
    outcomes = {o.name: o for o in watcher.poll()}
    assert {n: o.status for n, o in outcomes.items()} == {
        "good.txt": "done", "long.md": "paused", "bad.txt": "failed", "crash.txt": "failed", "after.txt": "done"}
    assert (inbox / "done/good.txt").exists() and (inbox / "done/after.txt").exists()
    assert (inbox / "paused/long.md").exists() and (inbox / "failed/bad.txt").exists()
    assert "questions.md" in outcomes["long.md"].message
    assert "2 项必须处理" in outcomes["good.txt"].message
    assert "worker crashed" in outcomes["crash.txt"].message
    status = (inbox / "STATUS.md").read_text()
    assert "⏸ 需要你决定" in status and "❌ 失败" in status
    assert len(json.loads((inbox / ".history.json").read_text())) == 5


def test_files_still_being_written_wait_for_the_next_scan(tmp_path):
    watcher, inbox = _watcher(tmp_path, {"a": 0})
    (inbox / "a.txt").write_text("一句")
    watcher.poll()
    with (inbox / "a.txt").open("a") as f:
        f.write("还在写。")
    assert watcher.poll() == []                       # size changed: not yet
    assert [o.name for o in watcher.poll()] == ["a.txt"]


def test_other_files_are_ignored(tmp_path):
    watcher, inbox = _watcher(tmp_path, {})
    for name in (".DS_Store", "photo.png", "STATUS.md", "empty.txt"):
        (inbox / name).write_text("" if name == "empty.txt" else "x")
    watcher.poll()
    assert watcher.poll() == []


def test_interrupted_task_is_requeued(tmp_path):
    watcher, inbox = _watcher(tmp_path, {"x": 0})
    (inbox / "processing/x.txt").write_text("一句话。")
    watcher.recover()
    assert (inbox / "x.txt").exists() and not (inbox / "processing/x.txt").exists()


def test_resubmitting_a_paused_script_does_not_overwrite_the_old_copy(tmp_path):
    watcher, inbox = _watcher(tmp_path, {"s": 3})
    (inbox / "paused/s.txt").write_text("旧的")
    (inbox / "s.txt").write_text("新的。")
    watcher.poll()
    watcher.poll()
    assert sorted(p.name for p in (inbox / "paused").iterdir())[0] == "s.txt"
    assert len(list((inbox / "paused").iterdir())) == 2


def test_only_one_watcher_per_inbox(tmp_path):
    with Lock(tmp_path):
        with pytest.raises(AlreadyRunning):
            with Lock(tmp_path):
                pass
    (tmp_path / ".watch.lock").write_text("999999")   # stale lock from a dead process
    with Lock(tmp_path):
        assert (tmp_path / ".watch.lock").read_text() == str(os.getpid())
    assert not (tmp_path / ".watch.lock").exists()


def test_doctor_flags_espeak_data_paths_too_long_for_espeak_ng():
    """espeak-ng keeps its data path in a fixed 160-byte buffer; longer paths silently fall back and crash."""
    from vagent.doctor import espeak_path_ok

    assert espeak_path_ok("/Users/someone/vagent/.venv/lib/python3.12/site-packages/espeakng_loader/espeak-ng-data")
    assert not espeak_path_ok("/" + "x" * 160 + "/espeak-ng-data")


def test_faster_whisper_is_a_core_dependency():
    """Every run transcribes the narration back, and CosyVoice timings come from Whisper alignment."""
    import tomllib
    from pathlib import Path

    project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert "faster-whisper" in project["dependencies"]
    assert "asr" not in project.get("optional-dependencies", {})
