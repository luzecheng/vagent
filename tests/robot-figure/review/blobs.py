"""冰蓝光点：逐个找出来（位置、大小），并量头宽、胸口核心到脚底的距离（不受手臂姿势影响的身体比例）。"""
import sys
from PIL import Image
import numpy as np
from scipy import ndimage

for n in sys.argv[1:]:
    a = np.asarray(Image.open(f"frames/{n}.png").convert("RGB")).astype(int); H, W, _ = a.shape
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blue = (b > 150) & (b - r > 40) & (g > r)
    lab, k = ndimage.label(ndimage.binary_dilation(blue, iterations=3))
    blobs = []
    for i in range(1, k + 1):
        ys, xs = np.where((lab == i) & blue)
        if len(ys) > 30:
            blobs.append((xs.mean(), ys.mean(), len(ys), xs.max() - xs.min(), ys.max() - ys.min()))
    visor = max(blobs, key=lambda q: q[3] / (q[4] + 1))            # 最扁的那个 = 面罩线
    core = min((q for q in blobs if q is not visor and q[1] > visor[1]), key=lambda q: abs(q[1] - visor[1] - 0.12 * H) + abs(q[0] - visor[0]))
    m = a.max(2) > 40
    row = np.where(m[int(visor[1])])[0]
    seg = row[(row > visor[0] - 0.12 * W) & (row < visor[0] + 0.12 * W)]
    foot = np.where(m.any(1))[0].max()
    print(f"{n}: 光点 {len(blobs)} 个 | 面罩线宽 {visor[3]/W*100:.1f}% | 头宽(面罩高度处) {(seg.max()-seg.min())/W*100:.1f}% | 胸口核心到脚底 {(foot-core[1])/H*100:.1f}% | 核心 x {core[0]/W*100:.1f}%")
