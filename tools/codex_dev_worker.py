"""Bounded, isolated worker for the V2 task queue.

Only ``unit_tests`` is implemented.  The command is assembled here, never
from an issue, title, body, or queue payload.  GitHub reporting is represented
by safe status records and an injected callback; this prototype performs no
network calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import subprocess
import sys
import time
from typing import Callable

from .codex_daemon import Task, TaskQueue

MAX_RUNTIME_SECONDS = 15 * 60
CLEANUP_TIMEOUT_SECONDS = 5
_SECRET = re.compile(r"(?i)(token|secret|password|authorization|api[-_ ]?key)\s*[:=]\s*[^\s,;]+")
_BEARER = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+")


@dataclass(frozen=True)
class Execution:
    status: str
    returncode: int | None
    duration_seconds: float
    log_path: str


@dataclass(frozen=True)
class Acceptance:
    status: str
    missing: tuple[str, ...] = ()


def redact(value: str) -> str:
    """Remove common credentials and keep status messages short/local-safe."""
    value = _SECRET.sub(lambda m: m.group(1) + "=[REDACTED]", value)
    value = _BEARER.sub("Bearer [REDACTED]", value)
    return value[:500]


def status_record(task: Task, execution: Execution, acceptance: Acceptance) -> dict[str, object]:
    """Return the only shape a GitHub status adapter should publish."""
    return {
        "task_id": task.task_id,
        "issue_number": task.issue_number,
        "execution": execution.status,
        "artifact_acceptance": acceptance.status,
        "missing_artifacts": list(acceptance.missing),
        "duration_seconds": execution.duration_seconds,
    }


class Worker:
    def __init__(self, queue: TaskQueue, repo_root: Path, worktree_root: Path,
                 *, timeout_seconds: int = 300, reporter: Callable[[dict[str, object]], None] | None = None):
        if timeout_seconds < 1 or timeout_seconds > MAX_RUNTIME_SECONDS:
            raise ValueError(f"timeout must be between 1 and {MAX_RUNTIME_SECONDS} seconds")
        self.queue, self.repo_root = queue, Path(repo_root).resolve()
        self.worktree_root = Path(worktree_root).resolve()
        self.timeout_seconds, self.reporter = timeout_seconds, reporter

    def run_once(self, task_id: str) -> dict[str, object] | None:
        task = self.queue.claim(task_id)
        if task is None:
            return None
        worktree = self.worktree_root / task.task_id
        worktree.parent.mkdir(parents=True, exist_ok=True)
        log_path = self.queue.root / "logs" / f"{task.task_id}.jsonl"
        log_path.parent.mkdir(exist_ok=True)
        started = time.monotonic()
        deadline = started + self.timeout_seconds
        execution = Execution("failed", None, 0.0, str(log_path))
        acceptance = Acceptance("not_run")
        try:
            self._event(log_path, "worktree_create")
            subprocess.run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"],
                           cwd=self.repo_root, check=True, timeout=self._remaining(deadline),
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            self._event(log_path, "execution_start", command="python -m pytest -q")
            try:
                completed = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=worktree,
                                           check=False, timeout=self._remaining(deadline),
                                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                self._event(log_path, "execution_output", output=completed.stdout)
                execution = Execution("passed" if completed.returncode == 0 else "failed",
                                      completed.returncode, time.monotonic() - started, str(log_path))
            except subprocess.TimeoutExpired:
                execution = Execution("timed_out", None, time.monotonic() - started, str(log_path))
            acceptance = accept_artifacts(worktree, task.expected_artifacts) if execution.status == "passed" else Acceptance("not_run")
            success = execution.status == "passed" and acceptance.status == "accepted"
            result = status_record(task, execution, acceptance)
            self.queue.finish(task.task_id, success=success, result=result)
            if self.reporter:
                self.reporter(result)
            return result
        except Exception as exc:
            execution = Execution("failed", None, time.monotonic() - started, str(log_path))
            result = status_record(task, execution, acceptance)
            result["error"] = redact(f"{type(exc).__name__}: {exc}")
            self._event(log_path, "worker_error", error=result["error"])
            self.queue.finish(task.task_id, success=False, result=result)
            if self.reporter:
                self.reporter(result)
            return result
        finally:
            if worktree.exists():
                subprocess.run(["git", "worktree", "remove", "--force", str(worktree)],
                               cwd=self.repo_root, check=False, timeout=CLEANUP_TIMEOUT_SECONDS,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("codex-v2 task", 0)
        return remaining

    @staticmethod
    def _event(path: Path, event: str, **fields: object) -> None:
        record = {"time": time.time(), "event": event, **{k: redact(str(v)) for k, v in fields.items()}}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def accept_artifacts(worktree: Path, expected: tuple[str, ...]) -> Acceptance:
    """Acceptance is a separate, read-only gate after execution succeeds."""
    root = worktree.resolve()
    missing = tuple(p for p in expected
                    if not (root / p).resolve().is_relative_to(root)
                    or not (root / p).is_file())
    return Acceptance("accepted" if not missing else "rejected", missing)
