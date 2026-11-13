#!/usr/bin/env python3
"""V2 opt-in GitHub issue executor: bounded one-shot runs, explicit allowlist."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

REPO = "luzecheng/vagent"
OWNER = "luzecheng"
MARKER = "<!-- vagent-v2-execution-result-v1 -->"
STATE = Path.home() / ".local/state/vagent-v2"
TASKS = {
    7: {"mode": "read-only", "repo": "issue5", "timeout": 900},
    8: {"mode": "workspace-write", "repo": "new-worktree", "timeout": 1800},
}

def cmd(argv, cwd=None, timeout=60):
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, timeout=timeout)

def api(path):
    r = cmd(["gh", "api", path])
    if r.returncode:
        raise RuntimeError("GitHub request failed")
    return json.loads(r.stdout)

def verify_issue(n):
    issue = api(f"repos/{REPO}/issues/{n}")
    if issue.get("number") != n or issue.get("state") != "open" or "pull_request" in issue:
        raise RuntimeError("Issue is not eligible")
    if issue.get("user", {}).get("login", "").lower() != OWNER:
        raise RuntimeError("Issue author is not authorized")
    return issue

def already_reported(n):
    page = 1
    while True:
        comments = api(f"repos/{REPO}/issues/{n}/comments?per_page=100&page={page}")
        if any(MARKER in (x.get("body") or "") for x in comments):
            return True
        if len(comments) < 100:
            return False
        page += 1

def prompt(n):
    if n == 7:
        return ("Read-only audit of issue #5 Mia and the Lost Kite output. "
                "Inspect actual source and MP4 if available. Diagnose audio narration, "
                "subtitle sync, character actions, scene continuity, 1920x1080 gap. "
                "Provide evidence, exact paths, 10-15s quality proof proposal and "
                "acceptance criteria. Do not modify anything, install, push or deploy.")
    return ("Implement GitHub issue #8 in this isolated worktree, as a narrow "
            "tested V2 prototype only. Review tools/codex_daemon.py and "
            "tools/codex_dev_worker.py. Build opt-in owner-only allowlisted "
            "task queue, per-task locking/idempotence, isolated worktrees, "
            "bounded runtime, local progress logs, safe redacted GitHub status "
            "and distinct execution vs artifact acceptance. Do not install "
            "launchd services, push, merge, deploy, touch other worktrees, "
            "read secrets or run arbitrary commands from issue text. "
            "Run unit tests and report file paths and limitations.")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--issue", type=int, choices=sorted(TASKS), required=True)
    p.add_argument("--repo-path", default=str(Path.home() / "vagent"))
    p.add_argument("--worktree-base", default=str(Path.home() / "vagent-agent-worktrees"))
    p.add_argument("--execute", action="store_true")
    a = p.parse_args()
    task = TASKS[a.issue]
    issue = verify_issue(a.issue)
    if already_reported(a.issue):
        p.error("Task already reported; duplicate execution refused")
    root = Path(a.repo_path).expanduser().resolve()
    if not (root / ".git").exists():
        p.error("Repo checkout not found")
    base = Path(a.worktree_base).expanduser().resolve()
    target = base / ("issue-5" if task["repo"] == "issue5" else f"issue-{a.issue}")
    if task["repo"] == "issue5" and not (target / ".git").exists():
        p.error("Existing issue-5 worktree not found")
    if task["repo"] == "new-worktree" and target.exists():
        p.error("Target worktree exists; refusing overwrite")
    if not a.execute:
        print(f"DRY RUN: #{a.issue} mode={task['mode']} target={target}")
        return
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    claim = STATE / f"issue-{a.issue}.claimed"
    try:
        fd = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        p.error("Task already claimed; no duplicate execution")
    with os.fdopen(fd, "w") as f:
        f.write(json.dumps({"issue": a.issue, "time": time.time()}))
    if task["repo"] == "new-worktree":
        base.mkdir(parents=True, exist_ok=True)
        branch = f"agent/v2-issue-{a.issue}"
        r = cmd(["git", "-C", str(root), "worktree", "add", "-b", branch,
                 str(target), "HEAD"], timeout=90)
        if r.returncode:
            print("Could not create worktree; claim retained", file=sys.stderr)
            sys.exit(2)
    log = STATE / f"issue-{a.issue}.log"
    print(f"Starting issue #{a.issue}; local log: {log}", flush=True)
    try:
        with open(log, "w", encoding="utf-8") as out:
            result = subprocess.run(["codex", "exec", "-s", task["mode"], prompt(a.issue)],
                                    cwd=target, stdout=out, stderr=subprocess.STDOUT,
                                    timeout=task["timeout"])
        code = result.returncode
        status = "EXECUTED" if code == 0 else "FAILED"
    except subprocess.TimeoutExpired:
        code, status = "timeout", "TIMEOUT"
    except Exception as exc:
        code, status = "error", "ERROR"
        with open(log, "a", encoding="utf-8") as out:
            out.write(f"Worker exception type: {type(exc).__name__}\n")
    # Do not publish raw logs, private paths or unverified Codex claims.
    digest = hashlib.sha256(log.read_bytes()).hexdigest() if log.exists() else "none"
    body = (f"{MARKER}\n### V2 issue #{a.issue}: {status}\n"
            f"- codex_exit: {code}\n- mode: {task['mode']}\n"
            f"- local_log_sha256: `{digest}`\n"
            "- Artifact acceptance: NOT VERIFIED\n"
            "- Raw logs and private media were not uploaded.\n")
    r = cmd(["gh", "issue", "comment", str(a.issue), "-R", REPO, "--body", body], timeout=60)
    if r.returncode:
        print("GitHub report failed; inspect local log. Claim retained.", file=sys.stderr)
        sys.exit(3)
    print(body)

if __name__ == "__main__":
    main()
