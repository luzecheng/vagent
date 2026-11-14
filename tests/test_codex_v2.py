import pytest
from pathlib import Path
from types import SimpleNamespace

from tools.codex_daemon import QueueRejected, Task, TaskQueue
from tools import codex_dev_worker
from tools.codex_dev_worker import Acceptance, Execution, Worker, accept_artifacts, command_for_task, redact, status_record


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


def test_codex_command_is_fixed_and_contains_only_issue_number():
    command = command_for_task(task(kind="codex_development", issue_number=10))
    assert command[:6] == ["codex", "exec", "--sandbox", "workspace-write", "--ask-for-approval", "never"]
    assert command[-1].endswith("Issue number: 10.")
    assert "ignore; rm -rf /" not in " ".join(command)


class FakeDelivery:
    def __init__(self, tmp_path, *, fail_at=None):
        self.tmp_path = tmp_path
        self.fail_at = fail_at
        self.calls = []

    def create_worktree(self, worktree, branch):
        self.calls.append(("worktree", branch))
        worktree.mkdir(parents=True, exist_ok=True)

    def changed_paths(self, worktree):
        return ("src/change.py",)

    def inspect_state(self, worktree, branch):
        return codex_dev_worker.DeliveryState.PUSHED_AWAITING_PR

    def validate_tests(self, worktree, timeout):
        self.calls.append("validate")
        if self.fail_at == "validate":
            raise codex_dev_worker.DeliveryError("tests failed")

    def commit_push(self, worktree, branch, message):
        self.calls.append(("push", branch))
        if self.fail_at == "push":
            raise codex_dev_worker.DeliveryError("push failed", stage="push")

    def create_draft_pr(self, *, repo, branch, issue_number):
        self.calls.append(("pr", repo, branch, issue_number))
        if self.fail_at == "pr":
            raise codex_dev_worker.DeliveryError("pr failed", stage="pr_creation")
        return "https://github.example/draft/1"

    def push_existing(self, worktree, branch):
        self.calls.append(("retry-push", branch))
        if self.fail_at == "push":
            raise codex_dev_worker.DeliveryError("push failed")

    def remove_worktree(self, worktree):
        self.calls.append("remove")
        if self.fail_at == "cleanup":
            raise codex_dev_worker.DeliveryError("cleanup failed", stage="cleanup")
        worktree.rmdir()


def run_codex_worker(tmp_path, monkeypatch, delivery):
    queue = TaskQueue(tmp_path / "queue", owner="alice", enabled=True)
    item = task(task_id="issue-10", owner="alice", kind="codex_development",
                repo="luzecheng/vagent", issue_number=10)
    assert queue.enqueue(item)
    monkeypatch.setattr(codex_dev_worker.subprocess, "run",
                        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok"))
    worker = Worker(queue, tmp_path / "repo", tmp_path / "worktrees",
                    timeout_seconds=30, delivery=delivery)
    return queue, worker, worker.run_once("issue-10")


def test_delivery_success_commits_pushes_draft_pr_then_removes_worktree(tmp_path, monkeypatch):
    delivery = FakeDelivery(tmp_path)
    queue, worker, result = run_codex_worker(tmp_path, monkeypatch, delivery)
    assert result["execution"] == "passed"
    assert (delivery.calls[0][0], delivery.calls[1], delivery.calls[2][0], delivery.calls[-1]) == (
        "worktree", "validate", "push", "remove")
    assert (queue.root / "completed" / "issue-10.json").exists()
    assert not (tmp_path / "worktrees" / "issue-10").exists()


@pytest.mark.parametrize("failure", ["validate", "push", "pr", "cleanup"])
def test_delivery_failure_retains_worktree_and_failed_state(tmp_path, monkeypatch, failure):
    delivery = FakeDelivery(tmp_path, fail_at=failure)
    queue, worker, result = run_codex_worker(tmp_path, monkeypatch, delivery)
    assert result["execution"] == "failed"
    assert (queue.root / "failed" / "issue-10.json").exists()
    assert (tmp_path / "worktrees" / "issue-10").exists()
    if failure != "cleanup":
        assert "remove" not in delivery.calls


def test_failed_delivery_can_be_requeued_and_recovered_without_losing_worktree(tmp_path, monkeypatch):
    delivery = FakeDelivery(tmp_path, fail_at="push")
    queue, worker, _ = run_codex_worker(tmp_path, monkeypatch, delivery)
    assert queue.requeue_failed("issue-10")
    delivery.fail_at = None
    result = worker.run_once("issue-10")
    assert result["execution"] == "passed"
    assert (queue.root / "completed" / "issue-10.json").exists()
    assert "remove" in delivery.calls


def test_duplicate_execution_is_not_claimed_twice(tmp_path, monkeypatch):
    delivery = FakeDelivery(tmp_path)
    queue, worker, _ = run_codex_worker(tmp_path, monkeypatch, delivery)
    assert worker.run_once("issue-10") is None
    assert delivery.calls.count("remove") == 1


def test_retry_delivery_reuses_retained_commit_without_rerunning_codex(tmp_path, monkeypatch):
    delivery = FakeDelivery(tmp_path, fail_at="pr")
    queue, worker, _ = run_codex_worker(tmp_path, monkeypatch, delivery)
    delivery.fail_at = None
    result = worker.retry_delivery("issue-10")
    assert result["execution"] == "recovered"
    assert [x[0] for x in delivery.calls if isinstance(x, tuple)].count("push") == 1
    assert (queue.root / "completed" / "issue-10.json").exists()


def test_retry_does_not_bypass_validation_failure(tmp_path, monkeypatch):
    delivery = FakeDelivery(tmp_path, fail_at="validate")
    queue, worker, _ = run_codex_worker(tmp_path, monkeypatch, delivery)
    result = worker.retry_delivery("issue-10")
    assert result["recovery"].startswith("not-retryable")
    assert (queue.root / "failed" / "issue-10.json").exists()
    assert "pr" not in [x[0] for x in delivery.calls if isinstance(x, tuple)]
