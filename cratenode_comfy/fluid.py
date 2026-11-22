"""Fluid gradients: procedural colour fields (mesh blobs, liquid marbling, twirls, waves,
motion blur, glass) used as a fill like any other gradient.

``FluidGradient`` is a ``Gradient`` whose ``stops`` are its colours (evenly spaced), so
everything that handles gradients handles it too: recolouring swaps its colours, fill
opacity fades them, templates save it, text and canvas backgrounds take it. Only the
picture differs: ``shader`` renders the field with numpy for the box it fills.

The field is worked out in box-relative units (the box height is 1), so a fill looks
the same at any size; it is computed at a working size, smoothed up to the box, and
grain is added at full size. The same settings and seed always give the same picture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import skia

from . import scene as sc

STYLES = ["mesh", "liquid", "twirl", "strange", "waves", "motion blur", "glass"]

# What each style adds on top of the user's controls (which add to / multiply these).
_BASE = {
    "mesh": dict(warp=0.35, twirl=0.0, blur=0.0, glass=0.0),
    "liquid": dict(warp=1.0, twirl=0.0, blur=0.0, glass=0.0),
    "twirl": dict(warp=0.25, twirl=420.0, blur=0.0, glass=0.0),
    "strange": dict(warp=1.4, twirl=0.0, blur=0.0, glass=0.0),
    "waves": dict(warp=1.0, twirl=0.0, blur=0.0, glass=0.0),
    "motion blur": dict(warp=0.6, twirl=0.0, blur=0.18, glass=0.0),
    "glass": dict(warp=0.9, twirl=0.0, blur=0.0, glass=0.85),
}

WORK = 560  # long side of the working grid (the field is smooth; it is scaled up after)
MAX_OUT = 2048  # long side of the rendered fill


@dataclass(frozen=True)
class FluidGradient(sc.Gradient):
    """A procedural gradient. ``stops`` holds the colours (position, rgba)."""

    kind: str = "fluid"
    style: str = "mesh"
    seed: int = 0
    scale: float = 1.0  # feature size: larger = bigger, calmer shapes
    warp: float = 1.0  # how much the shapes flow and bend (x the style's own amount)
    detail: int = 3  # noise octaves: more = finer ripples in the flow
    blobs: int = 2  # mesh points per colour
    softness: float = 1.0  # how softly colours blend (lower = crisper edges)
    twirl: float = 0.0  # degrees, added to the style's own twirl
    twirl_x: float = 0.5  # twirl centre, 0..1 across the box
    twirl_y: float = 0.5
    twirl_radius: float = 0.6  # in box heights
    rotation: float = 0.0  # degrees
    stretch: float = 1.0  # > 1 stretches the shapes sideways, < 1 upright
    bands: float = 0.0  # extra repeats of the colours (ripples / stripes)
    blur: float = 0.0  # motion blur length in box heights, added to the style's own
    blur_angle: float = 0.0  # degrees, 0 = left to right
    glass: float = 0.0  # glassy highlights and refraction, added to the style's own
    grain: float = 0.02  # film grain (also hides banding)
    brightness: float = 0.0  # -1..1
    contrast: float = 1.0
    saturation: float = 1.0
    hue_shift: float = 0.0  # degrees
    vignette: float = 0.0  # darker edges, 0..1
    evolve: float = 0.0  # moves through the noise: animate it for a flowing gradient

    def shader(self, x0: float, y0: float, x1: float, y1: float) -> skia.Shader:
        w, h = max(1.0, x1 - x0), max(1.0, y1 - y0)
        k = min(1.0, MAX_OUT / max(w, h))
        ow, oh = max(2, round(w * k)), max(2, round(h * k))
        img = _image(self, ow, oh)
        m = skia.Matrix.Translate(x0, y0)
        m.preScale(w / ow, h / oh)
        return img.makeShader(skia.TileMode.kClamp, skia.TileMode.kClamp,
                              skia.SamplingOptions(skia.FilterMode.kLinear), m)


@lru_cache(maxsize=24)
def _image(g: FluidGradient, ow: int, oh: int) -> skia.Image:
    from .render import image_from_rgba

    return image_from_rgba(render(g, ow, oh))


# ---- noise ----

def _table(seed: int) -> np.ndarray:
    return np.random.default_rng(seed & 0xFFFFFFFF).random((256, 256)).astype(np.float32)


def _noise(x, y, t):
    """Smooth value noise in 0..1 (quintic fade over a 256 x 256 random lattice)."""
    xf, yf = np.floor(x), np.floor(y)
    fx, fy = x - xf, y - yf
    xi, yi = xf.astype(np.int64) & 255, yf.astype(np.int64) & 255
    xj, yj = (xi + 1) & 255, (yi + 1) & 255
    u = fx * fx * fx * (fx * (fx * 6 - 15) + 10)
    v = fy * fy * fy * (fy * (fy * 6 - 15) + 10)
    a, b, c, d = t[yi, xi], t[yi, xj], t[yj, xi], t[yj, xj]
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def _fbm(x, y, t, octaves: int, evolve: float = 0.0):
    """Layered noise in about 0..1; each layer is turned so no grid shows."""
    total, amp, norm = 0.0, 0.5, 0.0
    ca, sa = math.cos(0.6), math.sin(0.6)
    for i in range(max(1, int(octaves))):
        ex, ey = evolve * (0.31 + 0.11 * i), evolve * (0.23 - 0.07 * i)
        total = total + amp * _noise(x + ex + 17.3 * i, y + ey + 9.1 * i, t)
        norm += amp
        x, y = (x * ca - y * sa) * 2.03, (x * sa + y * ca) * 2.03
        amp *= 0.5
    return total / norm


def _normalise(v):
    lo, hi = np.percentile(v, (1.5, 98.5))
    return np.clip((v - lo) / max(1e-6, hi - lo), 0.0, 1.0)


# ---- colour ----

def _ramp(t, stops) -> np.ndarray:
    """RGBA along the colour stops for t in 0..1."""
    pos = np.array([p for p, _ in stops], np.float32)
    cols = np.array([c for _, c in stops], np.float32)
    return np.stack([np.interp(t, pos, cols[:, ch]) for ch in range(4)], axis=-1).astype(np.float32)


def _mirror(t):
    """0..1..0 repeating, so cycling colours never jump."""
    f = np.mod(t, 2.0)
    return np.where(f > 1.0, 2.0 - f, f)


def _sample(img, xs, ys):
    """Bilinear lookup of img (H x W x C) at pixel coordinates, clamped at the edges."""
    h, w = img.shape[:2]
    xs, ys = np.clip(xs, 0, w - 1.001), np.clip(ys, 0, h - 1.001)
    x0, y0 = xs.astype(np.int64), ys.astype(np.int64)
    fx, fy = (xs - x0)[..., None], (ys - y0)[..., None]
    a, b = img[y0, x0], img[y0, x0 + 1]
    c, d = img[y0 + 1, x0], img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _adjust(rgb, g: FluidGradient):
    if g.hue_shift:
        a = math.radians(g.hue_shift)
        c, s = math.cos(a), math.sin(a)
        # rotate around the grey axis (YIQ)
        to_yiq = np.array([[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]], np.float32)
        rot = np.array([[1, 0, 0], [0, c, -s], [0, s, c]], np.float32)
        m = np.linalg.inv(to_yiq) @ rot @ to_yiq
        rgb = rgb @ m.T.astype(np.float32)
    if g.saturation != 1.0:
        lum = (rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32))[..., None]
        rgb = lum + (rgb - lum) * g.saturation
    if g.contrast != 1.0:
        rgb = (rgb - 0.5) * g.contrast + 0.5
    if g.brightness:
        rgb = rgb + g.brightness * 0.5
    return rgb


# ---- the field ----

def render(g: FluidGradient, ow: int, oh: int) -> np.ndarray:
    """H x W x 4 float (straight alpha) for an ow x oh box."""
    from PIL import Image

    base = _BASE.get(g.style, _BASE["mesh"])
    stops = tuple(sorted(g.stops, key=lambda s: s[0])) or ((0.0, (0, 0, 0, 1)), (1.0, (1, 1, 1, 1)))
    k = min(1.0, WORK / max(ow, oh))
    ww, wh = max(8, round(ow * k)), max(8, round(oh * k))
    aspect = ow / oh
    t = _table(g.seed)

    # box-relative coordinates: height 1, centred
    xs = (np.arange(ww, dtype=np.float32) + 0.5) / wh - aspect / 2
    ys = (np.arange(wh, dtype=np.float32) + 0.5) / wh - 0.5
    x, y = np.meshgrid(xs, ys)
    if g.rotation:
        a = math.radians(-g.rotation)
        x, y = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
    twirl = base["twirl"] + g.twirl
    if twirl:
        cx, cy = (g.twirl_x - 0.5) * aspect, g.twirl_y - 0.5
        dx, dy = x - cx, y - cy
        r = np.sqrt(dx * dx + dy * dy)
        ang = math.radians(twirl) * np.clip(1.0 - r / max(0.01, g.twirl_radius), 0.0, 1.0) ** 2
        ca, sa = np.cos(ang), np.sin(ang)
        x, y = cx + dx * ca - dy * sa, cy + dx * sa + dy * ca
    x = x / max(0.05, g.stretch)
    sc_ = max(0.05, g.scale)
    x, y = x / sc_, y / sc_
    warp = base["warp"] * g.warp
    det = max(1, min(8, int(g.detail)))
    soft = max(0.05, g.softness)

    if g.style in ("mesh", "twirl"):
        rgba, height = _mesh(g, x, y, t, warp, det, soft, aspect / sc_, stops)
    elif g.style == "waves":
        n = _fbm(x * 0.8, y * 0.8, t, det, g.evolve) - 0.5
        f = 1.5 + g.bands
        v = 0.5 + 0.5 * np.sin(2 * math.pi * f * (y + warp * 0.6 * n) + 2.0 * warp * n)
        v = 0.5 + (v - 0.5) / soft
        rgba, height = _ramp(np.clip(v, 0, 1), stops), v
    else:  # liquid, strange, glass, motion blur: warped noise (fbm of fbm)
        p = 0.9
        q1 = _fbm(x * p, y * p, t, det, g.evolve)
        q2 = _fbm(x * p + 5.2, y * p + 1.3, t, det, g.evolve)
        w4 = 2.6 * warp
        r1 = _fbm(x * p + w4 * q1 + 1.7, y * p + w4 * q2 + 9.2, t, det, g.evolve)
        r2 = _fbm(x * p + w4 * q1 + 8.3, y * p + w4 * q2 + 2.8, t, det, g.evolve)
        f = _fbm(x * p + w4 * r1, y * p + w4 * r2, t, det, g.evolve)
        v = _normalise(0.7 * f + 0.3 * r1)
        if g.style == "strange" or g.bands:
            v = _mirror(v * (1.0 + (2.0 if g.style == "strange" else 0.0) + g.bands))
        v = np.clip(0.5 + (v - 0.5) / soft, 0, 1)
        rgba, height = _ramp(v, stops), v

    # glass: shade the field as a smooth surface, bend the colours under it, add highlights
    glass = base["glass"] + g.glass
    if glass > 0:
        hb = _smooth(height.astype(np.float32), max(1, round(wh / 90)))
        gy, gx = np.gradient(hb * wh * 0.12 * (1 + glass))
        nz = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
        nx, ny = -gx * nz, -gy * nz
        jj, ii = np.meshgrid(np.arange(ww, dtype=np.float32), np.arange(wh, dtype=np.float32))
        rgba = _sample(rgba, jj + nx * wh * 0.06 * glass, ii + ny * wh * 0.06 * glass)
        lx, ly, lz = -0.45, -0.6, 0.66
        hx, hy, hz = lx, ly, lz + 1.0
        hn = math.sqrt(hx * hx + hy * hy + hz * hz)
        spec = np.clip((nx * hx + ny * hy + nz * hz) / hn, 0, 1) ** 40
        rim = (1.0 - nz) ** 2
        shade = 1.0 - 0.35 * glass * (1.0 - np.clip(nx * lx + ny * ly + nz * lz, 0, 1))
        rgb = rgba[..., :3] * shade[..., None] + (spec * 0.9 * glass + rim * 0.25 * glass)[..., None]
        rgba = np.concatenate([rgb, rgba[..., 3:]], axis=-1)

    # motion blur along an angle
    blur = base["blur"] + g.blur
    if blur > 0:
        n = 28
        a = math.radians(g.blur_angle)
        length = blur * wh
        jj, ii = np.meshgrid(np.arange(ww, dtype=np.float32), np.arange(wh, dtype=np.float32))
        acc = np.zeros_like(rgba)
        for s in np.linspace(-0.5, 0.5, n):
            acc += _sample(rgba, jj + s * length * math.cos(a), ii + s * length * math.sin(a))
        rgba = acc / n

    rgb = _adjust(rgba[..., :3], g)
    if g.vignette > 0:
        vx = (np.arange(ww, dtype=np.float32) + 0.5) / ww * 2 - 1
        vy = (np.arange(wh, dtype=np.float32) + 0.5) / wh * 2 - 1
        d = np.sqrt(vx[None, :] ** 2 + vy[:, None] ** 2) / math.sqrt(2)
        rgb = rgb * (1.0 - g.vignette * np.clip(d, 0, 1) ** 1.6)[..., None]
    rgba = np.concatenate([np.clip(rgb, 0, 1), np.clip(rgba[..., 3:], 0, 1)], axis=-1).astype(np.float32)

    # up to the box size (smooth), then grain at full size
    if (ww, wh) != (ow, oh):
        chans = [np.asarray(Image.fromarray(rgba[..., c]).resize((ow, oh), Image.BICUBIC)) for c in range(4)]
        rgba = np.stack(chans, axis=-1)
    if g.grain > 0:
        rng = np.random.default_rng((g.seed * 7919 + 17) & 0xFFFFFFFF)
        noise = (rng.random((oh, ow), dtype=np.float32) - 0.5) * (0.25 * g.grain)
        rgba[..., :3] += noise[..., None]
    return np.clip(rgba, 0, 1).astype(np.float32)


def _smooth(a: np.ndarray, r: int) -> np.ndarray:
    """Three box blurs of radius r (close to a gaussian), edges held."""
    for _ in range(3):
        for axis in (0, 1):
            pad = [(0, 0), (0, 0)]
            pad[axis] = (r + 1, r)
            c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
            hi = np.take(c, np.arange(2 * r + 1, c.shape[axis]), axis=axis)
            lo = np.take(c, np.arange(0, c.shape[axis] - 2 * r - 1), axis=axis)
            a = ((hi - lo) / (2 * r + 1)).astype(np.float32)
    return a


def _mesh(g, x, y, t, warp, det, soft, half_w, stops):
    """Colour blobs: each colour sits at a few seeded points and spreads softly; the
    space between them is bent by noise so the blends flow."""
    rng = np.random.default_rng((g.seed * 31 + 7) & 0xFFFFFFFF)
    colors = [c for _, c in stops]
    blobs = max(1, min(6, int(g.blobs)))
    pts = []
    for i in range(blobs):
        order = rng.permutation(len(colors))
        for j in order:
            pts.append((rng.uniform(-half_w * 0.55, half_w * 0.55), rng.uniform(-0.55, 0.55) / max(0.05, g.scale),
                        colors[j]))
    if warp:
        wx = _fbm(x * 1.8 + 3.1, y * 1.8, t, det, g.evolve) - 0.5
        wy = _fbm(x * 1.8, y * 1.8 + 7.7, t, det, g.evolve) - 0.5
        x, y = x + warp * 0.9 * wx, y + warp * 0.9 * wy
    if g.bands:
        x, y = x + 0.04 * np.sin(y * 2 * math.pi * (1 + g.bands)), y + 0.04 * np.sin(x * 2 * math.pi * (1 + g.bands))
    sigma = 0.22 * soft * (1.0 + 0.6 / blobs) / max(0.05, g.scale) ** 0.5
    acc = np.zeros(x.shape + (4,), np.float32)
    wsum = np.zeros(x.shape, np.float32)
    for px, py, c in pts:
        wgt = np.exp(-((x - px) ** 2 + (y - py) ** 2) / (2 * sigma * sigma)) + 1e-6
        acc += wgt[..., None] * np.array(c, np.float32)
        wsum += wgt
    rgba = acc / wsum[..., None]
    height = rgba[..., :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    return rgba.astype(np.float32), height
