"""Structured run log: one JSON object per line in <run dir>/run.log.jsonl, plus a readable console line."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import time


class RunLog:
    def __init__(self, path: Path | None = None, quiet: bool = False):
        self.path = path
        self.quiet = quiet
        self.t0 = time.time()
        self.events: list[dict] = []   # this run only (the file accumulates across reruns)
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)

    def event(self, stage: str, message: str, **fields) -> None:
        record = {"time": datetime.now().isoformat(timespec="seconds"), "elapsed_s": round(time.time() - self.t0, 2),
                  "stage": stage, "message": message, **fields}
        self.events.append(record)
        if self.path:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        if not self.quiet:
            print(f"[{record['elapsed_s']:7.1f}s] {stage:<10} {message}", file=sys.stderr, flush=True)

    def error(self, stage: str, message: str, retry: str, **fields) -> None:
        self.event(stage, "ERROR: " + message, retry=retry, level="error", **fields)
