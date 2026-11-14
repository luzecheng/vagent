import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools.github_codex_review import (
    GhReviewClient, ReviewBatch, ReviewEvent, ReviewRejected, ReviewListener,
    OUTCOME_MARKER, ReviewRepairWorker, ReviewState, ReviewTarget,
)


def target():
    return ReviewTarget("luzecheng/vagent", 11, "agent/v2-issue-10", "main", ("reviewer",))


def payloads():
    pr = {"state": "open", "draft": True,
          "head": {"ref": "agent/v2-issue-10", "sha": "abc", "repo": {"full_name": "luzecheng/vagent"}},
          "base": {"ref": "main", "repo": {"full_name": "luzecheng/vagent"}}}
    reviews = [{"id": 1, "state": "CHANGES_REQUESTED", "body": "Fix it",
                "user": {"login": "reviewer"}}]
    comments = [{"id": 2, "body": "Please add a test", "path": "x.py",
                 "user": {"login": "reviewer"}}]
    return pr, reviews, comments


class FakeClient:
    def __init__(self):
        self.pr, self.review_values, self.comment_values = payloads()
        self.calls = []

    def pull_request(self, target):
        self.calls.append("pr")
        return self.pr

    def reviews(self, target):
        self.calls.append("reviews")
        return self.review_values

    def comments(self, target):
        self.calls.append("comments")
        return self.comment_values


def test_listener_is_disabled_by_default_and_persists_idempotent_cursors(tmp_path):
    client = FakeClient()
    listener = ReviewListener(target(), tmp_path / "state.json", client)
    with pytest.raises(ReviewRejected):
        listener.poll_once()

    listener.enabled = True
    batch = listener.poll_once()
    assert {event.event_id for event in batch.events} == {"1", "2"}
    assert "Please add a test" in batch.context
    assert json.loads((tmp_path / "state.json").read_text())["head_sha"] == "abc"
    assert listener.poll_once().events == ()
    listener.acknowledge(batch, success=True)
    assert client.calls.count("reviews") == 2


def test_failed_batch_is_released_for_retry(tmp_path):
    client = FakeClient()
    listener = ReviewListener(target(), tmp_path / "state.json", client, enabled=True)
    batch = listener.poll_once()
    listener.acknowledge(batch, success=False)
    retry = listener.poll_once()
    assert {event.event_id for event in retry.events} == {"1", "2"}


def test_listener_rejects_concurrent_poll(tmp_path):
    client = FakeClient()
    state_path = tmp_path / "state.json"
    lock = state_path.with_suffix(".json.lock")
    lock.mkdir()
    with pytest.raises(ReviewRejected):
        ReviewListener(target(), state_path, client, enabled=True).poll_once()
    lock.rmdir()


def test_listener_rejects_changed_pr_identity_and_head_race(tmp_path):
    client = FakeClient()
    client.pr["base"]["ref"] = "agent/v2-issue-8"
    with pytest.raises(ReviewRejected):
        ReviewListener(target(), tmp_path / "state.json", client, enabled=True).poll_once()

    client = FakeClient()
    calls = {"n": 0}
    original = client.pull_request

    def changing_pr(t):
        calls["n"] += 1
        value = original(t)
        if calls["n"] == 2:
            value = dict(value)
            value["head"] = dict(value["head"], sha="def")
        return value

    client.pull_request = changing_pr
    with pytest.raises(ReviewRejected):
        ReviewListener(target(), tmp_path / "state.json", client, enabled=True).poll_once()
    assert not (tmp_path / "state.json").exists()


def test_listener_filters_untrusted_or_non_actionable_authors(tmp_path):
    client = FakeClient()
    client.review_values = [
        {"id": 1, "state": "APPROVED", "body": "no", "user": {"login": "reviewer"}},
        {"id": 2, "state": "COMMENTED", "body": "bot", "user": {"login": "bot"}},
        {"id": 3, "state": "COMMENTED", "body": "other", "user": {"login": "other"}},
    ]
    client.comment_values = []
    listener = ReviewListener(target(), tmp_path / "state.json", client,
                              enabled=True, bot_logins=("bot",))
    assert listener.poll_once().events == ()


def test_listener_ignores_its_own_outcome_comment(tmp_path):
    client = FakeClient()
    client.review_values = []
    client.comment_values = [{"id": 9, "body": f"{OUTCOME_MARKER}\ndelivered abc",
                              "user": {"login": "reviewer"}}]
    listener = ReviewListener(target(), tmp_path / "state.json", client, enabled=True)
    assert listener.poll_once().events == ()


def test_gh_client_paginates_reviews_with_fixed_argv():
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        if "reviews?per_page=100&page=1" in argv[-1]:
            return SimpleNamespace(returncode=0, stdout=json.dumps([{"id": i} for i in range(100)]))
        return SimpleNamespace(returncode=0, stdout=json.dumps([{"id": 101}]))

    client = GhReviewClient(runner=runner)
    values = client.reviews(target())
    assert len(values) == 101
    assert calls == [
        ["gh", "api", "repos/luzecheng/vagent/pulls/11/reviews?per_page=100&page=1"],
        ["gh", "api", "repos/luzecheng/vagent/pulls/11/reviews?per_page=100&page=2"],
    ]


def test_state_load_save_is_atomic_shape(tmp_path):
    path = tmp_path / "state.json"
    state = ReviewState(processed_review_ids={"2"}, processed_comment_ids={"3"}, head_sha="abc")
    state.save(path)
    assert ReviewState.load(path) == state


def test_repair_worker_uses_isolated_head_and_pushes_only_allowlisted_branch(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()

    def git(*args, cwd=repo, check=True):
        return subprocess.run(["git", *args], cwd=cwd, check=check,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    git("init", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Review Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git("add", "--", "README.md")
    git("commit", "-m", "base")
    git("init", "--bare", str(remote), cwd=tmp_path)
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "main")
    head = git("rev-parse", "HEAD").stdout.strip()
    git("branch", "agent/v2-issue-10")
    git("push", "origin", "agent/v2-issue-10")

    def runner(argv, **kwargs):
        if argv and argv[0] == "codex":
            Path(kwargs["cwd"]).joinpath("change.txt").write_text("repair\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="codex ok")
        if argv[:3] == [sys.executable, "-m", "pytest"]:
            return SimpleNamespace(returncode=0, stdout="tests ok")
        return subprocess.run(argv, **kwargs)

    batch = ReviewBatch(target(), head, (ReviewEvent("1", "comment", "reviewer", "fix"),),
                        '{"untrusted_review_events": []}')
    result = ReviewRepairWorker(repo, tmp_path / "worktrees", runner=runner).run_once(batch)
    assert result["status"] == "delivered"
    git("fetch", "origin")
    remote_head = git("rev-parse", "refs/remotes/origin/agent/v2-issue-10").stdout.strip()
    assert remote_head != head
    assert not (tmp_path / "worktrees" / "review-11").exists()
