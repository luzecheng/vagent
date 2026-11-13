# Mac Codex read-only daemon

This is an **opt-in read-only issue queue**, not an autonomous code-editing agent.

## One-time Mac installation

Run from a terminal where `gh auth status` succeeds and `codex` works:

```bash
git -C ~/vagent-agent-worker pull --ff-only origin agent/codex-worker-mvp
python3 -m unittest discover -s ~/vagent-agent-worker/tools -p 'test_codex_daemon.py' -v
python3 ~/vagent-agent-worker/tools/codex_daemon.py --repo-path ~/vagent --dry-run
python3 ~/vagent-agent-worker/tools/install_codex_daemon.py install --repo-path ~/vagent
```

This installs a per-user macOS LaunchAgent. No sudo. It polls every 60 seconds while Mac is awake, the user is logged in, and network/auth are working.

## Verify or uninstall

```bash
python3 ~/vagent-agent-worker/tools/install_codex_daemon.py status
tail -n 30 ~/Library/Logs/vagent-codex-worker/worker.log
python3 ~/vagent-agent-worker/tools/install_codex_daemon.py uninstall
```

## Safety boundaries

Only owner-authored open issues with `<!-- codex-worker-readonly-approved-v1 -->` are eligible. The worker **never executes issue content**; the Codex prompt is hardcoded read-only. It scans the latest 100 open issues. A local claim file avoids duplicate work on one Mac; **do not run multiple machines** because there is no distributed lock. Failed claims are retained for manual investigation. No deployment, code edits, or autonomous ChatGPT review. GitHub result comments include status and exit code, not raw output. To authorize arbitrary future development work, a separately reviewed worker version is required.
