#!/usr/bin/env python3
"""Safe, read-only local delivery inventory for issue #8.

Publishes only allowlisted source file paths and Git status metadata.
No source code, logs, environment values, tokens, or media uploaded.
"""
import argparse
import json
from pathlib import Path
import subprocess

REPO = "luzecheng/vagent"
MARKER = "<!-- vagent-v2-delivery-inventory-v1 -->"
ALLOW = ("tools/", "tests/", "docs/")

def run(args, timeout=40):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--worktree", default=str(Path.home() / "vagent-agent-worktrees/issue-8"))
    p.add_argument("--publish", action="store_true")
    a = p.parse_args()
    wt = Path(a.worktree).expanduser().resolve()
    if not (wt / ".git").exists():
        p.error("Expected isolated issue-8 worktree")
    r = run(["git", "-C", str(wt), "status", "--porcelain=v1", "--untracked-files=all"])
    if r.returncode:
        p.error("Cannot inspect git status")
    lines = r.stdout.splitlines()
    candidates = []
    excluded = 0
    for line in lines:
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if (path.startswith(ALLOW) and ".." not in Path(path).parts
                and Path(path).suffix in (".py", ".md", ".toml", ".json", ".yaml", ".yml")
                and not any(s in path.lower() for s in ("secret", "token", "credential", ".env", "private"))):
            candidates.append({"git_status": line[:2], "path": path})
        else:
            excluded += 1
    head = run(["git", "-C", str(wt), "log", "-1", "--format=%h"])
    data = {"issue": 8, "head": head.stdout.strip(), "allowlisted_changed_files": candidates[:100],
            "excluded_entries": excluded, "truncated": len(candidates) > 100,
            "code_reviewed": False, "tests_verified": False}
    print(json.dumps(data, indent=2))
    if not a.publish:
        print("DRY RUN; nothing uploaded")
        return
    prior = run(["gh", "api", f"repos/{REPO}/issues/8/comments?per_page=100"])
    if prior.returncode:
        p.error("Cannot check prior report")
    if any(MARKER in (x.get("body") or "") for x in json.loads(prior.stdout)):
        p.error("Report already posted")
    body = f"{MARKER}\n### Issue #8 local delivery inventory\n\n```json\n{json.dumps(data, indent=2)}\n```\n\nThis is metadata, not a PR or code review."
    posted = run(["gh", "issue", "comment", "8", "-R", REPO, "--body", body], timeout=60)
    if posted.returncode:
        p.error("Could not post GitHub comment")
    print("Published to https://github.com/luzecheng/vagent/issues/8")

if __name__ == "__main__":
    main()
