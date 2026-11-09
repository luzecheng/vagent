"""Robot story film: stations (props placed along the road) and the robot's footing on them."""
import types

import numpy as np
from PIL import Image

from robotfilm.robot_story import Film
from story.render import FPS


def _props_sheet(path):
    """Nine plain white blocks on black, 3 x 3, the sixth one wide like a staircase."""
    a = np.zeros((900, 1600, 3), np.uint8)
    for k in range(9):
        r, c = divmod(k, 3)
        w = 360 if k == 5 else 160
        x0, y0 = 120 + c * 520, 80 + r * 300
        a[y0:y0 + 160, x0:x0 + w] = 255
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(path)


def _film(tmp_path, beats):
    _props_sheet(tmp_path / "robot2/frames/道具图_v1.png")
    shots, t = [], 0.0
    for i, d in enumerate((9.0, 6.0), 1):
        shots.append({"id": i, "start": t, "end": t + d, "voice_end": t + d - 0.3})
        t += d
    mod = types.SimpleNamespace(BEATS=beats, MACHINE=None,
                                PROPS=["a", "b", "c", "d", "e", "stairs", "g", "h", "i"])
    return Film(tmp_path, {"duration": t, "shots": shots}, 1080, 1920, mod, "zh")


def test_the_robot_never_climbs_stairs_that_are_not_shown(tmp_path):
    # up the stairs in shot 1, down the far side in shot 2: the robot gets to the top while shot 1 is still on
    film = _film(tmp_path, {
        1: dict(walk=99, stations=[("stairs", 0, 250, {"left_at": 0.6, "climb": True, "key": "up"})]),
        2: dict(walk=99, stations=[("stairs", 0, 250, {"after": "up", "climb": True, "flip": True, "overlap": 80})]),
    })
    on_down = 0
    for f in range(int(film.tl["duration"] * FPS)):
        t = f / FPS
        for st in film.stations:
            if not st.get("climb"):
                continue
            left = st["x"] - st["w"] / 2 - film.trav(t)
            if 0 <= (film.hip_x - left) / st["w"] <= 1:          # the robot is standing on this one
                on_down += st.get("flip", False) and t < film.shots[1]["start"]
                assert st["t_in"] <= t <= st["t_out"], (t, st["name"], st["t_in"], st["t_out"])
    assert on_down, "the test should have the robot on the down stairs during shot 1"
