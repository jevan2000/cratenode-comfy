"""Generate the placeholder assets used by the example workflows.

    python tools/make_placeholders.py

- api_examples/assets/placeholder-background.jpg: a 1920x1080 "photo" (soft gradient,
  light blobs and grain), standing in for an AI-generated background.
- api_examples/assets/placeholder-logo.png: a 600x600 transparent logo mark.
- api_examples/assets/placeholder-busy.jpg: a bright 1920x1080 picture, busy on the left
  and calm on the right, for the smart helpers.

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

OUT = ROOT / "api_examples" / "assets"


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


def busy(w=1920, h=1080, seed=11) -> np.ndarray:
    """A bright scene that is busy on the left (shapes, lines) and calm on the right,
    for the smart helpers: auto-placement and scrims."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    sky = np.array([0.80, 0.86, 0.93]) * (1 - yy[..., None] / h * 0.25) + np.array([0.98, 0.9, 0.78]) * (yy[..., None] / h * 0.25)
    img = sky.astype(np.float32).copy()
    surf = skia.Surface.MakeRaster(skia.ImageInfo.Make(w, h, skia.kRGBA_8888_ColorType, skia.kPremul_AlphaType))
    c = surf.getCanvas()
    c.clear(skia.ColorTRANSPARENT)
    for _ in range(260):
        x, y = rng.uniform(-50, w * 0.55), rng.uniform(-50, h + 50)
        col = skia.Color(*[int(v) for v in rng.uniform(40, 255, 3)])
        p = skia.Paint(Color=col, AntiAlias=True, Alphaf=float(rng.uniform(0.5, 1.0)))
        kind = rng.integers(3)
        if kind == 0:
            c.drawCircle(x, y, float(rng.uniform(8, 70)), p)
        elif kind == 1:
            c.drawRect(skia.Rect.MakeXYWH(x, y, float(rng.uniform(10, 140)), float(rng.uniform(10, 140))), p)
        else:
            p.setStyle(skia.Paint.kStroke_Style)
            p.setStrokeWidth(float(rng.uniform(2, 10)))
            c.drawLine(x, y, x + float(rng.uniform(-200, 200)), y + float(rng.uniform(-200, 200)), p)
    shapes = surf.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType,
                                              alphaType=skia.kUnpremul_AlphaType).astype(np.float32) / 255
    a = shapes[..., 3:4]
    img = shapes[..., :3] * a + img * (1 - a)
    img += rng.normal(0, 0.01, img.shape)
    return np.clip(img, 0, 1)


ASSETS = {
    "placeholder-background.jpg": lambda p: Image.fromarray((background() * 255 + 0.5).astype(np.uint8)).save(p, quality=88),
    "placeholder-logo.png": lambda p: Image.fromarray((logo() * 255 + 0.5).astype(np.uint8), "RGBA").save(p),
    "placeholder-busy.jpg": lambda p: Image.fromarray((busy() * 255 + 0.5).astype(np.uint8)).save(p, quality=86),
}


def main() -> None:
    """Writes the assets that are missing (--force rewrites all)."""
    OUT.mkdir(parents=True, exist_ok=True)
    force = "--force" in sys.argv
    for name, make in ASSETS.items():
        if force or not (OUT / name).exists():
            make(OUT / name)
            print("wrote", OUT / name)


if __name__ == "__main__":
    main()
