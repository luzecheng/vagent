"""让一张姿势图贴合设定图：两张图里位置接近的冰蓝光点（面罩、胸口、没动的关节）一一配对，
最小二乘求"等比缩放 + 平移"，把姿势图变换过去。用于交叉淡化：身体不动的部分重合，就不会出现两个头。
用法：python review/fit_to_ref.py <参考图名> <姿势图名>（存为 <姿势图名>_贴合.png）"""
import sys
from PIL import Image
import numpy as np
from scipy import ndimage


def points(a):
    r, g, b = [a[..., i].astype(int) for i in range(3)]
    blue = (b > 150) & (b - r > 40) & (g > r)
    lab, k = ndimage.label(ndimage.binary_dilation(blue, iterations=3))
    pts = []
    for i in range(1, k + 1):
        ys, xs = np.where((lab == i) & blue)
        if len(ys) > 30:
            pts.append((xs.mean(), ys.mean()))
    return np.array(pts)


ref_name, name = sys.argv[1], sys.argv[2]
ref = np.asarray(Image.open(f"frames/{ref_name}.png").convert("RGB"))
img = np.asarray(Image.open(f"frames/{name}.png").convert("RGB"))
H, W = ref.shape[:2]
P, Q = points(img), points(ref)
pairs = []
for p in P:
    d = np.hypot(*(Q - p).T)
    if d.min() < 0.04 * W:                                  # 只配位置接近的点：动过的手臂关节不算
        pairs.append((p, Q[d.argmin()]))
src = np.array([p for p, _ in pairs]); dst = np.array([q for _, q in pairs])
keep = np.ones(len(src), bool)
for _ in range(3):                                          # 去掉配错的点（残差 > 15px）再算
    sc, dc = src[keep].mean(0), dst[keep].mean(0)
    s = np.sqrt(((dst[keep] - dc) ** 2).sum() / ((src[keep] - sc) ** 2).sum())
    t = dc - s * sc
    res = np.hypot(*(s * src + t - dst).T)
    keep = res < max(15, np.sort(res)[len(res) // 2] * 2)
res = res[keep]; pairs = [q for q, k in zip(pairs, keep) if k]
print(f"{name}: 配对 {len(pairs)} 个光点，缩放 {s:.3f}，平移 ({t[0]:.1f}, {t[1]:.1f})，残差平均 {res.mean():.1f}px 最大 {res.max():.1f}px")
out = Image.fromarray(img).transform((W, H), Image.AFFINE, (1 / s, 0, -t[0] / s, 0, 1 / s, -t[1] / s), Image.BICUBIC)
out.save(f"frames/{name}_贴合.png")
