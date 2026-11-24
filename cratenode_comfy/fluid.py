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

import dataclasses
import math
import random
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

# Ready-made looks. Each sets the style, colours and any controls it names; the rest
# take their defaults. Picking one in the node fills its settings in, ready to tweak.
CUSTOM = "custom"
PRESETS = {
    "Twirl": dict(style="glass", colors=["#c9c3ff", "#7a6cff", "#ff9ad5", "#ffffff", "#5b8cff"], seed=4,
                  twirl=320, twirl_radius=0.75, glass=0.15, scale=1.2),
    "Controlled": dict(style="mesh", colors=["#1a1033", "#ff5a5f", "#ffb347", "#6c5ce7", "#1a1033"], seed=11,
                       softness=0.65, warp=0.7, blobs=1),
    "Strange": dict(style="liquid", colors=["#0d1b4c", "#1e90ff", "#ff4fa3", "#ff8c42", "#ffffff"], seed=5,
                    twirl=220, twirl_radius=0.9, warp=1.3),
    "Liquid": dict(style="liquid", colors=["#2d0b5a", "#7b2ff7", "#ff2e63", "#f9a03f"], seed=7, stretch=1.4,
                   scale=1.2),
    "Generator": dict(style="mesh", colors=["#f6e7c1", "#e8b4d6", "#3a2a6b", "#f2c94c"], seed=3, blobs=2,
                      softness=0.6, warp=0.9),
    "Abstract": dict(style="liquid", colors=["#ff9a9e", "#fad0c4", "#a18cd1", "#fbc2eb", "#8fd3f4"], seed=2,
                     softness=1.4, warp=0.8, scale=1.4),
    "Color": dict(style="waves", colors=["#0b0f3a", "#1e3cff", "#ff6a00", "#ffb000"], seed=1, warp=1.3,
                  rotation=-20, blur=0.06),
    "Motion Blur": dict(style="motion blur", colors=["#6a5acd", "#ff7eb3", "#feff9c", "#7afcff"], seed=6,
                        blur_angle=20, blur=0.1),
    "Abstract Glass": dict(style="glass", colors=["#0a1a6b", "#1f6bff", "#6fe3ff", "#ffffff", "#7b2ff7"], seed=9,
                           scale=1.3),
    "Aurora": dict(style="waves", colors=["#03071e", "#00f5d4", "#7b2ff7", "#00bbf9"], seed=8, stretch=2.0,
                   rotation=-10, blur=0.12, vignette=0.4),
    "Sunset Silk": dict(style="liquid", colors=["#2b1055", "#a83279", "#ff5f6d", "#ffc371"], seed=12,
                        stretch=2.0, softness=1.3),
    "Lava": dict(style="strange", colors=["#1a0000", "#ff2a00", "#ffb000", "#3d0000"], seed=13, contrast=1.15,
                 scale=1.3),
    "Neon Marble": dict(style="strange", colors=["#0b0033", "#ff00e5", "#00f0ff", "#1400ff"], seed=14),
    "Holographic": dict(style="glass", colors=["#ffd1f7", "#c2fffd", "#d8c2ff", "#fff7c2", "#a0e9ff"], seed=15,
                        saturation=1.3, scale=1.4),
    "Ocean": dict(style="liquid", colors=["#001233", "#0353a4", "#00b4d8", "#90e0ef", "#caf0f8"], seed=16,
                  stretch=1.6),
    "Midnight": dict(style="mesh", colors=["#0b0b1f", "#2c1a5a", "#7b2ff7", "#0f3460", "#0b0b1f"], seed=17,
                     vignette=0.5, grain=0.05, blobs=2, softness=0.7),
    "Candy": dict(style="mesh", colors=["#ff9ff3", "#feca57", "#48dbfb", "#ff6b6b", "#1dd1a1"], seed=18, blobs=2,
                  softness=0.55, warp=0.9),
    "Mono Silk": dict(style="liquid", colors=["#0e0e0e", "#4a4a4a", "#b5b5b5", "#ffffff"], seed=19, stretch=1.5,
                      softness=1.4),
}
MAX_COLORS = 6


def _defaults() -> dict:
    return {f.name: f.default for f in dataclasses.fields(FluidGradient) if f.name not in ("kind", "stops", "angle")}


def _with_colors(out: dict, cols) -> dict:
    cols = list(cols)[:MAX_COLORS]
    out.update({f"color_{i + 1}": (cols[i] if i < len(cols) else "") for i in range(MAX_COLORS)})
    return out


def preset_values(name: str) -> dict:
    """A preset as the node's own inputs: style, seed, color_1..6 and every control."""
    p = dict(PRESETS[name])
    out = _with_colors(_defaults(), p.pop("colors"))
    out.update(p)
    return out


# Random looks: a style and colours that go together, with every other setting kept in a
# range that still looks good for that style (wide ranges on everything at once turn
# into noise or mud). Brightness, hue shift and heavy grain are left alone.
_STYLE_WEIGHTS = {"liquid": 3.0, "glass": 2.0, "mesh": 2.0, "twirl": 1.5, "strange": 1.0, "waves": 1.2,
                  "motion blur": 1.2}
_HARMONY_WEIGHTS = {"analogous": 2.0, "complementary": 1.5, "split complementary": 1.5, "warm and cool": 1.5,
                    "triadic": 1.0, "tetradic": 0.7, "monochromatic": 0.6}
_COLOR_STYLE_WEIGHTS = {"vivid": 2.5, "jewel": 1.5, "pastel": 1.5, "any": 1.2, "neon": 1.0, "dark": 0.5}
# the base hue: these gradients sing in blues, purples, pinks and oranges; greens and
# yellows are allowed but rarer
_FAMILY_WEIGHTS = {"blue": 2.0, "purple": 2.0, "pink": 2.0, "cool": 1.5, "warm": 1.2, "orange": 1.2,
                   "red": 1.0, "teal": 1.0, "any": 0.8, "green": 0.4, "yellow": 0.3}
_RAMP_STYLES = {"liquid", "strange", "waves", "glass", "motion blur"}  # colours run dark to light
# mesh and twirl blend colours across space, so opposite hues average to grey-brown:
# give them neighbouring hues and full colour
_BLEND_HARMONY_WEIGHTS = {"analogous": 3.0, "split complementary": 1.0, "monochromatic": 1.0, "warm and cool": 0.5}
_BLEND_COLOR_STYLE_WEIGHTS = {"vivid": 2.5, "jewel": 1.5, "pastel": 1.5, "neon": 1.0}


def _pick(rng, weights: dict):
    return rng.choices(list(weights), weights=list(weights.values()))[0]


def _luma(hex_color: str) -> float:
    from .render import parse_color

    r, g, b, _ = parse_color(hex_color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _lively(cols: list[str], family: str) -> bool:
    """Enough light-to-dark range and colour to make a gradient (not flat or grey), and
    no muddy mixes: at most one green/olive unless green was asked for, and no browns
    (a dark orange blended through these gradients reads as mud)."""
    import colorsys

    from .render import parse_color

    lumas = [_luma(c) for c in cols]
    hls = [colorsys.rgb_to_hls(*parse_color(c)[:3]) for c in cols]
    if max(lumas) - min(lumas) < 0.3 or sum(s for _, _, s in hls) / len(hls) < 0.35:
        return False
    greens = sum(1 for h, _, s in hls if 55 <= h * 360 <= 150 and s > 0.35)
    browns = sum(1 for h, l, s in hls if (15 <= h * 360 <= 60 and l < 0.38 and s > 0.25)
                 or ((h * 360 < 15 or h * 360 > 345) and l < 0.32 and s < 0.7))  # dull dark reds too
    return browns == 0 and (greens <= 1 or family in ("green", "teal"))


def random_colors(rng, style: str) -> list[str]:
    """3-5 colours from a colour harmony (the Palette Generator's rules), kept lively."""
    from . import palettegen as pg

    blend = style in ("mesh", "twirl")
    n = rng.choice([4, 4, 5, 5]) if blend else rng.choice([3, 4, 4, 5, 5])
    harmonies = _BLEND_HARMONY_WEIGHTS if blend else _HARMONY_WEIGHTS
    styles = _BLEND_COLOR_STYLE_WEIGHTS if blend else _COLOR_STYLE_WEIGHTS
    cols = []
    for _ in range(24):
        family = _pick(rng, _FAMILY_WEIGHTS)
        cols = pg.to_hex_list(pg.generate(rng.randrange(2**31), _pick(rng, harmonies), family,
                                          _pick(rng, styles)))[:n]
        if _lively(cols, family):
            break
    if style in _RAMP_STYLES:
        cols.sort(key=_luma)
    return cols


def random_look(seed: int) -> dict:
    """A random look for one seed, as the node's own inputs (like ``preset_values``)."""
    rng = random.Random(int(seed))
    if rng.random() < 0.35:  # start from a tuned preset, with a new pattern (and maybe new colours)
        out = preset_values(rng.choice(list(PRESETS)))
        out["seed"] = rng.randrange(2**31)
        out["evolve"] = round(rng.uniform(0, 100), 2)
        if rng.random() < 0.5:
            _with_colors(out, random_colors(rng, out["style"]))
        return out

    style = _pick(rng, _STYLE_WEIGHTS)
    out = _with_colors(_defaults(), random_colors(rng, style))
    lo_stretch, hi_stretch = math.log(0.8), math.log(2.0)
    out.update(
        style=style,
        seed=rng.randrange(2**31),
        evolve=round(rng.uniform(0, 100), 2),
        scale=round(rng.uniform(0.9, 1.6), 2),
        warp=round(rng.uniform(0.7, 1.3), 2),
        detail=4 if rng.random() < 0.2 else 3,
        stretch=round(math.exp(rng.uniform(lo_stretch, hi_stretch)), 2),
        rotation=round(rng.uniform(-180, 180)) if rng.random() < 0.5 else 0.0,
        grain=round(rng.uniform(0.02, 0.04), 3),
        saturation=round(rng.uniform(1.0, 1.15), 2),
        contrast=round(rng.uniform(1.0, 1.1), 2),
        vignette=round(rng.uniform(0.2, 0.5), 2) if rng.random() < 0.3 else 0.0,
    )
    if style == "mesh":
        out.update(softness=round(rng.uniform(0.55, 0.9), 2), blobs=rng.randint(1, 3),
                   warp=round(rng.uniform(0.6, 1.2), 2))
    elif style == "twirl":
        out.update(softness=round(rng.uniform(0.6, 1.0), 2), twirl=round(rng.uniform(-200, 200)),
                   twirl_x=round(rng.uniform(0.35, 0.65), 2), twirl_y=round(rng.uniform(0.35, 0.65), 2),
                   twirl_radius=round(rng.uniform(0.5, 0.9), 2))
    elif style == "liquid":
        out.update(softness=round(rng.uniform(1.0, 1.6), 2), bands=1.0 if rng.random() < 0.15 else 0.0)
    elif style == "strange":
        out.update(scale=round(rng.uniform(1.1, 1.6), 2), warp=round(rng.uniform(0.8, 1.1), 2),
                   softness=round(rng.uniform(1.0, 1.3), 2))
    elif style == "waves":
        out.update(bands=float(rng.randint(0, 2)), warp=round(rng.uniform(0.8, 1.5), 2),
                   blur=round(rng.uniform(0.0, 0.08), 2))
    elif style == "motion blur":
        out.update(blur=round(rng.uniform(0.05, 0.2), 2), blur_angle=round(rng.uniform(-180, 180)))
    elif style == "glass":
        out.update(glass=round(rng.uniform(0.0, 0.3), 2), scale=round(rng.uniform(1.1, 1.6), 2))
        if rng.random() < 0.3:
            out.update(twirl=round(rng.uniform(150, 400)), twirl_radius=round(rng.uniform(0.6, 0.9), 2))
    return out


def values_gradient(v: dict) -> "FluidGradient":
    """The FluidGradient for a dict of node inputs (from a preset or a random look)."""
    from .render import parse_color

    v = dict(v)
    texts = [v.pop(f"color_{i}") for i in range(1, MAX_COLORS + 1)]
    cols = [parse_color(c) for c in texts if c]
    stops = tuple((i / (len(cols) - 1), c) for i, c in enumerate(cols))
    return FluidGradient(stops=stops, **v)


def preset_gradient(name: str) -> "FluidGradient":
    """The FluidGradient a preset makes (for previews and tests)."""
    return values_gradient(preset_values(name))


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
