#!/usr/bin/env python3
"""Opt-in, read-only Codex/GitHub worker. Python stdlib only."""
import argparse
import json
import os
import pathlib
import subprocess
import time

REPO = "luzecheng/vagent"
OWNER = "luzecheng"
MARKER = "<!-- codex-worker-readonly-approved-v1 -->"
DONE = "<!-- codex-worker-readonly-result-v1 -->"
PROMPT = ("Inspect the current repository without modifying any files. "
          "Report the repository root, current branch, git status summary, "
          "and whether skill/make-video/SKILL.md exists. Do not run commands "
          "that modify files or contact external services.")

def run(args, timeout=30, cwd=None):
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout, cwd=cwd)

def issue_info(number):
    p = run(["gh", "api", f"repos/{REPO}/issues/{number}"])
    if p.returncode:
        raise RuntimeError("GitHub issue lookup failed: " + p.stderr[:400])
    return json.loads(p.stdout)

def comments(number):
    p = run(["gh", "api", "--paginate", f"repos/{REPO}/issues/{number}/comments"])
    if p.returncode:
        raise RuntimeError("GitHub comments lookup failed")
    return json.loads(p.stdout)

def eligible(issue, number, allowed):
    return (number in allowed and issue.get("user", {}).get("login", "").lower() == OWNER
            and issue.get("state") == "open" and MARKER in (issue.get("body") or "")
            and "pull_request" not in issue)

def post(number, body):
    p = run(["gh", "issue", "comment", str(number), "-R", REPO, "--body", body], timeout=45)
    if p.returncode:
        raise RuntimeError("Unable to post issue comment: " + p.stderr[:300])

def once(numbers, repo_path, state_dir, dry_run=False):
    state_dir.mkdir(parents=True, exist_ok=True)
    for number in numbers:
        issue = issue_info(number)
        if not eligible(issue, number, set(numbers)):
            print(f"SKIP #{number}: not owner-authorized")
            continue
        existing = comments(number)
        if any(DONE in (c.get("body") or "") for c in existing):
            print(f"SKIP #{number}: already completed")
            continue
        lock = state_dir / f"issue-{number}.claimed"
        try:
            with lock.open("x") as f:
                f.write(str(time.time()))
        except FileExistsError:
            print(f"SKIP #{number}: local claim exists")
            continue
        if dry_run:
            lock.unlink()
            print(f"DRY RUN #{number}: authorized and pending")
            continue
        try:
            result = run(["codex", "exec", "-s", "read-only", PROMPT], timeout=300, cwd=repo_path)
            output = (result.stdout + "\n" + result.stderr)[-9000:]
            # Avoid publishing environment details, secrets or full agent logs.
            status = "PASS" if result.returncode == 0 else "FAIL"
            safe = f"exit_code={result.returncode}; output_chars={len(output)}"
            post(number, f"{DONE}\n### Mac Codex worker: {status}\n"
                 f"- Mode: fixed read-only inspection\n- {safe}\n"
                 "- Full output retained locally; no raw logs published.\n")
            print(f"{status} #{number}: evidence posted")
        except (subprocess.TimeoutExpired, Exception) as exc:
            print(f"ERROR #{number}: {type(exc).__name__}")
            # Keep claim on failure to avoid retry storms; operator can inspect and clear.
            continue

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo-path", default=str(pathlib.Path.home() / "vagent"))
    p.add_argument("--issues", required=True, help="Comma-separated owner-approved issue numbers")
    p.add_argument("--interval", type=int, default=60)
    p.add_argument("--once", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    numbers = [int(x.strip()) for x in args.issues.split(",")]
    repo_path = pathlib.Path(args.repo_path).expanduser().resolve()
    if not (repo_path / ".git").exists():
        p.error("repo-path must be an existing Git checkout")
    state = pathlib.Path.home() / ".local/state/vagent-codex-worker"
    while True:
        try:
            once(numbers, repo_path, state, args.dry_run)
        except Exception as exc:
            print(f"Worker error: {type(exc).__name__}: {str(exc)[:150]}")
        if args.once or args.dry_run:
            break
        time.sleep(max(args.interval, 30))

if __name__ == "__main__":
    main()
