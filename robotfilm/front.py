"""The robot facing the viewer: front-view drawings (character sheet, arm at shoulder height, hand raised), cut out
of their black backgrounds, laid over the first drawing by their unmoved joints, scaled so the robot is a given
height with its feet on a given spot."""
import cairo
import numpy as np
from PIL import Image

from .puppet import _surface
from .walker import cutout


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
