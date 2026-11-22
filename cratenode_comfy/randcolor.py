"""Random colours within limits: a colour family (hue range), a style (how saturated and
how light), a perceived-brightness range, and optionally a minimum contrast against a
background. No ComfyUI imports.

Colours are drawn in HSL (hue, saturation, lightness), then checked against perceived
brightness (CIE L*, 0 = black, 100 = white), which treats yellow and blue fairly where
HSL lightness doesn't. Several colours (a palette) are kept apart so they don't repeat.
"""

from __future__ import annotations

import colorsys
import random

import numpy as np

from . import color as col

# hue ranges in degrees (start, end), going round the wheel; None = any hue
FAMILIES = {
    "any": None,
    "red": (345, 15),
    "orange": (15, 40),
    "yellow": (42, 64),
    "green": (75, 155),
    "teal": (160, 195),
    "blue": (195, 240),
    "purple": (250, 290),
    "pink": (290, 345),
    "warm": (330, 65),
    "cool": (160, 290),
    "brown": (15, 45),
    "earth": (20, 100),
    "neutral": None,
}
# (saturation range, lightness range) in HSL, 0..1
STYLES = {
    "any": ((0.15, 1.0), (0.15, 0.88)),
    "vivid": ((0.75, 1.0), (0.42, 0.6)),
    "pastel": ((0.45, 0.85), (0.78, 0.9)),
    "muted": ((0.12, 0.38), (0.32, 0.66)),
    "dark": ((0.45, 0.9), (0.1, 0.28)),
    "light": ((0.3, 0.7), (0.72, 0.9)),
    "neon": ((0.95, 1.0), (0.5, 0.6)),
    "jewel": ((0.6, 0.9), (0.24, 0.4)),
}
# styles that also limit perceived brightness (CIE L*), since HSL lightness alone lets a
# "dark" yellow look bright; combined with the user's range where the two overlap
STYLE_BRIGHTNESS = {"dark": (8.0, 34.0), "pastel": (78.0, 93.0), "light": (72.0, 92.0), "jewel": (22.0, 50.0)}
# families that also set saturation / lightness, whatever the style says
_FAMILY_SL = {
    "brown": ((0.3, 0.65), (0.15, 0.42)),
    "earth": ((0.18, 0.5), (0.2, 0.55)),
    "neutral": ((0.0, 0.08), (0.05, 0.95)),
}


def lightness(rgb) -> float:
    """Perceived brightness, CIE L* (0 = black, 100 = white)."""
    return float(col.srgb_to_lab(np.array([rgb[:3]], dtype=np.float64))[0, 0])


def _lab(rgb) -> np.ndarray:
    return col.srgb_to_lab(np.array([rgb[:3]], dtype=np.float64))[0]


def _hue(rng: random.Random, family: str) -> float:
    span = FAMILIES.get(family)
    if span is None:
        return rng.uniform(0, 360)
    a, b = span
    width = (b - a) % 360 or 360
    return (a + rng.uniform(0, width)) % 360


def _ranges(family: str, style: str):
    s, l = STYLES[style]
    if family in _FAMILY_SL:
        fs, fl = _FAMILY_SL[family]
        # keep the family's own range, narrowed by the style where they overlap
        s = (max(s[0], fs[0]), min(s[1], fs[1])) if max(s[0], fs[0]) <= min(s[1], fs[1]) else fs
        l = (max(l[0], fl[0]), min(l[1], fl[1])) if max(l[0], fl[0]) <= min(l[1], fl[1]) else fl
    return s, l


def _candidate(rng: random.Random, family: str, style: str):
    (s0, s1), (l0, l1) = _ranges(family, style)
    h = _hue(rng, family)
    r, g, b = colorsys.hls_to_rgb(h / 360, rng.uniform(l0, l1), rng.uniform(s0, s1))
    return (r, g, b, 1.0)


def _fit_brightness(c, lo: float, hi: float, rng: random.Random, lrange=(0.0, 1.0)):
    """The same hue and saturation with HSL lightness moved towards a random L* in lo..hi,
    without leaving the style's lightness range (so a pastel stays a pastel)."""
    h, l, s = colorsys.rgb_to_hls(*c[:3])
    target = rng.uniform(lo, hi)
    a, b = lrange
    for _ in range(30):  # L* rises with HSL lightness: bisect
        m = (a + b) / 2
        if lightness(colorsys.hls_to_rgb(h, m, s)) < target:
            a = m
        else:
            b = m
    r, g, bb = colorsys.hls_to_rgb(h, (a + b) / 2, s)
    return (r, g, bb, 1.0)


def generate(seed: int, count: int = 1, family: str = "any", style: str = "any", min_brightness: float = 0.0,
             max_brightness: float = 100.0, against=None, min_contrast: float = 0.0,
             min_difference: float = 12.0) -> tuple[list[tuple], list[str]]:
    """(colours, notes) for one seed: ``count`` colours meeting every limit it can.

    ``against`` is an RGBA background; ``min_contrast`` a WCAG ratio (0 = no check).
    ``min_difference`` keeps colours of a palette apart (CIE delta E). When the limits
    can't all be met, the closest colour found is used and a note says what was missed."""
    if family not in FAMILIES:
        raise ValueError(f"unknown colour family {family!r}; one of {', '.join(FAMILIES)}")
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; one of {', '.join(STYLES)}")
    lo, hi = sorted((float(min_brightness), float(max_brightness)))
    if style in STYLE_BRIGHTNESS:
        s_lo, s_hi = STYLE_BRIGHTNESS[style]
        if max(lo, s_lo) <= min(hi, s_hi):  # otherwise the user's range wins
            lo, hi = max(lo, s_lo), min(hi, s_hi)
    rng = random.Random(int(seed))
    lrange = _ranges(family, style)[1]
    out, labs, notes = [], [], []
    for k in range(max(1, int(count))):
        best, best_cost = None, None
        for attempt in range(600):
            c = _candidate(rng, family, style)
            L = lightness(c)
            if not lo <= L <= hi and attempt % 3 == 0:
                c = _fit_brightness(c, lo, hi, rng, lrange)  # often the hue and saturation are right
                L = lightness(c)
            cost = max(0.0, lo - L) + max(0.0, L - hi)
            if against is not None and min_contrast > 0:
                cost += max(0.0, min_contrast - col.contrast(c, against)) * 10
            lab = _lab(c)
            near = min((float(np.linalg.norm(lab - x)) for x in labs), default=1e9)
            cost += max(0.0, min_difference - near) * 0.5
            if best_cost is None or cost < best_cost:
                best, best_cost = c, cost
            if cost == 0:
                break
        out.append(best)
        labs.append(_lab(best))
        if best_cost:
            missed = []
            L = lightness(best)
            if not lo - 0.5 <= L <= hi + 0.5:
                missed.append(f"brightness {L:.0f} (wanted {lo:.0f}-{hi:.0f})")
            if against is not None and min_contrast > 0 and col.contrast(best, against) < min_contrast:
                missed.append(f"contrast {col.contrast(best, against):.2f}:1 (wanted {min_contrast:g}:1)")
            near = min((float(np.linalg.norm(labs[-1] - x)) for x in labs[:-1]), default=1e9)
            if near < min_difference:
                missed.append("close to another colour")
            if missed:
                notes.append(f"colour {k + 1}: " + ", ".join(missed))
    return out, notes


def describe(c, against=None) -> str:
    h, l, s = colorsys.rgb_to_hls(*c[:3])
    text = f"{col.to_hex(c)}  hue {h * 360:.0f}, sat {s * 100:.0f}%, brightness {lightness(c):.0f}"
    if against is not None:
        r = col.contrast(c, against)
        text += f", {r:.2f}:1 on {col.to_hex(against)} ({col.wcag_grade(r)})"
    return text
