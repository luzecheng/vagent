"""Opt-in, owner-only task queue for the V2 prototype.

This module deliberately does not talk to GitHub or execute task text.  A task
is a small JSON document accepted only when the daemon is explicitly enabled,
the owner matches exactly, and its kind is in ``ALLOWED_TASK_KINDS``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import time
from typing import Any

ALLOWED_TASK_KINDS = frozenset({"unit_tests", "codex_development"})
TASK_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class QueueRejected(ValueError):
    """The task did not pass the V2 admission policy."""


@dataclass(frozen=True)
class Task:
    task_id: str
    owner: str
    kind: str
    repo: str
    issue_number: int | None = None
    expected_artifacts: tuple[str, ...] = ()


class TaskQueue:
    """Filesystem queue with atomic state transitions and per-task locks."""

    states = ("pending", "running", "completed", "failed")

    def __init__(self, root: Path, *, owner: str, enabled: bool = False):
        self.root = Path(root)
        self.owner = owner
        self.enabled = enabled
        for state in self.states:
            (self.root / state).mkdir(parents=True, exist_ok=True)
        (self.root / "locks").mkdir(exist_ok=True)

    def _path(self, state: str, task_id: str) -> Path:
        return self.root / state / f"{task_id}.json"

    def _lock(self, task_id: str) -> Path:
        return self.root / "locks" / f"{task_id}.lock"

    def _validate(self, task: Task) -> None:
        if not self.enabled:
            raise QueueRejected("V2 queue is disabled; pass the explicit opt-in")
        if task.owner != self.owner:
            raise QueueRejected("task owner is not allowlisted")
        if not TASK_ID.fullmatch(task.task_id):
            raise QueueRejected("invalid task id")
        if task.kind not in ALLOWED_TASK_KINDS:
            raise QueueRejected("task kind is not allowlisted")
        if not task.repo or Path(task.repo).name in {".", ".."}:
            raise QueueRejected("repo is required")
        if any(Path(p).is_absolute() or ".." in Path(p).parts for p in task.expected_artifacts):
            raise QueueRejected("artifact paths must be relative")

    def enqueue(self, task: Task) -> bool:
        """Add a task once. Return False for an already-known task id."""
        self._validate(task)
        lock = self._lock(task.task_id)
        try:
            lock.mkdir()
        except FileExistsError:
            return False
        try:
            if any(self._path(s, task.task_id).exists() for s in self.states):
                return False
            temp = self._path("pending", f".{task.task_id}.{os.getpid()}.tmp")
            temp.write_text(json.dumps(asdict(task), sort_keys=True), encoding="utf-8")
            temp.replace(self._path("pending", task.task_id))
            return True
        finally:
            lock.rmdir()

    def claim(self, task_id: str) -> Task | None:
        """Atomically claim pending work; completed work is never re-run."""
        lock = self._lock(task_id)
        try:
            lock.mkdir()
        except FileExistsError:
            return None
        try:
            source = self._path("pending", task_id)
            target = self._path("running", task_id)
            if not source.exists() or target.exists() or self._path("completed", task_id).exists():
                return None
            source.replace(target)
            return self._read(target)
        finally:
            lock.rmdir()

    def finish(self, task_id: str, *, success: bool, result: dict[str, Any]) -> None:
        source = self._path("running", task_id)
        target = self._path("completed" if success else "failed", task_id)
        if not source.exists():
            raise QueueRejected("task is not running")
        data = json.loads(source.read_text(encoding="utf-8"))
        data["result"] = result
        data["finished_at"] = int(time.time())
        temp = target.with_suffix(f".{os.getpid()}.tmp")
        temp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        temp.replace(target)
        source.unlink()

    @staticmethod
    def _read(path: Path) -> Task:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Task(**{k: tuple(v) if k == "expected_artifacts" else v for k, v in data.items() if k in Task.__dataclass_fields__})
