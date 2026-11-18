"""Preview a design while building it: the scene so far, small and quick, over a
checkerboard (or a solid background) so transparency shows, with optional guides
(safe area, item outlines). No ComfyUI imports."""

from __future__ import annotations

import numpy as np

from . import scene as sc
from .fonts import FontRegistry, registry

BACKGROUNDS = ["checkerboard", "auto", "dark checkerboard", "white", "black", "grey"]
GUIDES = ["none", "safe area", "safe area + item outlines"]
SAFE = (0.0, 0.85, 1.0)  # cyan
BOUNDS = (1.0, 0.25, 0.75)  # magenta


def backdrop(h: int, w: int, kind: str = "checkerboard", cell: int = 12) -> np.ndarray:
    if kind == "white":
        return np.ones((h, w, 3), np.float32)
    if kind == "black":
        return np.zeros((h, w, 3), np.float32)
    if kind == "grey":
        return np.full((h, w, 3), 0.5, np.float32)
    yy, xx = np.mgrid[0:h, 0:w]
    check = ((yy // cell + xx // cell) % 2).astype(np.float32)
    base, step = (0.14, 0.07) if kind == "dark checkerboard" else (0.78, 0.12)
    return np.repeat((base + step * check)[:, :, None], 3, axis=2)


def auto_backdrop(rgba: np.ndarray) -> str:
    """A dark checkerboard behind light content (white text), else the light one."""
    a = rgba[:, :, 3]
    seen = a > 0.1
    if not seen.any():
        return "checkerboard"
    lum = (rgba[:, :, :3] @ np.array([0.2126, 0.7152, 0.0722], np.float32))[seen]
    return "dark checkerboard" if float(lum.mean()) > 0.6 else "checkerboard"


def _dashed_rect(img: np.ndarray, x0, y0, x1, y1, color, width: int = 1, dash: int = 8) -> None:
    h, w = img.shape[:2]
    x0, y0 = int(round(x0)), int(round(y0))
    x1, y1 = int(round(x1)) - 1, int(round(y1)) - 1
    c = np.array(color, np.float32)

    def on(i):
        return dash <= 0 or (i // dash) % 2 == 0

    for t in range(width):
        for y in (y0 + t, y1 - t):
            if 0 <= y < h:
                for x in range(max(0, x0), min(w, x1 + 1)):
                    if on(x - x0):
                        img[y, x] = c
        for x in (x0 + t, x1 - t):
            if 0 <= x < w:
                for y in range(max(0, y0), min(h, y1 + 1)):
                    if on(y - y0):
                        img[y, x] = c


def preview(scene: sc.Scene, scale: float = 0.5, t: float | None = None, guides: str = "none",
            background: str = "checkerboard", reg: FontRegistry | None = None) -> np.ndarray:
    """H x W x 3 float: the design at ``scale`` (at time ``t``; None = at rest) over a
    backdrop, with guides drawn on top (they are only in the preview, never in output)."""
    reg = reg or registry()
    rgba = sc.render(scene, scale, reg, t)
    h, w = rgba.shape[:2]
    a = rgba[:, :, 3:4]
    if background == "auto":
        background = auto_backdrop(rgba)
    img = (rgba[:, :, :3] * a + backdrop(h, w, background) * (1 - a)).astype(np.float32)
    lw = max(1, round(2 * scale))
    if guides in ("safe area", "safe area + item outlines"):
        x, y, bw, bh = scene.safe_box()
        if (bw, bh) != (scene.width, scene.height):
            _dashed_rect(img, x * scale, y * scale, (x + bw) * scale, (y + bh) * scale, SAFE, lw)
    if guides == "safe area + item outlines":
        for p in sc.place_items(scene.items, reg):
            x0, y0, x1, y1 = p.bounds
            _dashed_rect(img, x0 * scale, y0 * scale, x1 * scale, y1 * scale, BOUNDS, lw, dash=4)
    return img


def fit_scale(w: float, h: float, max_w: int, max_h: int) -> float:
    return min(max_w / max(w, 1.0), max_h / max(h, 1.0))


def part_preview(scene: sc.Scene, max_w: int = 320, max_h: int = 200, pad: float = 12.0,
                 background: str = "auto", reg: FontRegistry | None = None) -> np.ndarray:
    """A part (items without a real canvas, e.g. a Text Box with no scene) cropped to
    what it actually draws (the letters, not their text box; effects included) and
    fitted into max_w x max_h. H x W x 3 float."""
    from .smart import ink_bounds

    reg = reg or registry()
    ink = ink_bounds(scene.items, reg)
    if ink is None:
        return backdrop(max_h // 2, max_w, "checkerboard" if background == "auto" else background)
    x0, y0, x1, y1 = ink[0] - pad, ink[1] - pad, ink[2] + pad, ink[3] + pad
    crop = sc.Scene(max(1, int(np.ceil(x1 - x0))), max(1, int(np.ceil(y1 - y0))), scene.background,
                    items=(sc.GroupItem(items=scene.items, dx=-x0, dy=-y0),))
    return preview(crop, min(1.0, fit_scale(crop.width, crop.height, max_w, max_h)), None, "none", background, reg)


def to_png(img: np.ndarray) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.fromarray(np.round(np.clip(img, 0, 1) * 255).astype(np.uint8), "RGB").save(buf, "PNG", optimize=False)
    return buf.getvalue()


def describe(scene: sc.Scene, reg: FontRegistry | None = None) -> str:
    """One line about the scene: size, items, and duration when animated."""
    reg = reg or registry()
    kinds: dict[str, int] = {}
    for it in _walk(scene.items):
        k = type(it).__name__.replace("Item", "").lower()
        kinds[k] = kinds.get(k, 0) + 1
    parts = ", ".join(f"{n} {k}{'s' if n != 1 else ''}" for k, n in kinds.items()) or "empty"
    line = f"{scene.width}x{scene.height}: {parts}"
    animated = any(it.anim for it in _walk(scene.items)) or any(isinstance(it, sc.VideoItem)
                                                                 for it in _walk(scene.items))
    if animated:
        line += f"; {sc.scene_duration(scene):.2f} s at {scene.fps:g} fps"
    return line


def _walk(items):
    for it in items:
        if isinstance(it, (sc.GroupItem, sc.LayoutItem)):
            yield from _walk(it.items if isinstance(it, sc.GroupItem) else tuple(x for p in it.parts for x in p))
        else:
            yield it
