"""Palette generator: five colours that go together, by colour harmony (analogous,
complementary, triadic ...), within a colour family and style (the same families and
styles as Random Colour). No ComfyUI imports.

A harmony picks hues from one base hue; the style sets how saturated and light they are,
and lightness is spread across the five so they read as a palette (a dark, some mids, a
light) rather than five similar tones. "random" is five unrelated colours kept apart.
"""

from __future__ import annotations

import colorsys
import random

from . import color as col
from . import randcolor as rc

COUNT = 5

# hue offsets (degrees) from the base hue, one per colour
HARMONIES = {
    "random": None,
    "analogous": (0, -30, 30, -15, 15),
    "complementary": (0, 180, 0, 180, 0),
    "split complementary": (0, 150, 210, 0, 180),
    "triadic": (0, 120, 240, 0, 120),
    "tetradic": (0, 90, 180, 270, 0),
    "monochromatic": (0, 0, 0, 0, 0),
    "warm and cool": (0, 180, 30, 210, 0),
}


def _spread(rng: random.Random, lo: float, hi: float, n: int) -> list[float]:
    """n lightness values spread from lo to hi (with a little jitter), shuffled."""
    if n == 1:
        return [rng.uniform(lo, hi)]
    step = (hi - lo) / (n - 1)
    vals = [min(hi, max(lo, lo + i * step + rng.uniform(-0.25, 0.25) * step)) for i in range(n)]
    rng.shuffle(vals)
    return vals


def generate(seed: int, harmony: str = "random", family: str = "any", style: str = "any") -> list[tuple]:
    """Five RGBA colours for one seed."""
    if harmony not in HARMONIES:
        raise ValueError(f"unknown harmony {harmony!r}; one of {', '.join(HARMONIES)}")
    if family not in rc.FAMILIES:
        raise ValueError(f"unknown colour family {family!r}; one of {', '.join(rc.FAMILIES)}")
    if style not in rc.STYLES:
        raise ValueError(f"unknown style {style!r}; one of {', '.join(rc.STYLES)}")
    if harmony == "random":
        colors, _ = rc.generate(seed, COUNT, family, style, min_difference=18.0)
        return colors
    rng = random.Random(int(seed))
    base = rc._hue(rng, family)
    (s0, s1), (l0, l1) = rc._ranges(family, style)
    # a palette needs some range in lightness even for a narrow style (keep it in bounds)
    if l1 - l0 < 0.3:
        mid = (l0 + l1) / 2
        l0, l1 = max(0.06, mid - 0.18), min(0.94, mid + 0.18)
    if harmony == "monochromatic":
        l0, l1 = max(0.08, l0 - 0.1), min(0.94, l1 + 0.1)
    lights = _spread(rng, l0, l1, COUNT)
    out = []
    for off, light in zip(HARMONIES[harmony], lights):
        hue = (base + off + rng.uniform(-6, 6)) % 360
        sat = rng.uniform(s0, s1)
        r, g, b = colorsys.hls_to_rgb(hue / 360, light, sat)
        out.append((r, g, b, 1.0))
    return out


def to_hex_list(colors) -> list[str]:
    return [col.to_hex(c) for c in colors]
