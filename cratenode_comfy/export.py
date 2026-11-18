"""Raster export: PNG, JPEG and WebP from straight-alpha RGBA, with a size budget.

Pure Python + Pillow (no ComfyUI imports) so it can be unit-tested on its own.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageFile

from .render import parse_color

FORMATS = ("png", "jpeg", "webp")
EXT = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}
MIN_QUALITY = 10


@dataclass
class ExportOptions:
    fmt: str = "png"
    quality: int = 92            # JPEG / lossy WebP
    lossless: bool = False       # WebP only
    transparent: bool = True     # keep alpha (PNG / WebP); JPEG always flattens
    matte: str = "#ffffff"       # colour behind transparent areas when flattening
    dpi: float = 0.0             # 0 = don't write a DPI (PNG / JPEG only)
    max_kb: int = 0              # 0 = no limit; JPEG / lossy WebP lower quality to fit
    srgb: bool = True            # embed an sRGB ICC profile
    extra: dict = field(default_factory=dict)  # format-specific Pillow save kwargs (metadata)


@dataclass
class Encoded:
    data: bytes
    fmt: str
    quality: int | None   # quality actually used (lossy formats)
    fits: bool            # within max_kb (always True without a limit)

    @property
    def kb(self) -> float:
        return len(self.data) / 1024.0


def to_pil(rgba: np.ndarray, transparent: bool, matte: str = "#ffffff") -> Image.Image:
    """PIL image from H x W x 4 float (0..1, straight alpha): RGBA, or RGB over ``matte``."""
    a = np.clip(rgba[:, :, 3:4], 0.0, 1.0)
    rgb = np.clip(rgba[:, :, :3], 0.0, 1.0)
    if transparent:
        u8 = np.round(np.concatenate([rgb, a], axis=2) * 255.0).astype(np.uint8)
        return Image.fromarray(u8, "RGBA")
    m = np.array(parse_color(matte)[:3], np.float32)
    flat = rgb * a + m * (1.0 - a)
    return Image.fromarray(np.round(flat * 255.0).astype(np.uint8), "RGB")


def _srgb_bytes() -> bytes:
    from PIL import ImageCms

    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _save(img: Image.Image, opts: ExportOptions, quality: int) -> bytes:
    kw = dict(opts.extra)
    if opts.srgb:
        kw["icc_profile"] = _srgb_bytes()
    if opts.dpi and opts.fmt in ("png", "jpeg"):
        kw["dpi"] = (opts.dpi, opts.dpi)
    buf = io.BytesIO()
    if opts.fmt == "png":
        img.save(buf, "PNG", optimize=True, **kw)
    elif opts.fmt == "jpeg":
        # 4:4:4 chroma keeps coloured type crisp at high quality. Pillow's default output
        # buffer can be too small for busy 4:4:4 images ("Suspension not allowed"), so
        # raise it for this save only.
        old = ImageFile.MAXBLOCK
        ImageFile.MAXBLOCK = max(old, img.width * img.height * 4 + 65536)
        try:
            img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True,
                     subsampling=0 if quality >= 85 else 2, **kw)
        finally:
            ImageFile.MAXBLOCK = old
    elif opts.fmt == "webp":
        img.save(buf, "WEBP", quality=100 if opts.lossless else quality, lossless=opts.lossless,
                 method=6 if opts.lossless else 4, exact=opts.lossless, **kw)
    else:
        raise ValueError(f"unknown format {opts.fmt!r}; use one of {FORMATS}")
    return buf.getvalue()


def encode(rgba: np.ndarray, opts: ExportOptions) -> Encoded:
    """Encode one frame. With ``max_kb``, lossy formats use the highest quality that fits."""
    if opts.fmt not in FORMATS:
        raise ValueError(f"unknown format {opts.fmt!r}; use one of {FORMATS}")
    transparent = opts.transparent and opts.fmt != "jpeg"
    img = to_pil(rgba, transparent, opts.matte)
    lossy = opts.fmt == "jpeg" or (opts.fmt == "webp" and not opts.lossless)
    q = max(1, min(100, int(opts.quality)))
    data = _save(img, opts, q)
    limit = opts.max_kb * 1024
    if not limit:
        return Encoded(data, opts.fmt, q if lossy else None, True)
    if len(data) <= limit or not lossy:
        return Encoded(data, opts.fmt, q if lossy else None, len(data) <= limit)
    # binary search the highest quality in [MIN_QUALITY, q) that fits
    lo, hi, best = MIN_QUALITY, q - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        d = _save(img, opts, mid)
        if len(d) <= limit:
            best, lo = (mid, d), mid + 1
        else:
            hi = mid - 1
    if best:
        return Encoded(best[1], opts.fmt, best[0], True)
    return Encoded(_save(img, opts, MIN_QUALITY), opts.fmt, MIN_QUALITY, False)


def resize(rgba: np.ndarray, scale: float) -> np.ndarray:
    """Lanczos resize of straight-alpha RGBA (premultiplied while filtering, so edges stay clean)."""
    if abs(scale - 1.0) < 1e-6:
        return rgba
    h, w = rgba.shape[:2]
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    a = rgba[:, :, 3:4]
    pre = np.concatenate([rgba[:, :, :3] * a, a], axis=2)
    chans = [np.asarray(Image.fromarray(pre[:, :, i].astype(np.float32), "F").resize((nw, nh), Image.LANCZOS))
             for i in range(4)]
    out = np.clip(np.stack(chans, axis=2), 0.0, 1.0)
    na = out[:, :, 3:4]
    rgb = np.where(na > 1e-6, out[:, :, :3] / np.maximum(na, 1e-6), 0.0)
    return np.concatenate([np.clip(rgb, 0.0, 1.0), na], axis=2).astype(np.float32)
