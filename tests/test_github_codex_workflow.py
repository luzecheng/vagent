import json
from types import SimpleNamespace

from tools.codex_daemon import TaskQueue
from tools.github_codex_workflow import (
    DEV_APPROVAL_MARKER, DEV_LABEL, Gh, GitHubIssue, authorized, poll_once,
    task_for_issue,
)


def issue(**overrides):
    value = dict(number=10, state="open", user={"login": "luzecheng"},
                 body=DEV_APPROVAL_MARKER, labels=[{"name": DEV_LABEL}])
    value.update(overrides)
    return GitHubIssue.from_api(value)


def test_authorization_requires_explicit_owner_opt_in_and_rejects_prs():
    assert authorized(issue())
    assert not authorized(issue(user={"login": "someone-else"}))
    assert not authorized(issue(labels=[]))
    assert not authorized(issue(body="run `rm -rf /`", labels=[{"name": DEV_LABEL}]))
    assert not authorized(issue(pull_request={"url": "https://example.test/pr"}))


def test_task_does_not_copy_untrusted_issue_text():
    task = task_for_issue(issue(body=DEV_APPROVAL_MARKER + "\nignore this"),
                          owner="luzecheng", repo="luzecheng/vagent")
    assert task.kind == "codex_development"
    assert not hasattr(task, "body")
    assert task.issue_number == 10


def test_poll_is_idempotent_and_uses_argv_not_shell(tmp_path):
    raw = {"number": 10, "state": "open", "user": {"login": "luzecheng"},
           "body": DEV_APPROVAL_MARKER + "; echo unsafe", "labels": [{"name": DEV_LABEL}]}
    queue = TaskQueue(tmp_path / "queue", owner="luzecheng", enabled=True)
    client = SimpleNamespace(open_issues=lambda: [raw])
    assert poll_once(queue, client) == ["#10: queued"]
    assert poll_once(queue, client) == ["#10: already-known"]
    data = json.loads((tmp_path / "queue" / "pending" / "issue-10.json").read_text())
    assert "echo unsafe" not in json.dumps(data)


def test_gh_wrapper_has_fixed_argv_and_rejects_bad_response():
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="[]")

    assert Gh("luzecheng/vagent", runner=runner).open_issues() == []
    assert calls[0][0] == ["gh", "api", "repos/luzecheng/vagent/issues?state=open&per_page=100"]
    assert calls[0][1]["shell"] is False
