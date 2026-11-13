"""小样：机器人木偶走在「一笔」的夜山世界里——走几步、停下、抬头、转身面向观众、挥手（约 10 秒，竖屏）。
用法：.venv/bin/python tests/robot-puppet/make_clip.py [--scale 0.5] [--out 文件名] [--still 秒数]
--scale  机器人等比缩放（以站姿时两脚中点、地面线为基准；所有姿势同一比例、同一基准），走路时背景滚动速度同比例变化"""
import math
import subprocess
import sys
from pathlib import Path

import cairo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from robotfilm.puppet import Puppet, load_parts  # noqa: E402
from story import hero as H  # noqa: E402
from story.stage import Camera, Stage, ramp  # noqa: E402

HERE = Path(__file__).parent
W, HH, FPS, DUR = 1080, 1920, 30, 10.0
smooth = lambda k: k * k * (3 - 2 * k)
full = lambda q: {**{k: 0.0 for k in H.KEYS}, **q}


def pose_at(t):
    """(pose, distance walked) at time t."""
    walk = full(H.pose("walk", t))
    stand, look, front = full(H.pose("stand")), full(H.pose("look_up")), full(H.pose("front"))
    wave = full({**H.POSES["lamp_up"], "turn": 1, "la_f": 150 + 18 * math.sin((t - 8.4) * 7)})
    if t < 4.0:
        q = walk
    elif t < 4.7:
        q = H.blend(walk, stand, smooth(ramp(t, 4.0, 4.7)))
    elif t < 6.6:
        q = H.blend(stand, look, smooth(ramp(t, 4.9, 5.6)))
    elif t < 7.3:
        q = H.blend(look, stand, smooth(ramp(t, 6.6, 7.3)))
    elif t < 8.4:
        q = H.blend(stand, front, smooth(ramp(t, 7.4, 8.3)))
    else:
        q = H.blend(front, wave, smooth(ramp(t, 8.4, 8.9)))
    # walking speed eases out as the robot stops
    v = 135 * 1.9
    d = v * min(t, 4.0) + v * 0.35 * max(0.0, min(t, 4.7) - 4.0)
    return q, d


def main():
    parts = load_parts(HERE / "frames/01_零件图_v1.png")
    pup = Puppet(parts)
    st = Stage(W, HH, seed=19, scenery=True)
    arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    still, scale, name = arg("--still", -1.0), arg("--scale", 1.0), arg("--out", "小样_机器人走路_v1.mp4")
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, HH)
    x_full, height = st.hx + W * 0.08, 560
    # the scaling anchor: the middle of the two ankles in the standing pose at full size, on the ground line
    j = pup.solve(full(H.pose("stand")))
    anchor = x_full + (j["leg_f"][-1][0] + j["leg_b"][-1][0]) / 2 * height / pup.stand_h
    x = anchor - (anchor - x_full) * scale

    def frame(t):
        q, d = pose_at(t)
        st.cam = Camera(travel=d * scale)          # smaller steps: the world scrolls slower by the same factor
        st.t = t
        cr = cairo.Context(surf)
        st.draw_world(cr, t)
        pup.draw(cr, x, st.horizon, q, height=height * scale)
        surf.flush()

    if still >= 0:
        frame(still)
        surf.write_to_png(str(HERE / f"review/小样帧_{still}s.png"))
        return
    out = HERE / "clips" / name
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{HH}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                           "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for f in range(int(DUR * FPS)):
        frame(f / FPS)
        ff.stdin.write(bytes(surf.get_data()))
    ff.stdin.close()
    assert ff.wait() == 0
    print("wrote", out)


if __name__ == "__main__":
    main()
