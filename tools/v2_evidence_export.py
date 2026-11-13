#!/usr/bin/env python3
"""Publish bounded, metadata-only evidence from local V2 runs to GitHub.

No raw Codex logs, media, file contents, credentials or diffs are uploaded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = "luzecheng/vagent"
MARKER = "<!-- vagent-evidence-v1 -->"
ISSUES = (7, 8)

def run(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--issue", type=int, choices=ISSUES, required=True)
    parser.add_argument("--repo-path", default=str(Path.home() / "vagent"))
    parser.add_argument("--worktree-base", default=str(Path.home() / "vagent-agent-worktrees"))
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    state = Path.home() / ".local/state/vagent-v2"
    log = state / f"issue-{args.issue}.log"
    worktree = Path(args.worktree_base).expanduser() / f"issue-{8 if args.issue == 8 else 5}"
    if not log.is_file():
        parser.error("No local execution log; refusing to fabricate evidence")
    if not worktree.is_dir():
        parser.error("Worktree missing")

    status = run(["git", "-C", str(worktree), "status", "--porcelain=v1", "-uno"])
    if status.returncode:
        parser.error("Cannot inspect worktree")
    # Count changed tracked files; do not publish filenames or file content.
    changed = len([x for x in status.stdout.splitlines() if x.strip()])
    commits = run(["git", "-C", str(worktree), "log", "-1", "--format=%h"])
    if commits.returncode:
        parser.error("Cannot read HEAD")
    # Git commit IDs are not secret. A count is safer than publishing arbitrary paths.
    data = {
        "issue": args.issue,
        "log_bytes": log.stat().st_size,
        "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
        "tracked_changes_count": changed,
        "git_head_short": commits.stdout.strip(),
        "video_accepted": False,
        "report_scope": "metadata-only; no content review",
    }
    print(json.dumps(data, indent=2))
    if not args.publish:
        print("DRY RUN; no GitHub changes")
        return
    check = run(["gh", "api", f"repos/{REPO}/issues/{args.issue}/comments?per_page=100"])
    if check.returncode:
        parser.error("Cannot verify prior evidence comment")
    if any(MARKER in (x.get("body") or "") for x in json.loads(check.stdout)):
        parser.error("Evidence already posted; duplicate refused")
    body = f"{MARKER}\n### Local V2 evidence metadata\n\n```json\n{json.dumps(data, indent=2)}\n```\n\nNo artifact acceptance is implied."
    result = run(["gh", "issue", "comment", str(args.issue), "-R", REPO, "--body", body], timeout=60)
    if result.returncode:
        parser.error("GitHub comment failed")
    print(f"Published metadata to https://github.com/{REPO}/issues/{args.issue}")

if __name__ == "__main__":
    main()
