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


def _talky_film(tmp_path):
    """Shot 1 talks, 2 walks in then talks, 3 talks, 4 is a quote shot."""
    _props_sheet(tmp_path / "robot2/frames/道具图_v1.png")
    shots, t = [], 0.0
    for i, d in enumerate((5.0, 6.0, 4.0, 5.0), 1):
        s = {"id": i, "start": t, "end": t + d, "voice_end": t + d - 0.3}
        if i == 4:
            s["quote"] = "金句"
        shots.append(s)
        t += d
    mod = types.SimpleNamespace(BEATS={2: dict(walk=1.5)}, MACHINE=None,
                                PROPS=["a", "b", "c", "d", "e", "stairs", "g", "h", "i"])
    return Film(tmp_path, {"duration": t, "shots": shots}, 1080, 1920, mod, "zh")


def test_camera_moves_smoothly_and_never_shows_past_the_frame(tmp_path):
    film = _talky_film(tmp_path)
    zs = [film.zoom(f / FPS) for f in range(int(film.tl["duration"] * FPS))]
    assert min(zs) >= 1.0
    assert max(zs) > 1.04, "the camera should push in while the robot talks"
    assert max(abs(b - a) for a, b in zip(zs, zs[1:])) < 0.01, "no jumps at shot changes"


def test_camera_is_wide_when_the_robot_arrives_and_closest_on_quotes(tmp_path):
    film = _talky_film(tmp_path)
    s2, s4 = film.shots[1], film.shots[3]
    assert abs(film.zoom(s2["start"] + 1.5) - 1.0) < 1e-6
    talk_peaks = [film.zoom(s["end"] - 1e-3) for s in film.shots[:3]]
    assert film.zoom(s4["end"] - 1e-3) > max(talk_peaks)


def test_sky_words_are_bigger_on_a_phone(tmp_path):
    from robotfilm.fx import label_scale
    film = _talky_film(tmp_path)
    wide = types.SimpleNamespace(portrait=False)
    assert label_scale(film) >= 1.5 and 1.2 <= label_scale(wide) < label_scale(film)


def _frame(film, t):
    import cairo
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, film.W, film.H)
    film.draw(cairo.Context(surf), t)
    surf.flush()
    return np.ndarray((film.H, film.W, 4), np.uint8, surf.get_data()).astype(int)[..., :3].sum(2)


def _on_screen(film, t, x, y):
    """Where a point of the world (unzoomed frame coordinates) is on screen with the camera's zoom at t."""
    (fx, fy), z = film.cam_focus, film.zoom(t)
    return int(fx + (x - fx) * z), int(fy + (y - fy) * z)


def _lit_film(tmp_path, glow):
    _props_sheet(tmp_path / "robot2/frames/道具图_v1.png")
    shots = [{"id": 1, "start": 0.0, "end": 6.0, "voice_end": 5.7, "subs": []}]
    opts = {"glow": (1.0, 0.6, 0.25)} if glow else {}
    mod = types.SimpleNamespace(BEATS={1: dict(stations=[("a", 0.7, 150, opts)])}, MACHINE=None, SOLID_PROPS=True,
                                PROPS=["a", "b", "c", "d", "e", "stairs", "g", "h", "i"])
    return Film(tmp_path, {"duration": 6.0, "shots": shots}, 1080, 1920, mod, "zh", "color")


def test_robot_and_props_cast_soft_shadows(tmp_path):
    film = _lit_film(tmp_path, glow=False)
    img = _frame(film, 3.0)
    x, y = _on_screen(film, 3.0, film.hip_x + film.height * 0.1, film.ground + 5 * film.u)   # beside the feet
    ground = img[y, int(film.W * 0.05)]
    assert img[y, x] < ground - 6, "shadow under the robot's feet"


def test_glowing_props_light_the_ground_around_them(tmp_path):
    lit, plain = _frame(_lit_film(tmp_path, True), 3.0), _frame(_lit_film(tmp_path / "b", False), 3.0)
    film = _lit_film(tmp_path, True)
    x, y = _on_screen(film, 3.0, film.W * 0.7 + 110 * film.u, film.ground + 14 * film.u)   # beside the prop
    assert lit[y, x] > plain[y, x] + 10


def test_street_lamps_light_a_pool_on_the_ground():
    from robotfilm.world import World
    import cairo

    def render(pool):
        w = World(1080, 1920, palette="color")
        w.c = {**w.c, "lamp_pool": pool}
        surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1080, 1920)
        w.draw(cairo.Context(surf), 0.0, 0.0)
        surf.flush()
        return w, np.ndarray((1920, 1080, 4), np.uint8, surf.get_data()).astype(int)[..., :3].sum(2)

    w, lit = render(0.16)
    _, dark = render(0.0)
    y = int(w.horizon + 8 * w.u)
    lamp_x = [x for wx in w.props.lamps for x in w.props._on_screen(wx, 0.0, 1080, 100) if 100 < x < 900]
    assert lamp_x, "a lamp should be on screen at travel 0"
    head = int(lamp_x[0] + 34 * w.s)
    assert lit[y, head] > dark[y, head] + 8
    assert World(1080, 1920, palette="color").c.get("lamp_pool", 0) > 0, "the colour night has lamp pools"
