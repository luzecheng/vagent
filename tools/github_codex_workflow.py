"""Opt-in GitHub issue adapter for the local V2 Codex queue.

GitHub is an input source, not a command source.  This module only turns an
explicitly approved issue into queue metadata.  It never interpolates issue
titles or bodies into a shell command, and it does not post to GitHub.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable

from .codex_daemon import QueueRejected, Task, TaskQueue

DEV_APPROVAL_MARKER = "<!-- vagent-codex-dev-approved-v1 -->"
DEV_LABEL = "codex-dev"
DEFAULT_REPO = "luzecheng/vagent"
DEFAULT_OWNER = "luzecheng"


@dataclass(frozen=True)
class GitHubIssue:
    number: int
    state: str
    author: str
    body: str
    is_pull_request: bool
    labels: tuple[str, ...] = ()

    @classmethod
    def from_api(cls, value: dict[str, Any]) -> "GitHubIssue":
        user = value.get("user") or {}
        labels = tuple(str(x.get("name", "")) for x in value.get("labels", ()) if isinstance(x, dict))
        return cls(
            number=int(value["number"]),
            state=str(value.get("state", "")),
            author=str(user.get("login", "")),
            body=str(value.get("body") or ""),
            is_pull_request=bool(value.get("pull_request")),
            labels=labels,
        )


def authorized(issue: GitHubIssue, *, owner: str = DEFAULT_OWNER) -> bool:
    """Require an explicit owner approval marker and opt-in label."""
    return (
        issue.state == "open"
        and not issue.is_pull_request
        and issue.author.casefold() == owner.casefold()
        and DEV_APPROVAL_MARKER in issue.body
        and DEV_LABEL in issue.labels
    )


def task_for_issue(issue: GitHubIssue, *, owner: str, repo: str) -> Task:
    """Create queue data without copying untrusted issue text into it."""
    if not authorized(issue, owner=owner):
        raise QueueRejected("issue is not explicitly approved for Codex development")
    return Task(
        task_id=f"issue-{issue.number}",
        owner=owner,
        kind="codex_development",
        repo=repo,
        issue_number=issue.number,
    )


class Gh:
    """Small argv-only wrapper around gh; useful to replace in unit tests."""

    def __init__(self, repo: str = DEFAULT_REPO, *, runner: Callable[..., Any] = subprocess.run):
        self.repo = repo
        self.runner = runner

    def open_issues(self) -> list[dict[str, Any]]:
        result = self.runner(
            ["gh", "api", f"repos/{self.repo}/issues?state=open&per_page=100"],
            check=False, capture_output=True, text=True, timeout=45, shell=False,
        )
        if result.returncode != 0:
            raise RuntimeError("GitHub issue listing failed")
        value = json.loads(result.stdout)
        if not isinstance(value, list):
            raise RuntimeError("GitHub issue response was not a list")
        return value


def poll_once(queue: TaskQueue, client: Gh, *, owner: str = DEFAULT_OWNER,
              repo: str = DEFAULT_REPO) -> list[str]:
    """Enqueue approved issues; return stable per-issue outcomes."""
    outcomes: list[str] = []
    for raw in client.open_issues():
        issue = GitHubIssue.from_api(raw)
        if not authorized(issue, owner=owner):
            continue
        try:
            added = queue.enqueue(task_for_issue(issue, owner=owner, repo=repo))
            outcomes.append(f"#{issue.number}: {'queued' if added else 'already-known'}")
        except QueueRejected:
            outcomes.append(f"#{issue.number}: rejected")
    return outcomes


def main(argv: Iterable[str] | None = None) -> int:
    """Poll once only when the caller supplies the explicit opt-in flag."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable", action="store_true", help="explicitly enable GitHub polling")
    parser.add_argument("--queue-root", type=Path, required=True)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    args = parser.parse_args(argv)
    if not args.enable:
        parser.error("GitHub-to-Codex workflow is disabled; pass --enable")
    queue = TaskQueue(args.queue_root, owner=args.owner, enabled=True)
    for outcome in poll_once(queue, Gh(args.repo), owner=args.owner, repo=args.repo):
        print(outcome)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
