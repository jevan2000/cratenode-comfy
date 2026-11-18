"""CMYK colour management with Pillow's ImageCms (littleCMS).

``CMYK(profile)`` converts sRGB to the CMYK of an ICC output profile (say your
printer's, or U.S. Web Coated SWOP), for images and for single colours, and back
for a soft proof. Without a profile it falls back to the uncalibrated formula
(K = 1 - max(R, G, B)) and says so.

Exact values: ``overrides`` map RGB colours to the CMYK you want printed (brand
colours, 0/0/0/100 black). Vector colours (text, shapes, gradient stops) use them;
images go through the profile only, so edges and shadows stay continuous.

No ICC profile ships with this package: point the ``cmyk_profile`` config at one.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageCms

INTENTS = {
    "relative colorimetric": ImageCms.Intent.RELATIVE_COLORIMETRIC,
    "perceptual": ImageCms.Intent.PERCEPTUAL,
    "saturation": ImageCms.Intent.SATURATION,
    "absolute colorimetric": ImageCms.Intent.ABSOLUTE_COLORIMETRIC,
}
PURE_BLACK = ((0, 0, 0), (0.0, 0.0, 0.0, 1.0))


def _u8(rgb) -> tuple:
    return tuple(int(round(max(0.0, min(1.0, float(v))) * 255)) for v in rgb[:3])


class CMYK:
    def __init__(self, profile: str | Path | None = None, intent: str = "relative colorimetric",
                 black_point: bool = True, overrides: list | None = None, pure_black: bool = True):
        self.path = Path(profile) if profile else None
        self.overrides: dict[tuple, tuple] = {}
        if pure_black:
            self.overrides[PURE_BLACK[0]] = PURE_BLACK[1]
        for rgb, c in overrides or []:
            self.overrides[_u8(rgb)] = tuple(float(v) for v in c)
        self.icc = None
        self.name = "uncalibrated (no CMYK profile set)"
        if self.path is not None:
            if not self.path.is_file():
                raise FileNotFoundError(f"CMYK profile not found: {self.path}")
            cmyk = ImageCms.getOpenProfile(str(self.path))
            if cmyk.profile.xcolor_space.strip() != "CMYK":
                raise ValueError(f"{self.path.name} is not a CMYK profile ({cmyk.profile.xcolor_space.strip()})")
            srgb = ImageCms.createProfile("sRGB")
            flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if black_point else ImageCms.Flags.NONE
            it = INTENTS[intent]
            self._fwd = ImageCms.buildTransform(srgb, cmyk, "RGB", "CMYK", renderingIntent=it, flags=flags)
            self._back = ImageCms.buildTransform(cmyk, srgb, "CMYK", "RGB",
                                                 renderingIntent=ImageCms.Intent.ABSOLUTE_COLORIMETRIC
                                                 if intent == "absolute colorimetric" else
                                                 ImageCms.Intent.RELATIVE_COLORIMETRIC, flags=flags)
            self.icc = self.path.read_bytes()
            self.name = (ImageCms.getProfileDescription(cmyk) or self.path.name).strip()

    @property
    def calibrated(self) -> bool:
        return self.icc is not None

    # ---- images (uint8) ----

    def image(self, rgb: np.ndarray, exact: bool = True) -> np.ndarray:
        """H x W x 3 uint8 sRGB -> H x W x 4 uint8 CMYK (255 = full ink). ``exact`` applies
        the overrides to pixels of exactly that colour; print images use exact=False, since
        neighbours (edges, shadows) go through the profile and a seam would show."""
        rgb = np.ascontiguousarray(rgb[:, :, :3], np.uint8)
        if self.calibrated:
            out = np.asarray(ImageCms.applyTransform(Image.fromarray(rgb, "RGB"), self._fwd)).copy()
        else:
            f = rgb.astype(np.float32) / 255.0
            k = 1.0 - f.max(axis=2)
            d = np.maximum(1.0 - k, 1e-6)
            cmy = (1.0 - f - k[..., None]) / d[..., None]
            out = np.round(np.concatenate([cmy, k[..., None]], axis=2) * 255).astype(np.uint8)
        for key, c in (self.overrides.items() if exact else ()):
            hit = np.all(rgb == np.array(key, np.uint8), axis=2)
            if hit.any():
                out[hit] = np.round(np.array(c) * 255).astype(np.uint8)
        return out

    def proof(self, rgb: np.ndarray) -> np.ndarray:
        """sRGB -> CMYK -> sRGB: how the colours will print (out-of-gamut colours shift)."""
        cmyk = self.image(rgb)
        if self.calibrated:
            return np.asarray(ImageCms.applyTransform(Image.fromarray(cmyk, "CMYK"), self._back))
        c = cmyk.astype(np.float32) / 255.0
        rgb2 = (1 - c[..., :3]) * (1 - c[..., 3:4])
        return np.round(rgb2 * 255).astype(np.uint8)

    # ---- single colours (0..1) ----

    def color(self, rgb) -> tuple:
        """(c, m, y, k) 0..1 for one sRGB colour; an override wins."""
        key = _u8(rgb)
        if key in self.overrides:
            return self.overrides[key]
        px = self.image(np.array(key, np.uint8).reshape(1, 1, 3))[0, 0]
        return tuple(round(float(v) / 255.0, 4) for v in px)


def parse_overrides(text: str, palette=None) -> list[tuple[tuple, tuple]]:
    """``#hex = C M Y K`` lines (percent, separated by spaces, commas or slashes); with a
    palette, the left side may be a colour name. ``//`` starts a comment."""
    from .color import resolve_color

    out = []
    for line in (text or "").splitlines():
        line = line.split("//")[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"(.+?)\s*[=:]\s*([\d.]+)[\s,/]+([\d.]+)[\s,/]+([\d.]+)[\s,/]+([\d.]+)\s*%?", line)
        if not m:
            raise ValueError(f"CMYK line {line!r} is not 'colour = C M Y K' (percent)")
        vals = [float(v) for v in m.groups()[1:]]
        if any(v > 100 for v in vals):
            raise ValueError(f"CMYK values are percent (0-100): {line!r}")
        out.append((resolve_color(m.group(1), palette), tuple(v / 100.0 for v in vals)))
    return out


def fmt_cmyk(c) -> str:
    return " / ".join(f"{v * 100:.0f}" for v in c)
