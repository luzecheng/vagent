#!/usr/bin/env python3
"""Issue #7 video audit: explicit one-shot, read-only, with GitHub evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = "luzecheng/vagent"
OWNER = "luzecheng"
ISSUE = 7
MARKER = "<!-- codex-video-audit-v1 -->"
PROMPT = """Audit the existing Mia and the Lost Kite video from issue #5, READ ONLY.
Inspect repository sources and the real rendered MP4 if present in this worktree.
Investigate audio (AAC stream versus audible English narration), subtitle timing,
character and puppy action against story beats, scene changes, resolution and fps.
Distinguish verified observations from hypotheses, citing local paths and commands.
Recommend a 10-15 second quality proof before full re-render, with acceptance checks.
DO NOT edit files, install software, render, push, merge, access secrets or use paid APIs.
Output a concise plain Markdown report under 10000 characters. If an artifact or
tool is unavailable, state that limitation. Do not claim video acceptance."""

def run(argv, *, cwd=None, timeout=60):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo-path", default=str(Path.home() / "vagent-agent-worktrees/issue-5"))
    p.add_argument("--execute", action="store_true")
    args = p.parse_args()
    repo = Path(args.repo_path).expanduser().resolve()
    if not (repo / ".git").exists():
        p.error("Existing isolated issue-5 worktree is required; no changes made")
    r = run(["gh", "api", f"repos/{REPO}/issues/{ISSUE}"])
    if r.returncode:
        p.error("GitHub issue lookup failed")
    issue = json.loads(r.stdout)
    if issue.get("state") != "open" or issue.get("user", {}).get("login", "").lower() != OWNER:
        p.error("Issue author/status not authorized")
    c = run(["gh", "api", f"repos/{REPO}/issues/{ISSUE}/comments?per_page=100"])
    if c.returncode:
        p.error("Cannot check prior audit results")
    if any(MARKER in (x.get("body") or "") for x in json.loads(c.stdout)):
        p.error("Audit already reported; refusing duplicate execution")
    if not args.execute:
        print(f"DRY RUN: issue #{ISSUE}; read-only audit at {repo}")
        return
    print("Running Codex read-only video audit (up to 15 minutes)...", flush=True)
    try:
        result = run(["codex", "exec", "-s", "read-only", PROMPT], cwd=repo, timeout=900)
        status = "EXECUTED" if result.returncode == 0 else "FAILED"
        report = (result.stdout or "").strip()[-11000:]
        if not report:
            report = "No report on stdout; inspect local Codex logs. No acceptance claim."
        details = f"exit_code={result.returncode}"
    except subprocess.TimeoutExpired:
        status, details, report = "TIMEOUT", "limit=900s", "Audit timed out; no conclusions."
    body = (f"{MARKER}\n### Issue #7 read-only audit: {status}\n"
            f"- {details}\n- This is a diagnostic run, not video acceptance.\n\n"
            f"### Codex findings (unverified until independent review)\n\n{report[:11000]}\n")
    posted = run(["gh", "issue", "comment", str(ISSUE), "-R", REPO, "--body", body], timeout=60)
    if posted.returncode:
        print("Failed to post audit to GitHub; report follows:\n" + body, file=sys.stderr)
        sys.exit(2)
    print(f"Audit result posted to https://github.com/{REPO}/issues/{ISSUE}")

if __name__ == "__main__":
    main()
