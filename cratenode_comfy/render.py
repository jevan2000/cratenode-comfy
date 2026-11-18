"""Shared drawing: skia surfaces, colour parsing, image fit/fill, drop shadows,
and conversion between skia/numpy RGBA and ComfyUI IMAGE/MASK tensors."""

from __future__ import annotations

import numpy as np
import skia

FIT_MODES = ["fit", "fill", "stretch"]


def parse_color(s: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    """``#rrggbb`` / ``#rrggbbaa`` (alpha multiplies ``alpha``)."""
    h = s.strip().lstrip("#")
    if len(h) not in (6, 8) or any(c not in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"colour {s!r} is not #rrggbb or #rrggbbaa")
    v = [int(h[i : i + 2], 16) / 255 for i in range(0, len(h), 2)]
    a = v[3] if len(v) == 4 else 1.0
    return (v[0], v[1], v[2], a * alpha)


def surface(width: int, height: int) -> skia.Surface:
    info = skia.ImageInfo.Make(width, height, skia.kRGBA_8888_ColorType, skia.kUnpremul_AlphaType)
    return skia.Surface.MakeRaster(info)


def to_rgba(surf: skia.Surface) -> np.ndarray:
    """H x W x 4 float32 straight alpha, 0..1."""
    img = surf.makeImageSnapshot()
    arr = img.toarray(colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kUnpremul_AlphaType)
    return arr.astype(np.float32) / 255.0


def image_from_rgba(rgba: np.ndarray) -> skia.Image:
    """From H x W x 3|4 float 0..1 (straight alpha)."""
    if rgba.shape[2] == 3:
        rgba = np.concatenate([rgba, np.ones(rgba.shape[:2] + (1,), rgba.dtype)], axis=2)
    u8 = np.ascontiguousarray((np.clip(rgba, 0, 1) * 255 + 0.5).astype(np.uint8))
    return skia.Image.fromarray(u8, colorType=skia.kRGBA_8888_ColorType, alphaType=skia.kUnpremul_AlphaType)


def fit_rects(iw: float, ih: float, x: float, y: float, w: float, h: float, mode: str, align=(0.5, 0.5)):
    """(src rect, dst rect) to draw an iw x ih image into box (x, y, w, h)."""
    ax, ay = align
    if mode == "stretch":
        return skia.Rect.MakeWH(iw, ih), skia.Rect.MakeXYWH(x, y, w, h)
    if mode == "fill":
        s = max(w / iw, h / ih)
        sw, sh = w / s, h / s
        sx, sy = (iw - sw) * ax, (ih - sh) * ay
        return skia.Rect.MakeXYWH(sx, sy, sw, sh), skia.Rect.MakeXYWH(x, y, w, h)
    s = min(w / iw, h / ih)
    dw, dh = iw * s, ih * s
    return skia.Rect.MakeWH(iw, ih), skia.Rect.MakeXYWH(x + (w - dw) * ax, y + (h - dh) * ay, dw, dh)


def shadow_paint(dx: float, dy: float, blur: float, color, opacity: float) -> skia.Paint:
    """A layer paint that draws a drop shadow under whatever is drawn in the layer."""
    r, g, b, a = color
    c = skia.Color4f(r, g, b, a * opacity).toColor()
    return skia.Paint(ImageFilter=skia.ImageFilters.DropShadow(dx, dy, blur / 2, blur / 2, c))


# ---- ComfyUI tensors ----


def rgba_to_comfy(rgba: np.ndarray):
    """(IMAGE [1,H,W,3], MASK [1,H,W]) from H x W x 4. IMAGE is the colour, MASK the alpha."""
    import torch

    t = torch.from_numpy(np.ascontiguousarray(rgba))
    return t[None, :, :, :3].clone(), t[None, :, :, 3].clone()


def comfy_to_rgba(image, mask=None, index: int = 0) -> np.ndarray:
    """H x W x 4 from a ComfyUI IMAGE (and optional MASK, 1 = opaque)."""
    rgb = image[index].cpu().numpy().astype(np.float32)
    h, w = rgb.shape[:2]
    if mask is None:
        a = np.ones((h, w, 1), np.float32)
    else:
        m = mask[min(index, mask.shape[0] - 1)].cpu().numpy().astype(np.float32)
        if m.shape != (h, w):
            raise ValueError(f"mask {m.shape} does not match image {(h, w)}")
        a = m[:, :, None]
    if rgb.shape[2] == 4:
        return rgb
    return np.concatenate([rgb, a], axis=2)
