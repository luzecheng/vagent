"""Inbox watcher: every .txt / .md dropped into inbox/ becomes one isolated task.

    inbox/              drop scripts here
    inbox/processing/   the task being worked on
    inbox/done/         finished (videos in output/YYYY-MM-DD_<name>/)
    inbox/paused/       needs a decision: see questions.md in its output folder
    inbox/failed/       an error; the reason is in STATUS.md and the task's run.log.jsonl
    inbox/STATUS.md     the latest tasks and where their results are

Each task runs `python -m vagent run` in its own process, so a crash or a pause
in one script never stops the others. A file is picked up only once its size
has stopped changing (an editor or a copy may still be writing it).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

from .pipeline import slug_for

SUFFIXES = {".txt", ".md"}
FOLDERS = ("processing", "done", "paused", "failed")
RESULT = {0: "done", 3: "paused"}


@dataclass
class Outcome:
    name: str
    status: str            # done | paused | failed
    output: str
    message: str
    finished: str


def run_subprocess(script: Path, out: Path) -> tuple[int, str]:
    """Run one task in a fresh process; returns (exit code, last lines of its console output)."""
    out.mkdir(parents=True, exist_ok=True)
    with (out / "console.log").open("w", encoding="utf-8") as console:
        code = subprocess.run([sys.executable, "-m", "vagent", "run", str(script), "--out", str(out)],
                              stdout=console, stderr=subprocess.STDOUT).returncode
    tail = (out / "console.log").read_text(encoding="utf-8", errors="replace").strip().splitlines()[-3:]
    return code, "\n".join(tail)


def _unique(folder: Path, name: str) -> Path:
    target = folder / name
    if target.exists():
        stem, suffix = os.path.splitext(name)
        target = folder / f"{stem}_{datetime.now():%H%M%S}{suffix}"
    return target


class Watcher:
    def __init__(self, inbox: Path, output: Path, runner=run_subprocess, log=None):
        self.inbox, self.output, self.runner, self.log = inbox, output, runner, log
        self.sizes: dict[str, tuple[int, float]] = {}
        for folder in FOLDERS:
            (inbox / folder).mkdir(parents=True, exist_ok=True)
        self.history_file = inbox / ".history.json"

    # ------------------------------------------------------------ bookkeeping
    def _event(self, message: str, **fields) -> None:
        if self.log:
            self.log.event("inbox", message, **fields)

    def _history(self) -> list[dict]:
        try:
            return json.loads(self.history_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _record(self, outcome: Outcome) -> None:
        history = ([asdict(outcome)] + self._history())[:50]
        self.history_file.write_text(json.dumps(history, ensure_ascii=False, indent=1), encoding="utf-8")
        label = {"done": "✅ 完成", "paused": "⏸ 需要你决定", "failed": "❌ 失败"}
        rows = ["# inbox 状态", "", "最新的在最上面。成片只在本地，从不自动发布。", "",
                "| 时间 | 稿件 | 结果 | 输出文件夹 | 说明 |", "|---|---|---|---|---|"]
        for h in history:
            note = h["message"].replace("\n", " ").replace("|", "/")[:120]
            rows.append(f"| {h['finished']} | {h['name']} | {label[h['status']]} | `{h['output']}` | {note} |")
        (self.inbox / "STATUS.md").write_text("\n".join(rows) + "\n", encoding="utf-8")

    # ------------------------------------------------------------ scanning
    def recover(self) -> None:
        """Tasks left in processing/ by a crash or a stopped watcher go back to the queue."""
        for path in (self.inbox / "processing").iterdir():
            if path.suffix.lower() in SUFFIXES:
                path.rename(_unique(self.inbox, path.name))
                self._event(f"requeued {path.name} (was interrupted)")

    def ready(self) -> list[Path]:
        """Script files whose size and mtime did not change since the previous scan, oldest first."""
        found = []
        current = {}
        for path in self.inbox.iterdir():
            if not path.is_file() or path.name.startswith(".") or path.suffix.lower() not in SUFFIXES:
                continue
            if path.name == "STATUS.md":
                continue
            stat = path.stat()
            current[path.name] = (stat.st_size, stat.st_mtime)
            if stat.st_size and self.sizes.get(path.name) == current[path.name]:
                found.append(path)
        self.sizes = current
        return sorted(found, key=lambda p: p.stat().st_mtime)

    # ------------------------------------------------------------ one task
    def process(self, path: Path) -> Outcome:
        out = self.output / f"{date.today().isoformat()}_{slug_for('', path.stem)}"
        working = _unique(self.inbox / "processing", path.name)
        path.rename(working)
        self._event(f"start {path.name} -> {out}")
        try:
            code, tail = self.runner(working, out)
        except Exception as exc:  # the watcher itself must survive anything one task does
            code, tail = -1, f"{type(exc).__name__}: {exc}"
        status = RESULT.get(code, "failed")
        if status == "done":
            message = "成片和 report.md 已生成"
            report = out / "report.md"
            if report.exists():
                found = re.search(r"发布前必须处理（(\d+) 项）", report.read_text(encoding="utf-8"))
                errors = int(found.group(1)) if found else 0
                message = f"请看 report.md：{errors} 项必须处理" if errors else "report.md 无必须处理的问题"
        elif status == "paused":
            questions = sorted(out.rglob("questions.md"))
            message = "见 " + ", ".join(str(q) for q in questions) if questions else "已暂停"
        else:
            message = f"退出码 {code}：{tail}"
        working.rename(_unique(self.inbox / status, path.name))
        outcome = Outcome(path.name, status, str(out), message, datetime.now().strftime("%m-%d %H:%M"))
        self._record(outcome)
        self._event(f"{status} {path.name}: {message}")
        return outcome

    def poll(self) -> list[Outcome]:
        return [self.process(path) for path in self.ready()]

    def run(self, interval: float = 5.0, once: bool = False) -> list[Outcome]:
        """`once`: scan twice (to confirm files are complete), process what is there, then exit."""
        self.recover()
        if once:
            self.ready()
            time.sleep(min(interval, 1.0))
            return self.poll()
        self._event(f"watching {self.inbox} every {interval:g}s (Ctrl+C to stop)")
        outcomes = []
        try:
            while True:
                outcomes += self.poll()
                time.sleep(interval)
        except KeyboardInterrupt:
            self._event("stopped")
        return outcomes


class AlreadyRunning(RuntimeError):
    pass


class Lock:
    """One watcher per inbox: two would pick up the same file."""

    def __init__(self, inbox: Path):
        self.path = inbox / ".watch.lock"

    def __enter__(self):
        if self.path.exists():
            try:
                pid = int(self.path.read_text())
                try:
                    os.kill(pid, 0)
                except PermissionError:  # exists, owned by someone else
                    pass
                raise AlreadyRunning(f"another watcher (pid {pid}) is already watching {self.path.parent}")
            except (ValueError, ProcessLookupError):
                pass  # stale lock from a watcher that died
        self.path.write_text(str(os.getpid()))
        return self

    def __exit__(self, *exc):
        self.path.unlink(missing_ok=True)
