"""python -m vagent  (used by the inbox watcher to run each task in its own process)."""
from .cli import main

raise SystemExit(main())
