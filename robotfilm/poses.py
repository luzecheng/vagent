"""Named robot poses for reusable episode beats.

Episode files may still pass the old pose dictionaries/callables.  Named poses
make longer shots easier to author and keep the character's proportions in one
place across a series.
"""
from __future__ import annotations

import math

from .walker import STAND


def P(**kw):
    return {**STAND, **kw}


POSES = {
    "stand": STAND,
    "think": P(ua_f=28, la_f=158, head=10),
    "look_up": P(head=-30, lean=-3),
    "point": P(ua_f=128, la_f=136, head=-14),
    "shrug": P(ua_f=26, la_f=96, ua_b=-22, la_b=82, head=6),
    "read": P(ua_f=36, la_f=96, ua_b=30, la_b=92, head=22),
    "bow": P(head=24, lean=4),
    "hold": P(ua_f=34, la_f=82, ua_b=26, la_b=78),
    "wave": P(ua_f=155, la_f=170, head=-8),
}


def work(lt: float, _duration: float):
    return P(ua_f=46, la_f=88 + 14 * math.sin(lt * 9), ua_b=40, la_b=80 + 12 * math.sin(lt * 9 + 2), head=18)


POSES["work"] = work


def resolve(pose):
    """Resolve a named pose while preserving dictionaries and callables."""
    if isinstance(pose, str):
        try:
            return POSES[pose]
        except KeyError as exc:
            raise ValueError(f"unknown robot pose {pose!r}; choose one of {sorted(POSES)}") from exc
    return pose
