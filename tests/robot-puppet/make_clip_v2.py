"""小样 v2（第 1 步的代码修复）：新的机器人世界（黑蓝剪影 + 白细线、透视暗地面）、路灯不再只剩灯头、
走路随步子上下起伏、停下 0.5 秒就转身（转身瞬间硬切 + 白光闪烁）、举手从外侧抬起不挡头盔。人物 50%。
用法：.venv/bin/python tests/robot-puppet/make_clip_v2.py [--still 秒数] [--out 文件名]"""
import math
import subprocess
import sys
from pathlib import Path

import cairo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from robotfilm.puppet import ICE, Puppet, load_parts  # noqa: E402
from robotfilm.world import World  # noqa: E402
from story import hero as H  # noqa: E402
from story.stage import ramp  # noqa: E402

HERE = Path(__file__).parent
W, HH, FPS = 1080, 1920, 30
SCALE, HEIGHT = 0.5, 560
WALK_END, STOP_END, TURN_AT, DUR = 4.0, 4.6, 5.1, 7.6
BOB = 0.02                     # body rise and fall while walking, as a share of its height
smooth = lambda k: k * k * (3 - 2 * k)
full = lambda q: {**{k: 0.0 for k in H.KEYS}, **q}

STAND, FRONT = full(H.pose("stand")), full(H.pose("front"))
SHOULDER = full({**H.POSES["front"], "turn": 1, "ua_f": -88, "la_f": -96})     # arm out to the side, shoulder high
WAVE = lambda t: full({**H.POSES["front"], "turn": 1, "ua_f": -160, "la_f": -172 + 14 * math.sin((t - 6.0) * 7)})


def state(t):
    """(pose, distance walked, vertical bob in px at full size)."""
    walk = full(H.pose("walk", t))
    ph = t * 2 * math.pi * 0.9
    bob = 0.0
    if t < WALK_END:
        q = walk
        bob = BOB * HEIGHT * (1 - abs(math.sin(ph)))      # highest as the legs pass, lowest at heel strike
    elif t < STOP_END:
        k = smooth(ramp(t, WALK_END, STOP_END))
        q = H.blend(walk, STAND, k)
        bob = BOB * HEIGHT * (1 - abs(math.sin(ph))) * (1 - k)
    elif t < TURN_AT:
        q = STAND
    elif t < 5.4:
        q = FRONT                                          # hard switch to the front at TURN_AT
    elif t < 5.8:
        q = H.blend(FRONT, SHOULDER, smooth(ramp(t, 5.4, 5.8)))
    elif t < 6.1:
        q = H.blend(SHOULDER, WAVE(t), smooth(ramp(t, 5.8, 6.1)))
    else:
        q = WAVE(t)
    v = 135 * 1.9
    d = v * min(t, WALK_END) + v * 0.35 * max(0.0, min(t, STOP_END) - WALK_END)
    return q, d, bob


def main():
    pup = Puppet(load_parts(HERE / "frames/01_零件图_v1.png"))
    world = World(W, HH)
    arg = lambda k, d: type(d)(sys.argv[sys.argv.index(k) + 1]) if k in sys.argv else d
    still, name = arg("--still", -1.0), arg("--out", "小样_机器人走路_v2_代码修复.mp4")
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, HH)
    j = pup.solve(STAND)
    x_full = W * 0.30 + W * 0.08
    anchor = x_full + (j["leg_f"][-1][0] + j["leg_b"][-1][0]) / 2 * HEIGHT / pup.stand_h
    x = anchor - (anchor - x_full) * SCALE

    def frame(t):
        q, d, bob = state(t)
        cr = cairo.Context(surf)
        world.draw(cr, d * SCALE, t)
        J = pup.draw(cr, x, world.horizon - bob * SCALE, q, height=HEIGHT * SCALE)
        flash = 1 - min(1.0, abs(t - TURN_AT) / (1.5 / FPS))     # ~3 frames of white light over the switch
        if flash > 0:
            cx, cy = J["neck"][0], (J["neck"][1] + world.horizon) / 2
            R = HEIGHT * SCALE * 0.75
            g = cairo.RadialGradient(cx, cy, 0, cx, cy, R)
            g.add_color_stop_rgba(0, 1, 1, 1, 0.95 * flash)
            g.add_color_stop_rgba(0.45, *ICE, 0.55 * flash)
            g.add_color_stop_rgba(1, *ICE, 0)
            cr.set_source(g)
            cr.arc(cx, cy, R, 0, 2 * math.pi)
            cr.fill()
        surf.flush()

    if still >= 0:
        frame(still)
        surf.write_to_png(str(HERE / f"review/v2帧_{still}s.png"))
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
