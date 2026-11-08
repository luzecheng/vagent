"""对比图 + 量化：机器人外接框（高度、中心、脚底）和颜色统计。用法：python measure.py <版本标签> <图名...>"""
import sys
from PIL import Image, ImageDraw, ImageFont
import numpy as np

tag, names = sys.argv[1], sys.argv[2:]
font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 28)
tiles, rows = [], []
for n in names:
    im = Image.open(f"frames/{n}.png").convert("RGB")
    a = np.asarray(im).astype(int); H, W, _ = a.shape
    ys, xs = np.where(a.max(2) > 40)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    blue = (b > 150) & (b - r > 40) & (g > r)
    by, bx = np.where(blue)
    warm = (((r - b) > 30) & (r > 60)).sum(); green = (((g - r) > 40) & ((g - b) > 20)).sum()
    h, cx, foot = (ys.max() - ys.min()) / H, (xs.min() + xs.max()) / 2 / W, ys.max() / H
    rows.append((n, W, H, h, cx, foot, blue.sum(), warm, green))
    np.save(f"review/blue_{n}.npy", np.stack([bx / W, by / H]))
    t = im.resize((640, round(640 * H / W))); d = ImageDraw.Draw(t); s = 640 / W
    d.rectangle([xs.min() * s, ys.min() * s, xs.max() * s, ys.max() * s], outline=(255, 80, 80))
    d.line([0, ys.max() * s, 640, ys.max() * s], fill=(255, 200, 0))
    d.text((10, 8), n, fill=(255, 200, 0), font=font)
    tiles.append(t)
hh = max(t.height for t in tiles)
sheet = Image.new("RGB", (640 * 3, hh * ((len(tiles) + 2) // 3)), (30, 30, 30))
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % 3) * 640, (i // 3) * hh))
sheet.save(f"review/对比图_{tag}.png")
b = rows[0]
print("图 | 尺寸 | 高度% 中心x% 脚底y% | 高度偏差 中心偏差 脚底偏差 | 冰蓝 暖色 绿色")
for n, W, H, h, cx, foot, bl, wa, gr in rows:
    print(f"{n} | {W}x{H} | {h*100:.1f} {cx*100:.1f} {foot*100:.1f} | {(h-b[3])/b[3]*100:+.1f}% {(cx-b[4])*100:+.1f} {(foot-b[5])*100:+.1f} | {bl} {wa} {gr}")
