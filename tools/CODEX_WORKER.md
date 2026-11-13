# Mac Codex read-only worker (prototype)

This is a narrowly scoped opt-in prototype, **not** an unattended code-editing agent.
It runs a fixed read-only Codex prompt, **not** instructions from GitHub issue bodies.
It only checks owner-authored, open, explicitly marked issues whose numbers are supplied on the command line. It does not automatically discover newly created issues.

## First-time setup

Prerequisites: authenticated `gh`, working `codex`, Python 3, and a checkout at `~/vagent`.
This prototype lives on branch `agent/codex-worker-mvp`. To avoid touching the existing working tree, create a **separate checkout**:

```bash
git clone --branch agent/codex-worker-mvp https://github.com/luzecheng/vagent.git ~/vagent-agent-worker
python3 -m unittest discover -s ~/vagent-agent-worker/tools -p 'test_codex_issue_worker.py' -v
python3 ~/vagent-agent-worker/tools/codex_issue_worker.py --repo-path ~/vagent --issues 2 --dry-run
```

After verifying the dry run, run a one-shot test:

```bash
python3 ~/vagent-agent-worker/tools/codex_issue_worker.py --repo-path ~/vagent --issues 2 --once
```

For foreground polling, omit `--once`; stop with Ctrl+C. It polls every 60 seconds by default, but Issue #2 will only run once. No macOS launch agent is installed by these commands.

## Security / limitations

- No GitHub tokens or secrets should be pasted into chat.
- No auto-push, deployment, code changes or arbitrary issue-prompt execution.
- GitHub comments contain only completion status and exit code, **not** full Codex output.
- Local claim files at `~/.local/state/vagent-codex-worker/` prevent automatic retries. Do not delete them unless investigating an incomplete run.
- A local claim is not a distributed lock. Multiple machines or different home directories must not run this worker for the same issue.
- This version is intentionally **not** a fully automatic task queue or macOS background service; those require a separate safety review and implementation.
