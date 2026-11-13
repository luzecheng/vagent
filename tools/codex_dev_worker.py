#!/usr/bin/env python3
"""One-shot, explicitly approved development task runner. No unattended execution."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

REPO = "luzecheng/vagent"
OWNER = "luzecheng"
RESULT = "<!-- codex-dev-worker-result-v1 -->"

def call(argv, *, cwd=None, timeout=30):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)

def gh_json(path):
    r = call(["gh", "api", path])
    if r.returncode:
        raise RuntimeError("GitHub API request failed")
    return json.loads(r.stdout)

def validate(issue, number):
    return (issue.get("number") == number and issue.get("state") == "open"
            and issue.get("user", {}).get("login", "").lower() == OWNER
            and "pull_request" not in issue)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--repo-path", default=str(Path.home() / "vagent"))
    p.add_argument("--worktree-base", default=str(Path.home() / "vagent-agent-worktrees"))
    p.add_argument("--execute", action="store_true", help="Explicitly authorize a single development run")
    a = p.parse_args()
    if a.issue != 5:
        p.error("V1 is restricted to approved video issue #5")
    issue = gh_json(f"repos/{REPO}/issues/{a.issue}")
    if not validate(issue, a.issue):
        p.error("Issue author or status invalid")
    root = Path(a.repo_path).expanduser().resolve()
    if not (root / ".git").exists():
        p.error("Expected a Git checkout")
    base = Path(a.worktree_base).expanduser().resolve()
    worktree = base / f"issue-{a.issue}"
    if not a.execute:
        print(f"DRY RUN: issue #{a.issue} authorized; isolated worktree target {worktree}")
        return
    base.mkdir(parents=True, exist_ok=True)
    if worktree.exists():
        p.error("Worktree target already exists; refusing to reuse it")
    branch = f"agent/video-issue-{a.issue}"
    create = call(["git", "-C", str(root), "worktree", "add", "-b", branch, str(worktree), "HEAD"], timeout=60)
    if create.returncode:
        raise RuntimeError("Could not create isolated worktree: " + create.stderr[-500:])
    prompt = (
        "You are implementing GitHub issue #5 in this isolated repository worktree. "
        "Build a real playable 60-120 second English children's animated story video "
        "'Mia and the Lost Kite'. The girl, puppy, kite and tree must actually animate; "
        "a slideshow with Ken Burns effects does not satisfy the task. Use existing local "
        "tools and no paid APIs. Do not read secrets, deploy, push, merge or modify "
        "other worktrees. Inspect repository first, implement and run tests, render a "
        "small animation proof before attempting full video. If rendering cannot finish, "
        "report precisely what is done and what blocks completion. Provide reproducible "
        "commands, video path, ffprobe specs and validation evidence. "
        "Do not claim a video exists without verifying it."
    )
    result = None
    try:
        result = call(["codex", "exec", "-s", "workspace-write", prompt], cwd=worktree, timeout=3600)
        status = "PASS" if result.returncode == 0 else "FAIL"
        details = f"exit_code={result.returncode}"
    except subprocess.TimeoutExpired:
        status, details = "TIMEOUT", "limit=3600s"
    body = (f"{RESULT}\n### Development Codex run: {status}\n"
            f"- Issue: #{a.issue}\n- Worktree: {worktree}\n- {details}\n"
            "- Raw agent logs not uploaded. Video artifact must be verified locally.\n")
    posted = call(["gh", "issue", "comment", str(a.issue), "-R", REPO, "--body", body], timeout=45)
    if posted.returncode:
        raise RuntimeError("Could not post status to GitHub")
    print(body)

if __name__ == "__main__":
    main()
