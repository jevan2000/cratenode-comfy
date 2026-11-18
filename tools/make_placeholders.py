"""Generate the placeholder assets used by the example workflows.

    python tools/make_placeholders.py

- examples/assets/placeholder-background.jpg: a 1920x1080 "photo" (soft gradient,
  light blobs and grain), standing in for an AI-generated background.
- examples/assets/placeholder-logo.png: a 600x600 transparent logo mark.

Both are made here, so they are free to publish with the pack.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import skia
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cratenode_comfy import fonts, scene, text  # noqa: E402

OUT = ROOT / "examples" / "assets"


def background(w=1920, h=1080, seed=7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    t = (yy / h) * 0.7 + (xx / w) * 0.3
    top, bottom = np.array([0.05, 0.07, 0.16]), np.array([0.10, 0.32, 0.36])
    img = top * (1 - t[..., None]) + bottom * t[..., None]
    for _ in range(6):
        cx, cy, r = rng.uniform(0, w), rng.uniform(0, h * 0.8), rng.uniform(150, 450)
        glow = np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * r * r)))[..., None]
        img += glow * rng.uniform(0.05, 0.18) * np.array([1.0, 0.85, 0.6])
    img += rng.normal(0, 0.012, img.shape)
    return np.clip(img, 0, 1)


def logo(size=600) -> np.ndarray:
    surf = skia.Surface.MakeRaster(skia.ImageInfo.Make(size, size, skia.kRGBA_8888_ColorType, skia.kUnpremul_AlphaType))
    c = surf.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    ring = skia.Paint(Color=skia.Color(255, 255, 255), AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=28)
    c.drawCircle(size / 2, size / 2, size / 2 - 30, ring)
    leaf = skia.Paint(Color=skia.Color(120, 200, 90), AntiAlias=True)
    c.drawOval(skia.Rect.MakeXYWH(size * 0.42, size * 0.68, size * 0.16, size * 0.12), leaf)
    rgba = surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kUnpremul_AlphaType)
    rgba = rgba.astype(np.float32) / 255
    mark = scene.Scene(size, size).add(scene.TextItem(text.TextSpec(
        text="LOGO", family="Montserrat", weight=900, size=150, color=(1, 1, 1, 1),
        x=0, y=0, width=size, height=size, align="center", valign="middle")))
    m = scene.render(mark, reg=fonts.FontRegistry())
    a = m[..., 3:4]
    out = rgba.copy()
    out[..., :3] = m[..., :3] * a + rgba[..., :3] * (1 - a)
    out[..., 3:4] = a + rgba[..., 3:4] * (1 - a)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray((background() * 255 + 0.5).astype(np.uint8)).save(OUT / "placeholder-background.jpg", quality=88)
    Image.fromarray((logo() * 255 + 0.5).astype(np.uint8), "RGBA").save(OUT / "placeholder-logo.png")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
