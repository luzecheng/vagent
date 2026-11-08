"""整套图统一对齐：每张按面罩线宽归一到同一身体大小，再统一缩小到最高点（含举起的手）离顶部 ≥ 8%，
脚底放在同一高度，按胸口核心水平居中（用身体居中，举手时人不会左右跳）。
用法：python review/align.py 原图名... （存为 <原图名>_对齐.png）"""
import sys
from PIL import Image
import numpy as np
from scipy import ndimage

TOP, FOOT = 0.09, 0.92          # 最高点离顶部 ≥ 8%（留 1% 余量给辉光）；脚底放在画面 92% 高度


def measure(a):
    H, W = a.shape[:2]
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blue = (b > 150) & (b - r > 40) & (g > r)
    lab, k = ndimage.label(ndimage.binary_dilation(blue, iterations=3))
    blobs = []
    for i in range(1, k + 1):
        ys, xs = np.where((lab == i) & blue)
        if len(ys) > 30:
            blobs.append((xs.mean(), ys.mean(), xs.max() - xs.min(), ys.max() - ys.min()))
    visor = max(blobs, key=lambda q: q[2] / (q[3] + 1))
    core = min((q for q in blobs if q[1] > visor[1] and q is not visor),
               key=lambda q: abs(q[1] - visor[1] - 0.12 * H) + abs(q[0] - visor[0]))
    ys, xs = np.where(a.max(2) > 40)
    return dict(visor=visor[2], core_x=core[0], top=ys.min(), foot=ys.max())


def main():
    names = sys.argv[1:]
    imgs = {n: np.asarray(Image.open(f"frames/{n}.png").convert("RGB")) for n in names}
    H, W = imgs[names[0]].shape[:2]
    m = {n: measure(a) for n, a in imgs.items()}
    ref = m[names[0]]["visor"]
    norm = {n: ref / m[n]["visor"] for n in names}                       # 身体大小归一
    room = (FOOT - TOP) * H
    s = min(room / (norm[n] * (m[n]["foot"] - m[n]["top"])) for n in names)   # 统一缩小，最高的那张刚好放下
    for n in names:
        k = s * norm[n]
        im = Image.fromarray(imgs[n]).resize((round(W * k), round(H * k)), Image.LANCZOS)
        out = Image.new("RGB", (W, H))
        out.paste(im, (round(W / 2 - m[n]["core_x"] * k), round(FOOT * H - m[n]["foot"] * k)))
        out.save(f"frames/{n}_对齐.png")
        print(f"{n}: 缩放 {k:.3f}（统一 {s:.3f} × 身体归一 {norm[n]:.3f}）")


if __name__ == "__main__":
    main()
