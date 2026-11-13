"""小样 v2：侧面用代码走路（walker.py：8 个关键姿势、指尖到大腿中部、脚不打滑、身体起伏），停 0.5 秒，
硬切 + 白光闪烁转到正面设定图，再交叉淡化到"手臂抬到肩高"和"举手"（只有手臂在变）。人物 50%，新背景。
用法：.venv/bin/python tests/robot-puppet/make_clip_v2b.py [--still 秒数] [--log]"""
import json
import math
import subprocess
import sys
from pathlib import Path

import cairo
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from robotfilm.puppet import ICE, _surface  # noqa: E402
from robotfilm.walker import PERIOD, STAND, Walker, blend, cutout, load_side_parts, walk_pose  # noqa: E402
from robotfilm.world import World  # noqa: E402
from story.stage import ramp  # noqa: E402

HERE = Path(__file__).parent
FIG = ROOT / "tests/robot-figure/frames"
W, HH, FPS = 1080, 1920, 30
HEIGHT = 280                                   # 50% of the first test's 560 px
WALK_END = 3 * PERIOD                          # three full cycles (six steps)
STOP_END = WALK_END + 0.5
TURN_AT = STOP_END + 0.5                       # stands still 0.5 s, then turns
FRONTS = [(FIG / "00_设定图_v1.png", TURN_AT), (FIG / "03_手臂抬到肩高_v1.png", TURN_AT + 0.30),
          (FIG / "01_举手_v2.png", TURN_AT + 0.65)]
FADE = 0.3
DUR = TURN_AT + 2.2
smooth = lambda k: k * k * (3 - 2 * k)


def pose(t):
    if t < WALK_END:
        return walk_pose(t)
    if t < STOP_END:
        return blend(walk_pose(t), STAND, smooth(ramp(t, WALK_END, STOP_END)))
    return STAND


def _glows(a):
    from scipy import ndimage
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blue = (b > 150) & (b - r > 40) & (g > r)
    lab, k = ndimage.label(ndimage.binary_dilation(blue, iterations=3))
    pts = []
    for i in range(1, k + 1):
        ys, xs = np.where((lab == i) & blue)
        if len(ys) > 30:
            pts.append((xs.mean(), ys.mean()))
    return np.array(pts)


def fit(ref, img):
    """Scale and shift mapping `img` onto `ref`, from the ice-blue joints that did not move (as in
    tests/robot-figure/review/fit_to_ref.py), without cropping anything."""
    P, Q = _glows(img), _glows(ref)
    W_ = ref.shape[1]
    pairs = [(p, Q[np.hypot(*(Q - p).T).argmin()]) for p in P if np.hypot(*(Q - p).T).min() < 0.04 * W_]
    src, dst = np.array([p for p, _ in pairs]), np.array([q for _, q in pairs])
    keep = np.ones(len(src), bool)
    for _ in range(3):
        sc, dc = src[keep].mean(0), dst[keep].mean(0)
        s = np.sqrt(((dst[keep] - dc) ** 2).sum() / ((src[keep] - sc) ** 2).sum())
        t = dc - s * sc
        res = np.hypot(*(s * src + t - dst).T)
        keep = res < max(15, np.sort(res)[len(res) // 2] * 2)
    return s, (t[0], t[1])


class Front:
    """The front-view drawings, cut out of their black backgrounds, scaled so the robot is as tall as the
    walking one and its feet stand on the same spot."""

    def __init__(self, paths, height):
        self.surfs = []
        ref = np.asarray(Image.open(paths[0]).convert("RGB")).astype(np.float32)
        lum = ref.max(2)
        ys, xs = np.where(lum > 60)
        self.top, self.feet_y = ys.min(), ys.max()
        low = ys > self.feet_y - 12
        self.feet_x = (xs[low].min() + xs[low].max()) / 2
        self.k = height / (self.feet_y - self.top)
        self.fits = []
        for p in paths:
            rgb = np.asarray(Image.open(p).convert("RGB")).astype(np.float32)
            self.surfs.append(_surface(rgb, cutout(rgb)))
            self.fits.append(fit(ref, rgb))      # scale + shift that lays its body over the first drawing

    def draw(self, cr, i, x, ground, alpha):
        cr.save()
        cr.translate(x, ground)
        cr.scale(self.k, self.k)
        cr.translate(-self.feet_x, -self.feet_y)
        fs, (fx, fy) = self.fits[i]
        cr.translate(fx, fy)
        cr.scale(fs, fs)
        cr.set_source_surface(self.surfs[i], 0, 0)
        cr.get_source().set_filter(cairo.FILTER_GOOD)
        cr.paint_with_alpha(alpha)
        cr.restore()


def main():
    walker = Walker(load_side_parts(HERE / "frames/04_侧面零件图_v1.png"))
    front = Front([p for p, _ in FRONTS], HEIGHT)
    world = World(W, HH)
    s = walker.scale_for(HEIGHT)
    hip_x = W * 0.36
    # where the feet stand (the middle of the two ankles, standing): the front drawings put their feet there
    j0 = walker.solve(STAND)
    foot_mid = (j0["leg_f"][-1][0] + j0["leg_b"][-1][0]) / 2
    fp = walker.p["foot"]
    feet_x = hip_x + (foot_mid + (sum(x for x, _ in fp.sole) / 2 - fp.top[0])) * s

    # world travel: the planted foot must not move against the ground
    n = int(DUR * FPS) + 1
    travel, log = [0.0], []
    for f in range(1, n):
        t0, t1 = (f - 1) / FPS, f / FPS
        a, b = walker.solve(pose(t0)), walker.solve(pose(t1))
        side = a["support"]
        dx = (a["leg_" + side][-1][0] - b["leg_" + side][-1][0]) * s     # the planted ankle moved back by dx
        travel.append(travel[-1] + max(0.0, dx))
    for f in range(n):
        t = f / FPS
        jj = walker.solve(pose(t))
        side = jj["support"]
        log.append({"t": round(t, 3), "support": side, "ankle_screen_x": round(hip_x + jj["leg_" + side][-1][0] * s, 2),
                    "travel": round(travel[f], 2)})

    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, HH)

    def frame(f):
        t = f / FPS
        cr = cairo.Context(surf)
        world.draw(cr, travel[min(f, n - 1)], t)
        ground = world.horizon
        if t < TURN_AT:
            walker.draw(cr, hip_x, ground, pose(t), HEIGHT)
        else:
            for i, (_, t0) in enumerate(FRONTS):
                nxt = FRONTS[i + 1][1] if i + 1 < len(FRONTS) else None
                a = 1.0 if i == 0 else smooth(ramp(t, t0, t0 + FADE))
                if nxt is not None and t >= nxt + FADE:
                    continue
                if a > 0:
                    front.draw(cr, i, feet_x, ground, a)
        flash = 1 - min(1.0, abs(t - TURN_AT) / (1.5 / FPS))
        if flash > 0:
            cx, cy = feet_x, ground - HEIGHT * 0.5
            R = HEIGHT * 0.8
            g = cairo.RadialGradient(cx, cy, 0, cx, cy, R)
            g.add_color_stop_rgba(0, 1, 1, 1, 0.95 * flash)
            g.add_color_stop_rgba(0.45, *ICE, 0.55 * flash)
            g.add_color_stop_rgba(1, *ICE, 0)
            cr.set_source(g)
            cr.arc(cx, cy, R, 0, 2 * math.pi)
            cr.fill()
        surf.flush()

    if "--still" in sys.argv:
        t = float(sys.argv[sys.argv.index("--still") + 1])
        frame(int(round(t * FPS)))
        surf.write_to_png(str(HERE / f"review/v2b帧_{t}s.png"))
        return
    (HERE / "review/走路打滑追踪_v2.json").write_text(json.dumps(log, ensure_ascii=False))
    out = HERE / "clips/小样_机器人走路_v2.mp4"
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{HH}",
                           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                           "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    for f in range(int(DUR * FPS)):
        frame(f)
        ff.stdin.write(bytes(surf.get_data()))
    ff.stdin.close()
    assert ff.wait() == 0
    print("wrote", out, f"{DUR:.2f}s")


if __name__ == "__main__":
    main()
