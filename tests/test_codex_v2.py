import pytest
from pathlib import Path

from tools.codex_daemon import QueueRejected, Task, TaskQueue
from tools.codex_dev_worker import Acceptance, Execution, accept_artifacts, redact, status_record


def task(**overrides):
    values = dict(task_id="one", owner="alice", kind="unit_tests", repo="repo")
    values.update(overrides)
    return Task(**values)


def test_queue_is_opt_in_owner_only_and_idempotent(tmp_path):
    queue = TaskQueue(tmp_path / "queue", owner="alice")
    with pytest.raises(QueueRejected):
        queue.enqueue(task())
    queue.enabled = True
    assert queue.enqueue(task()) is True
    assert queue.enqueue(task()) is False
    with pytest.raises(QueueRejected):
        queue.enqueue(task(task_id="two", owner="mallory"))
    claimed = queue.claim("one")
    assert claimed == task()
    assert queue.claim("one") is None
    queue.finish("one", success=True, result={"execution": "passed"})
    assert queue.claim("one") is None


def test_queue_rejects_unknown_kind_and_escape_artifacts(tmp_path):
    queue = TaskQueue(tmp_path / "queue", owner="alice", enabled=True)
    with pytest.raises(QueueRejected):
        queue.enqueue(task(kind="run_command"))
    with pytest.raises(QueueRejected):
        queue.enqueue(task(expected_artifacts=("../secret",)))


def test_acceptance_is_distinct_and_status_has_no_log_or_issue_text():
    worktree = Path("/tmp")
    assert accept_artifacts(worktree, ("definitely-not-here",)).status == "rejected"
    execution = Execution("passed", 0, 0.2, "/private/log")
    acceptance = Acceptance("accepted")
    status = status_record(task(issue_number=8), execution, acceptance)
    assert status == {"task_id": "one", "issue_number": 8, "execution": "passed",
                      "artifact_acceptance": "accepted", "missing_artifacts": [], "duration_seconds": 0.2}
    assert "secret=[REDACTED]" in redact("secret=abc")
    assert "Bearer [REDACTED]" in redact("Bearer abc")
