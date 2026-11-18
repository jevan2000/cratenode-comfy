"""Preview a design while building it: the scene so far, small and quick, over a
checkerboard (or a solid background) so transparency shows, with optional guides
(safe area, item outlines). No ComfyUI imports."""

from __future__ import annotations

import numpy as np

from . import scene as sc
from .fonts import FontRegistry, registry

BACKGROUNDS = ["checkerboard", "white", "black", "grey"]
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
    return np.repeat((0.78 + 0.12 * check)[:, :, None], 3, axis=2)


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
