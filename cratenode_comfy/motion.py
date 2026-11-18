"""Motion: keyframe tracks with easing, evaluated at a time in seconds.

Every scene item can carry ``anim``: a tuple of ``Track``. A track animates one
property between keyframes ((time, value), ...). Animation is visual only: it
moves, scales, fades or wipes an item after layout, so layouts never jump.

Properties (and their resting values):
    x, y      offset in canvas pixels (0)
    scale     around the item's centre (1)
    rotation  degrees around the centre (0)
    opacity   multiplies the item's opacity (1)
    blur      blur radius in pixels (0)
    wipe      how much is revealed, left to right (1 = all)

Several tracks may animate the same property (say an "in" and an "out"): the
first one holds its starting value until it begins; a later one takes over from
its first keyframe on.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

PROPS = {"x": 0.0, "y": 0.0, "scale": 1.0, "rotation": 0.0, "opacity": 1.0, "blur": 0.0, "wipe": 1.0}


def _out_bounce(t):
    n, d = 7.5625, 2.75
    if t < 1 / d:
        return n * t * t
    if t < 2 / d:
        t -= 1.5 / d
        return n * t * t + 0.75
    if t < 2.5 / d:
        t -= 2.25 / d
        return n * t * t + 0.9375
    t -= 2.625 / d
    return n * t * t + 0.984375


EASINGS = {
    "linear": lambda t: t,
    "ease in": lambda t: t ** 3,
    "ease out": lambda t: 1 - (1 - t) ** 3,
    "ease in out": lambda t: 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2,
    "back out": lambda t: 1 + 2.70158 * (t - 1) ** 3 + 1.70158 * (t - 1) ** 2,
    "elastic out": lambda t: t if t in (0, 1) else 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * 2 * math.pi / 3) + 1,
    "bounce out": _out_bounce,
    "step": lambda t: 1.0 if t >= 1 else 0.0,
}


@dataclass(frozen=True)
class Track:
    prop: str
    keys: tuple = ((0.0, 0.0), (1.0, 1.0))  # ((seconds, value), ...), sorted by time
    easing: str = "ease out"

    @property
    def start(self) -> float:
        return self.keys[0][0]

    @property
    def end(self) -> float:
        return self.keys[-1][0]

    def value(self, t: float) -> float:
        ks = self.keys
        if t <= ks[0][0]:
            return ks[0][1]
        if t >= ks[-1][0]:
            return ks[-1][1]
        ease = EASINGS.get(self.easing, EASINGS["linear"])
        for (t0, v0), (t1, v1) in zip(ks, ks[1:]):
            if t <= t1:
                f = 0.0 if t1 <= t0 else (t - t0) / (t1 - t0)
                return v0 + (v1 - v0) * ease(f)
        return ks[-1][1]


def track(prop: str, keys, easing: str = "ease out") -> Track:
    if prop not in PROPS:
        raise ValueError(f"cannot animate {prop!r}; use one of {', '.join(PROPS)}")
    ks = tuple(sorted((float(a), float(b)) for a, b in keys))
    if not ks:
        raise ValueError("a track needs at least one keyframe")
    return Track(prop, ks, easing)


def parse_keys(text: str) -> tuple:
    """``time: value`` pairs separated by lines or commas, e.g. "0: 0, 0.5: 1"."""
    out = []
    for part in re.split(r"[\n,;]+", text or ""):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(-?[\d.]+)\s*s?\s*[:=]\s*(-?[\d.]+)", part)
        if not m:
            raise ValueError(f"keyframe {part!r} is not 'seconds: value'")
        out.append((float(m.group(1)), float(m.group(2))))
    return tuple(out)


def state(anim: tuple, t: float | None) -> dict:
    """The animated property values at time t (``None``: no animation)."""
    s = dict(PROPS)
    if not anim or t is None:
        return s
    seen = set()
    for tr in anim:
        if tr.prop not in seen or t >= tr.start:
            s[tr.prop] = tr.value(t)
            seen.add(tr.prop)
    return s


def is_identity(s: dict) -> bool:
    return all(abs(s[k] - v) < 1e-9 for k, v in PROPS.items())


def anim_end(anim: tuple) -> float:
    return max((tr.end for tr in anim), default=0.0)


# ---- presets ----

PRESETS = ["fade", "fade up", "fade down", "slide from left", "slide from right", "slide from top",
           "slide from bottom", "pop", "zoom in", "wipe", "blur in", "rise and blur"]


def preset(name: str, start: float, duration: float, distance: float = 80.0, easing: str = "ease out",
           out: bool = False) -> tuple:
    """Tracks for an entrance (or, with ``out``, the matching exit) starting at ``start``."""
    a, b = start, start + max(duration, 1e-3)

    def tr(prop, hidden, shown, ease=easing):
        keys = ((a, shown), (b, hidden)) if out else ((a, hidden), (b, shown))
        return track(prop, keys, ease)

    fade = tr("opacity", 0.0, 1.0)
    d = distance
    table = {
        "fade": (fade,),
        "fade up": (fade, tr("y", d, 0.0)),
        "fade down": (fade, tr("y", -d, 0.0)),
        "slide from left": (fade, tr("x", -d, 0.0)),
        "slide from right": (fade, tr("x", d, 0.0)),
        "slide from top": (fade, tr("y", -d, 0.0)),
        "slide from bottom": (fade, tr("y", d, 0.0)),
        "pop": (fade, tr("scale", 0.6, 1.0, "back out" if not out else easing)),
        "zoom in": (fade, tr("scale", 1.25, 1.0)),
        "wipe": (tr("wipe", 0.0, 1.0),),
        "blur in": (fade, tr("blur", 24.0, 0.0)),
        "rise and blur": (fade, tr("y", d, 0.0), tr("blur", 16.0, 0.0)),
    }
    if name not in table:
        raise ValueError(f"unknown animation preset {name!r}")
    return table[name]
