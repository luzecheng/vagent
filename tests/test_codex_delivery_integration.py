import json
import subprocess
from types import SimpleNamespace

import pytest

from tools.codex_dev_worker import DeliveryError, DeliveryState, GitDelivery


def git(cwd, *args, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check,
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True)


def repository(tmp_path):
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "test@example.invalid")
    git(repo, "config", "user.name", "Delivery Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    git(repo, "add", "--", "README.md")
    git(repo, "commit", "-m", "base")
    git(tmp_path, "init", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "--set-upstream", "origin", "main")
    return repo, remote


class GhMock:
    def __init__(self):
        self.existing = []
        self.created = 0

    def __call__(self, argv, **kwargs):
        if argv[:3] == ["gh", "pr", "list"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.existing))
        if argv[:3] == ["gh", "pr", "create"]:
            self.created += 1
            return SimpleNamespace(returncode=0, stdout="https://github.invalid/pr/11\n")
        return subprocess.run(argv, **kwargs)


def test_real_worktree_commit_push_and_remote_state(tmp_path):
    repo, _ = repository(tmp_path)
    delivery = GitDelivery(repo)
    worktree = tmp_path / "worktree"
    branch = "codex/issue-10"

    delivery.create_worktree(worktree, branch)
    assert git(worktree, "symbolic-ref", "--short", "HEAD").stdout.strip() == branch
    (worktree / "change.txt").write_text("change\n", encoding="utf-8")
    assert delivery.inspect_state(worktree, branch) == DeliveryState.UNCOMMITTED

    delivery.commit_push(worktree, branch, "Issue #10: implement approved change")
    assert delivery.inspect_state(worktree, branch) == DeliveryState.PUSHED_AWAITING_PR
    assert git(repo, "show-ref", "--verify", f"refs/remotes/origin/{branch}").returncode == 0
    assert git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip() == "main"


def test_rename_status_records_are_staged_without_losing_old_path(tmp_path):
    repo, _ = repository(tmp_path)
    delivery = GitDelivery(repo)
    worktree = tmp_path / "worktree"
    branch = "codex/issue-rename"
    delivery.create_worktree(worktree, branch)
    git(worktree, "mv", "README.md", "renamed.md")
    assert set(delivery.changed_paths(worktree)) == {"README.md", "renamed.md"}
    delivery.commit_push(worktree, branch, "rename test")
    assert git(worktree, "show", "--format=", "--name-status", "HEAD").stdout.startswith("R")


def test_remote_base_commit_is_not_classified_as_deliverable(tmp_path):
    repo, _ = repository(tmp_path)
    delivery = GitDelivery(repo)
    worktree = tmp_path / "worktree"
    branch = "codex/issue-no-change"
    delivery.create_worktree(worktree, branch)
    git(worktree, "push", "origin", f"HEAD:refs/heads/{branch}")
    assert delivery.inspect_state(worktree, branch) == DeliveryState.NO_CHANGE


def test_push_failure_preserves_commit_and_recovers_without_recommit(tmp_path):
    repo, _ = repository(tmp_path)
    failed = {"value": True}

    def runner(argv, **kwargs):
        if argv[:2] == ["git", "push"] and failed["value"]:
            failed["value"] = False
            return SimpleNamespace(returncode=1, stdout="remote unavailable")
        return subprocess.run(argv, **kwargs)

    delivery = GitDelivery(repo, runner=runner)
    worktree = tmp_path / "worktree"
    branch = "codex/issue-11"
    delivery.create_worktree(worktree, branch)
    (worktree / "change.txt").write_text("change\n", encoding="utf-8")
    with pytest.raises(DeliveryError) as error:
        delivery.commit_push(worktree, branch, "Issue #11: implement approved change")
    assert error.value.stage == "push"
    assert delivery.inspect_state(worktree, branch) == DeliveryState.COMMITTED_UNPUSHED

    delivery.push_existing(worktree, branch)
    assert delivery.inspect_state(worktree, branch) == DeliveryState.PUSHED_AWAITING_PR
    assert len(list(worktree.glob("change.txt"))) == 1


def test_staging_blocks_sensitive_paths_and_credential_content(tmp_path):
    repo, _ = repository(tmp_path)
    delivery = GitDelivery(repo)
    worktree = tmp_path / "worktree"
    branch = "codex/issue-12"
    delivery.create_worktree(worktree, branch)

    (worktree / ".env.local").write_text("TOKEN=not-for-commit\n", encoding="utf-8")
    with pytest.raises(DeliveryError):
        delivery.commit_push(worktree, branch, "unsafe")
    assert git(worktree, "rev-list", "--count", "main..HEAD").stdout.strip() == "0"

    (worktree / ".env.local").unlink()
    (worktree / "config.txt").write_text("api_key: abc123\n", encoding="utf-8")
    with pytest.raises(DeliveryError):
        delivery.commit_push(worktree, branch, "unsafe content")
    assert git(worktree, "rev-list", "--count", "main..HEAD").stdout.strip() == "0"


def test_pr_lookup_is_idempotent_and_does_not_create_duplicate(tmp_path):
    repo, _ = repository(tmp_path)
    gh = GhMock()
    delivery = GitDelivery(repo, runner=gh)
    first = delivery.create_draft_pr(repo="luzecheng/vagent", branch="codex/issue-13", issue_number=13)
    assert first.endswith("/11")
    assert gh.created == 1

    gh.existing = [{"url": first, "isDraft": True}]
    second = delivery.create_draft_pr(repo="luzecheng/vagent", branch="codex/issue-13", issue_number=13)
    assert second == first
    assert gh.created == 1
