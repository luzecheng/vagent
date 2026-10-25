"""Content-addressed cache: identical inputs (text + settings) are never recomputed."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def key(*parts: Any) -> str:
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


class Cache:
    def __init__(self, root: str | Path, namespace: str):
        self.dir = Path(root) / namespace
        self.dir.mkdir(parents=True, exist_ok=True)

    def path(self, digest: str, suffix: str) -> Path:
        return self.dir / f"{digest}{suffix}"

    def get_json(self, digest: str) -> Any | None:
        path = self.path(digest, ".json")
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def put_json(self, digest: str, value: Any) -> None:
        path = self.path(digest, ".json")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
