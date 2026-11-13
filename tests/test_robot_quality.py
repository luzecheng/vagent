from pathlib import Path
import types

import pytest

from robotfilm.poses import POSES, resolve
from robotfilm.series_assets import validate
from robotfilm.shotlist import warnings


def test_named_poses_are_reusable_and_unknown_names_fail():
    assert resolve("look_up") == POSES["look_up"]
    with pytest.raises(ValueError, match="unknown robot pose"):
        resolve("cartwheel")


def test_series_assets_require_nine_unique_props_and_sheet(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    for name in ("side_parts.png", "front_00_stand.png", "front_01_hand_up.png", "front_03_arm_shoulder.png"):
        (assets / name).touch()
    folder = tmp_path / "episode"
    (folder / "robot2/frames").mkdir(parents=True)
    (folder / "robot2/frames/道具图_v1.png").touch()
    result = validate(folder, list("abcdefghi"), assets)
    assert result["style"] == "robot-night-v1"
    with pytest.raises(ValueError, match="exactly 9"):
        validate(folder, list("abcdefgh"), assets)


def test_long_shots_need_split_or_timed_actions():
    rows = [{"id": 1, "dur": 18.0, "moves": ["walks"]}]
    assert any("long" in message for message in warnings(rows))
    rows[0]["moves"].append("think / point / look_up")
    assert not any("long" in message for message in warnings(rows))
