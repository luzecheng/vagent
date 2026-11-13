"""Shared visual contract for the robot video series.

The robot itself comes from the checked-in side-parts/angle assets.  Episodes
provide only a nine-island props sheet, whose order is declared in beats.py.
This small validator catches accidental character/asset drift before a costly
render starts.
"""
from __future__ import annotations

from pathlib import Path

SERIES_STYLE = "robot-night-v1"
PROP_SHEET_COUNT = 9
REQUIRED_ROBOT_ASSETS = ("side_parts.png", "front_00_stand.png", "front_01_hand_up.png", "front_03_arm_shoulder.png")


def validate(folder: Path, prop_names: list[str], robot_assets: Path) -> dict:
    names = list(prop_names)
    if len(names) != PROP_SHEET_COUNT:
        raise ValueError(f"robot props sheet must have exactly {PROP_SHEET_COUNT} objects; beats declares {len(names)}")
    if len(set(names)) != len(names):
        raise ValueError("robot props names must be unique and match the generated sheet order")
    missing = [name for name in REQUIRED_ROBOT_ASSETS if not (robot_assets / name).exists()]
    if missing:
        raise FileNotFoundError(f"robot series assets missing: {', '.join(missing)}")
    sheet = Path(folder) / "robot2/frames/道具图_v1.png"
    if not sheet.exists():
        raise FileNotFoundError(f"episode props sheet missing: {sheet}")
    return {"style": SERIES_STYLE, "prop_names": names, "prop_sheet": str(sheet)}
