"""The vector design model: a Scene is a canvas plus a list of items (text boxes,
images, rectangles), each with an optional drop shadow. Nothing is rasterised
until ``render``; text is laid out at render time, so a scene can be rendered at
any scale and can reflow (an item can sit "below the previous item").

Scenes are immutable: nodes return a new Scene with one more item or a change.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import skia

from . import text as textmod
from .fonts import FontRegistry, registry
from .render import fit_rects, image_from_rgba, shadow_paint, surface, to_rgba


@dataclass(frozen=True)
class Shadow:
    dx: float = 0.0
    dy: float = 8.0
    blur: float = 16.0
    color: tuple = (0.0, 0.0, 0.0, 1.0)
    opacity: float = 0.6


@dataclass(frozen=True)
class Flow:
    """Place an item relative to the previous one instead of at its own y."""

    below_previous: bool = False
    gap: float = 24.0


@dataclass(frozen=True)
class TextItem:
    spec: textmod.TextSpec
    shadow: Shadow | None = None
    flow: Flow = Flow()
    name: str = ""


@dataclass(frozen=True)
class ImageItem:
    rgba: np.ndarray = field(compare=False, repr=False)
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    mode: str = "fit"
    shadow: Shadow | None = None
    flow: Flow = Flow()
    name: str = ""


@dataclass(frozen=True)
class RectItem:
    x: float = 0.0
    y: float = 0.0
    w: float = 100.0
    h: float = 100.0
    color: tuple = (1.0, 1.0, 1.0, 1.0)
    radius: float = 0.0
    shadow: Shadow | None = None
    flow: Flow = Flow()
    name: str = ""


Item = TextItem | ImageItem | RectItem


@dataclass(frozen=True)
class Scene:
    width: int
    height: int
    background: tuple = (0.0, 0.0, 0.0, 0.0)
    items: tuple = ()

    def add(self, item) -> "Scene":
        return replace(self, items=self.items + (item,))

    def map_last(self, fn) -> "Scene":
        if not self.items:
            raise ValueError("the scene has no items yet")
        return replace(self, items=self.items[:-1] + (fn(self.items[-1]),))


@dataclass
class Placed:
    item: Item
    bounds: tuple[float, float, float, float]
    laid: textmod.Laid | None = None
    dst: skia.Rect | None = None
    src: skia.Rect | None = None


def resolve(scene: Scene, reg: FontRegistry | None = None) -> list[Placed]:
    """Lay every item out in order, applying "below previous" flow."""
    reg = reg or registry()
    out: list[Placed] = []
    prev_bottom = None
    for it in scene.items:
        dy = 0.0
        if it.flow.below_previous and prev_bottom is not None:
            own_top = it.spec.y if isinstance(it, TextItem) else it.y
            dy = prev_bottom + it.flow.gap - own_top
        if isinstance(it, TextItem):
            laid = textmod.layout(replace(it.spec, y=it.spec.y + dy), reg)
            p = Placed(it, laid.bounds(), laid=laid)
        elif isinstance(it, ImageItem):
            ih, iw = it.rgba.shape[:2]
            src, dst = fit_rects(iw, ih, it.x, it.y + dy, it.w or iw, it.h or ih, it.mode)
            p = Placed(it, (dst.left(), dst.top(), dst.right(), dst.bottom()), dst=dst, src=src)
        else:
            p = Placed(it, (it.x, it.y + dy, it.x + it.w, it.y + dy + it.h))
        out.append(p)
        prev_bottom = p.bounds[3]
    return out


def render(scene: Scene, scale: float = 1.0, reg: FontRegistry | None = None) -> np.ndarray:
    """H x W x 4 float32 straight alpha at ``scale`` x the canvas size."""
    w, h = max(1, round(scene.width * scale)), max(1, round(scene.height * scale))
    surf = surface(w, h)
    canvas = surf.getCanvas()
    canvas.clear(skia.Color4f(*scene.background).toColor())
    canvas.scale(scale, scale)
    for p in resolve(scene, reg):
        it = p.item
        if it.shadow:
            s = it.shadow
            canvas.saveLayer(paint=shadow_paint(s.dx, s.dy, s.blur, s.color, s.opacity))
        if p.laid is not None:
            p.laid.paragraph.paint(canvas, p.laid.x, p.laid.y)
        elif isinstance(it, ImageItem):
            img = image_from_rgba(it.rgba)
            canvas.drawImageRect(img, p.src, p.dst, skia.SamplingOptions(skia.CubicResampler.Mitchell()), None)
        else:
            r, g, b, a = it.color
            paint = skia.Paint(Color=skia.Color4f(r, g, b, a), AntiAlias=True)
            x0, y0, x1, y1 = p.bounds
            canvas.drawRoundRect(skia.Rect.MakeLTRB(x0, y0, x1, y1), it.radius, it.radius, paint)
        if it.shadow:
            canvas.restore()
    return to_rgba(surf)


def to_pdf(scene: Scene, path: str, dpi: float = 300.0, reg: FontRegistry | None = None) -> None:
    """Vector RGB PDF of the scene (text stays text) via skia's PDF backend."""
    s = 72.0 / dpi
    stream = skia.FILEWStream(path)
    with skia.PDF.MakeDocument(stream) as doc:
        with doc.page(scene.width * s, scene.height * s) as canvas:
            canvas.scale(s, s)
            if scene.background[3] > 0:
                canvas.drawColor(skia.Color4f(*scene.background).toColor())
            for p in resolve(scene, reg):
                it = p.item
                if it.shadow:
                    sh = it.shadow
                    canvas.saveLayer(paint=shadow_paint(sh.dx, sh.dy, sh.blur, sh.color, sh.opacity))
                if p.laid is not None:
                    p.laid.paragraph.paint(canvas, p.laid.x, p.laid.y)
                elif isinstance(it, ImageItem):
                    canvas.drawImageRect(image_from_rgba(it.rgba), p.src, p.dst)
                else:
                    x0, y0, x1, y1 = p.bounds
                    canvas.drawRoundRect(
                        skia.Rect.MakeLTRB(x0, y0, x1, y1), it.radius, it.radius,
                        skia.Paint(Color=skia.Color4f(*it.color), AntiAlias=True),
                    )
                if it.shadow:
                    canvas.restore()
    stream.flush()
