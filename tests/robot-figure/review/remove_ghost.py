"""去掉 02_叉腰_v2 右膝（画面左侧）外侧那道淡淡的竖条残影。
只动一个小框：框里离亮线（>150）超过 5 像素的像素逐渐压暗，超过 8 像素的变黑；
正常辉光在 8 像素外本来就 < 10，几乎不受影响。存为 _去残影.png，原图不动。"""
from PIL import Image
import numpy as np
from scipy import ndimage

SRC, DST = "frames/02_叉腰_v2.png", "frames/02_叉腰_v2_去残影.png"
X0, X1, Y0, Y1 = 712, 746, 575, 700

a = np.asarray(Image.open(SRC).convert("RGB")).astype(np.float32)
L = a.max(2)
d = ndimage.distance_transform_edt(L < 150)          # 每个像素到最近亮线的距离
keep = np.clip((8 - d) / 3, 0, 1)
out = a.copy()
out[Y0:Y1, X0:X1] *= keep[Y0:Y1, X0:X1, None]
Image.fromarray(out.round().astype(np.uint8)).save(DST)
before, after = L[Y0:Y1, X0:X1], out.max(2)[Y0:Y1, X0:X1]
far = d[Y0:Y1, X0:X1] > 6
print(f"框内离亮线 >6px 的像素：最亮 {before[far].max():.0f} → {after[far].max():.0f}")
