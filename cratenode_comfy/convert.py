"""Scene → image for other pipelines: pick an output size (scale, fit, exact), round it
to a multiple (8 / 64 for diffusion latents), and optionally flatten transparency onto
a colour. No ComfyUI imports."""

from __future__ import annotations

import numpy as np
from PIL import Image

from . import scene as sc
from .fonts import FontRegistry, registry
from .render import parse_color

SIZE_MODES = ["scale", "fit width", "fit height", "fit inside", "exact size (stretch)"]
MULTIPLES = [1, 8, 16, 32, 64]


def _round(v: float, m: int) -> int:
    m = max(1, int(m))
    return max(m, int(round(v / m)) * m)


def target_size(w: int, h: int, mode: str = "scale", scale: float = 1.0, width: int = 1024, height: int = 1024,
                multiple: int = 1) -> tuple[int, int]:
    """Output (width, height) for a w x h canvas."""
    if mode == "fit width":
        tw, th = width, h * width / w
    elif mode == "fit height":
        tw, th = w * height / h, height
    elif mode == "fit inside":
        s = min(width / w, height / h)
        tw, th = w * s, h * s
    elif mode == "exact size (stretch)":
        tw, th = width, height
    else:
        tw, th = w * scale, h * scale
    return _round(tw, multiple), _round(th, multiple)


def resize_to(rgba: np.ndarray, w: int, h: int) -> np.ndarray:
    """Lanczos resize of straight-alpha RGBA to exactly w x h (premultiplied while filtering)."""
    if rgba.shape[1] == w and rgba.shape[0] == h:
        return rgba
    def rs(ch):
        return np.asarray(Image.fromarray(ch.astype(np.float32), "F").resize((w, h), Image.LANCZOS))

    a = rgba[:, :, 3:4]
    pre = np.stack([rs(rgba[:, :, i] * a[:, :, 0]) for i in range(3)] + [rs(a[:, :, 0])], axis=2)
    pre = np.clip(pre, 0.0, 1.0)
    na = pre[:, :, 3:4]
    # Un-premultiplying faint pixels amplifies resampling error into speckled edges, which
    # shows when the IMAGE is used without its MASK. There, use the plainly resampled colour.
    straight = np.clip(np.stack([rs(rgba[:, :, i]) for i in range(3)], axis=2), 0.0, 1.0)
    rgb = np.where(na > 0.15, pre[:, :, :3] / np.maximum(na, 1e-6), straight)
    return np.concatenate([np.clip(rgb, 0, 1), na], axis=2).astype(np.float32)


def flatten(rgba: np.ndarray, matte: str = "#ffffff") -> np.ndarray:
    """Transparency composited onto a colour; alpha becomes 1."""
    m = np.array(parse_color(matte)[:3], np.float32)
    a = rgba[:, :, 3:4]
    rgb = rgba[:, :, :3] * a + m * (1 - a)
    return np.concatenate([rgb, np.ones_like(a)], axis=2).astype(np.float32)


def scene_to_rgba(scene: sc.Scene, mode: str = "scale", scale: float = 1.0, width: int = 1024, height: int = 1024,
                  multiple: int = 1, t: float | None = None, matte: str | None = None,
                  reg: FontRegistry | None = None) -> np.ndarray:
    """The scene as H x W x 4 float at the chosen size: rendered sharp at the size it
    needs (vector), then only resampled for rounding or a stretched exact size."""
    reg = reg or registry()
    tw, th = target_size(scene.width, scene.height, mode, scale, width, height, multiple)
    s = max(tw / scene.width, th / scene.height)  # render at least this sharp
    rgba = resize_to(sc.render(scene, s, reg, t), tw, th)
    return flatten(rgba, matte) if matte else rgba
