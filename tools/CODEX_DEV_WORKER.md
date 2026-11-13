# Development worker V1 — explicit one-shot execution

This is **not yet a background development daemon**. It is a deliberately limited first development runner for issue #5. The existing read-only LaunchAgent is unchanged.

## Preflight on Mac

```bash
git -C ~/vagent-agent-worker pull --ff-only origin agent/codex-worker-mvp
python3 ~/vagent-agent-worker/tools/codex_dev_worker.py --issue 5 --repo-path ~/vagent
```

The above performs a dry run only. Review the resulting worktree path. To explicitly start a single development run:

```bash
python3 ~/vagent-agent-worker/tools/codex_dev_worker.py --issue 5 --repo-path ~/vagent --execute
```

The runner creates a separate Git worktree and invokes Codex with `workspace-write`, with a 60-minute limit. It posts only the exit status and worktree location to GitHub. **It does not automatically push code, upload MP4, prove the video quality, or conduct independent review.** The worktree must not already exist. No API tokens should be pasted into chat.

**Important:** Workspace-write sandboxing and prompt restrictions are not a guarantee against all side effects; the first run should be supervised. This is not a substitute for OS-level isolation. Before allowing unattended code execution, implement additional verification, output artifact handling, and a robust approval mechanism.

Stop the run with Ctrl+C in its terminal. Do not delete worktree or local files until reviewed.
