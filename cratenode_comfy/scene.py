"""The vector design model.

A ``Scene`` is a canvas (size, background, safe-area margins) plus an ordered
tuple of items, drawn first to last. Items are text boxes, images, shapes and
groups; every item has an opacity, a blend mode and a list of effects (drop
shadow, outer glow, outline, blur). Nothing is rasterised until ``render``, so a
scene renders sharp at any scale, reflows (an item can sit below the previous
one), exports to vector PDF, and can be re-rendered per frame for motion.

Scenes and items are immutable; nodes return new ones.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import skia

from . import text as textmod
from .fonts import FontRegistry, registry
from .render import fit_rects, image_from_rgba, surface, to_rgba

RGBA = tuple  # (r, g, b, a), 0..1

BLEND_MODES = {
    "normal": skia.BlendMode.kSrcOver, "multiply": skia.BlendMode.kMultiply, "screen": skia.BlendMode.kScreen,
    "overlay": skia.BlendMode.kOverlay, "darken": skia.BlendMode.kDarken, "lighten": skia.BlendMode.kLighten,
    "color dodge": skia.BlendMode.kColorDodge, "color burn": skia.BlendMode.kColorBurn,
    "hard light": skia.BlendMode.kHardLight, "soft light": skia.BlendMode.kSoftLight,
    "difference": skia.BlendMode.kDifference, "exclusion": skia.BlendMode.kExclusion,
    "hue": skia.BlendMode.kHue, "saturation": skia.BlendMode.kSaturation, "color": skia.BlendMode.kColor,
    "luminosity": skia.BlendMode.kLuminosity, "add": skia.BlendMode.kPlus,
}
SHAPES = ["rectangle", "ellipse", "line", "polygon", "star"]


# ---- fills ----

@dataclass(frozen=True)
class Gradient:
    """Linear (``angle`` degrees, 0 = left to right, 90 = top to bottom) or radial
    (from the box centre). Stops are (position 0..1, rgba)."""

    kind: str = "linear"
    stops: tuple = ((0.0, (0.0, 0.0, 0.0, 1.0)), (1.0, (1.0, 1.0, 1.0, 1.0)))
    angle: float = 90.0

    def shader(self, x0: float, y0: float, x1: float, y1: float) -> skia.Shader:
        colors = [skia.Color4f(*c).toColor() for _, c in self.stops]
        pos = [float(p) for p, _ in self.stops]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if self.kind == "radial":
            r = max(x1 - x0, y1 - y0) / 2 or 1.0
            return skia.GradientShader.MakeRadial(skia.Point(cx, cy), r, colors, pos)
        a = math.radians(self.angle)
        dx, dy = math.cos(a), math.sin(a)
        half = abs(dx) * (x1 - x0) / 2 + abs(dy) * (y1 - y0) / 2
        p0 = skia.Point(cx - dx * half, cy - dy * half)
        p1 = skia.Point(cx + dx * half, cy + dy * half)
        return skia.GradientShader.MakeLinear([p0, p1], colors, pos)


Fill = tuple | Gradient  # an RGBA tuple or a Gradient


def fill_paint(fill: Fill, bounds) -> skia.Paint:
    paint = skia.Paint(AntiAlias=True)
    if isinstance(fill, Gradient):
        paint.setShader(fill.shader(*bounds))
    else:
        paint.setColor4f(skia.Color4f(*fill))
    return paint


# ---- effects ----

@dataclass(frozen=True)
class Shadow:
    dx: float = 0.0
    dy: float = 8.0
    blur: float = 16.0
    color: RGBA = (0.0, 0.0, 0.0, 1.0)
    opacity: float = 0.6


@dataclass(frozen=True)
class Glow:
    blur: float = 24.0
    spread: float = 0.0
    color: RGBA = (1.0, 1.0, 1.0, 1.0)
    opacity: float = 0.8


@dataclass(frozen=True)
class Outline:
    """A solid outline around the item's shape (text, images with alpha, shapes)."""

    width: float = 4.0
    color: RGBA = (0.0, 0.0, 0.0, 1.0)
    opacity: float = 1.0


@dataclass(frozen=True)
class Blur:
    radius: float = 8.0


Effect = Shadow | Glow | Outline | Blur


def _tint(color: RGBA, opacity: float, source: skia.ImageFilter | None) -> skia.ImageFilter:
    r, g, b, a = color
    cf = skia.ColorFilters.Blend(skia.Color4f(r, g, b, a * opacity).toColor(), skia.BlendMode.kSrcIn)
    return skia.ImageFilters.ColorFilter(cf, source)


def _grow(width: float, source: skia.ImageFilter | None) -> skia.ImageFilter:
    """Grow the shape's alpha by about ``width`` px: blur, then a steep alpha threshold.
    Much faster than morphology (Dilate) at large widths, and rounds the corners."""
    sigma = max(width, 0.5) / 2.0
    k, t = 40.0, 0.03  # alpha' = k * (alpha - t): a near-binary edge at about 2 sigma out
    matrix = [1, 0, 0, 0, 0,
              0, 1, 0, 0, 0,
              0, 0, 1, 0, 0,
              0, 0, 0, k, -k * t]
    blurred = skia.ImageFilters.Blur(sigma, sigma, skia.TileMode.kDecal, source)
    return skia.ImageFilters.ColorFilter(skia.ColorFilters.Matrix(matrix), blurred)


def effect_reach(effects: tuple) -> float:
    """How far (px) effects draw outside the item's bounds."""
    reach = 0.0
    for e in effects:
        if isinstance(e, Shadow):
            reach = max(reach, abs(e.dx) + abs(e.dy) + e.blur * 1.5)
        elif isinstance(e, Glow):
            reach = max(reach, e.spread + e.blur * 1.5)
        elif isinstance(e, Outline):
            reach = max(reach, e.width * 1.5)
        elif isinstance(e, Blur):
            reach = max(reach, e.radius * 1.5)
    return reach


def effects_filter(effects: tuple) -> skia.ImageFilter | None:
    """One image filter: layers under the item (shadow, glow, outline) then the item."""
    if not effects:
        return None
    src = None
    for e in effects:
        if isinstance(e, Blur) and e.radius > 0:
            src = skia.ImageFilters.Blur(e.radius / 2, e.radius / 2, skia.TileMode.kDecal, src)
    under = []
    for e in effects:
        if isinstance(e, Shadow):
            c = skia.Color4f(e.color[0], e.color[1], e.color[2], e.color[3] * e.opacity).toColor()
            under.append(skia.ImageFilters.DropShadowOnly(e.dx, e.dy, e.blur / 2, e.blur / 2, c, src))
        elif isinstance(e, Glow):
            # Spread brightens and widens the halo with an alpha gain after the blur (no hard
            # edge, so no banding on 8-bit layers).
            halo = skia.ImageFilters.Blur(e.blur / 2, e.blur / 2, skia.TileMode.kDecal, src)
            if e.spread > 0:
                g = 1.0 + e.spread / 4.0
                gain = [0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, 0, 0,  0, 0, 0, g, 0]
                halo = skia.ImageFilters.ColorFilter(skia.ColorFilters.Matrix(gain), halo)
            under.append(_tint(e.color, e.opacity, halo))
        elif isinstance(e, Outline) and e.width > 0:
            under.append(_tint(e.color, e.opacity, _grow(e.width, src)))
    if not under:
        return src
    return skia.ImageFilters.Merge(under + [src])


# ---- items ----

@dataclass(frozen=True)
class Flow:
    """Place an item relative to the previous one instead of at its own y."""

    below_previous: bool = False
    gap: float = 24.0


@dataclass(frozen=True)
class Style:
    opacity: float = 1.0
    blend: str = "normal"
    effects: tuple = ()
    clip_to_previous: bool = False


@dataclass(frozen=True)
class TextItem:
    spec: textmod.TextSpec
    fill: Gradient | None = None  # gradient text; solid colour lives in spec.color
    style: Style = Style()
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
    style: Style = Style()
    flow: Flow = Flow()
    name: str = ""
    _skimage: list = field(default_factory=list, init=False, compare=False, repr=False)  # decode cache

    def skimage(self) -> skia.Image:
        if not self._skimage:
            self._skimage.append(image_from_rgba(self.rgba))
        return self._skimage[0]


@dataclass(frozen=True)
class ShapeItem:
    kind: str = "rectangle"
    x: float = 0.0
    y: float = 0.0
    w: float = 100.0
    h: float = 100.0
    fill: Fill | None = (1.0, 1.0, 1.0, 1.0)
    stroke: RGBA | None = None
    stroke_width: float = 0.0
    radius: float = 0.0  # rectangle corners
    sides: int = 6  # polygon / star points
    inner: float = 0.5  # star inner radius ratio
    rotation: float = 0.0  # degrees, around the box centre
    style: Style = Style()
    flow: Flow = Flow()
    name: str = ""


@dataclass(frozen=True)
class GroupItem:
    """Items drawn together, moved by (dx, dy); effects apply to the group as one."""

    items: tuple = ()
    dx: float = 0.0
    dy: float = 0.0
    style: Style = Style()
    flow: Flow = Flow()
    name: str = ""


@dataclass(frozen=True)
class LayoutItem:
    """Parts arranged when the scene is drawn, so changed text (a filled template)
    still reflows. ``kind`` is "stack" or "grid"; Place is a one-part stack.
    ``parts`` is a tuple of item tuples; ``box`` is (x, y, w, h) in canvas pixels."""

    kind: str = "stack"
    parts: tuple = ()
    box: tuple = (0.0, 0.0, 0.0, 0.0)
    direction: str = "vertical"
    gap: float = 24.0
    gap_y: float = 24.0
    columns: int = 3
    align: str = "center"
    valign: str = "middle"
    style: Style = Style()
    flow: Flow = Flow()
    name: str = ""


Item = TextItem | ImageItem | ShapeItem | GroupItem | LayoutItem


def children(it, reg: FontRegistry) -> tuple[tuple, float, float]:
    """(items, dx, dy) inside a group or a layout (a layout is arranged now)."""
    if isinstance(it, LayoutItem):
        from .layout import arrange

        return arrange(it, reg), 0.0, 0.0
    return it.items, it.dx, it.dy


@dataclass(frozen=True)
class Scene:
    width: int
    height: int
    background: Fill = (0.0, 0.0, 0.0, 0.0)
    items: tuple = ()
    margin: tuple = (0.0, 0.0, 0.0, 0.0)  # safe area: left, top, right, bottom

    def add(self, item) -> "Scene":
        return replace(self, items=self.items + (item,))

    def map_last(self, fn) -> "Scene":
        if not self.items:
            raise ValueError("the scene has no items yet")
        return replace(self, items=self.items[:-1] + (fn(self.items[-1]),))

    def safe_box(self) -> tuple[float, float, float, float]:
        l, t, r, b = self.margin
        return (l, t, self.width - l - r, self.height - t - b)


def with_style(item, **changes):
    return replace(item, style=replace(item.style, **changes))


def add_effect(item, effect):
    return with_style(item, effects=item.style.effects + (effect,))


# ---- layout ----

@dataclass
class Placed:
    item: Item
    bounds: tuple[float, float, float, float]
    laid: textmod.Laid | None = None
    src: skia.Rect | None = None
    dst: skia.Rect | None = None
    children: list | None = None


def _item_top(it) -> float:
    if isinstance(it, TextItem):
        return it.spec.y
    if isinstance(it, (GroupItem, LayoutItem)):
        return 0.0
    return it.y


def _union(bs):
    bs = [b for b in bs if b is not None]
    if not bs:
        return None
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs))


def _shape_bounds(it: ShapeItem, dy: float):
    return (it.x, it.y + dy, it.x + it.w, it.y + dy + it.h)


def place_items(items: tuple, reg: FontRegistry, ox: float = 0.0, oy: float = 0.0) -> list[Placed]:
    """Lay items out in order, applying "below previous" flow; (ox, oy) offsets all."""
    out: list[Placed] = []
    prev_bottom = None
    for it in items:
        dy = 0.0
        if it.flow.below_previous and prev_bottom is not None:
            if isinstance(it, (GroupItem, LayoutItem)):
                kids, kdx, kdy = children(it, reg)
                inner = _union([p.bounds for p in place_items(kids, reg, ox + kdx, oy + kdy)])
                top = inner[1] if inner else oy
            else:
                top = _item_top(it) + oy
            dy = prev_bottom + it.flow.gap - top
        if isinstance(it, TextItem):
            laid = textmod.layout(replace(it.spec, x=it.spec.x + ox, y=it.spec.y + oy + dy), reg)
            p = Placed(it, laid.bounds(), laid=laid)
        elif isinstance(it, ImageItem):
            ih, iw = it.rgba.shape[:2]
            src, dst = fit_rects(iw, ih, it.x + ox, it.y + oy + dy, it.w or iw, it.h or ih, it.mode)
            p = Placed(it, (dst.left(), dst.top(), dst.right(), dst.bottom()), src=src, dst=dst)
        elif isinstance(it, ShapeItem):
            x0, y0, x1, y1 = _shape_bounds(it, dy)
            p = Placed(it, (x0 + ox, y0 + oy, x1 + ox, y1 + oy))
        else:
            items, kdx, kdy = children(it, reg)
            kids = place_items(items, reg, ox + kdx, oy + kdy + dy)
            p = Placed(it, _union([k.bounds for k in kids]) or (ox, oy, ox, oy), children=kids)
        out.append(p)
        prev_bottom = p.bounds[3]
    return out


def resolve(scene: Scene, reg: FontRegistry | None = None) -> list[Placed]:
    return place_items(scene.items, reg or registry())


def content_bounds(items: tuple, reg: FontRegistry | None = None):
    return _union([p.bounds for p in place_items(items, reg or registry())])


# ---- drawing ----

def _shape_path(it: ShapeItem, b) -> skia.Path:
    x0, y0, x1, y1 = b
    w, h = x1 - x0, y1 - y0
    cx, cy = x0 + w / 2, y0 + h / 2
    path = skia.Path()
    if it.kind == "ellipse":
        path.addOval(skia.Rect.MakeLTRB(x0, y0, x1, y1))
    elif it.kind == "line":
        path.moveTo(x0, y0)
        path.lineTo(x1, y1)
    elif it.kind in ("polygon", "star"):
        n = max(3, int(it.sides))
        pts = n * (2 if it.kind == "star" else 1)
        for k in range(pts):
            a = -math.pi / 2 + 2 * math.pi * k / pts
            r = 1.0 if (it.kind == "polygon" or k % 2 == 0) else max(0.05, min(1.0, it.inner))
            px, py = cx + math.cos(a) * w / 2 * r, cy + math.sin(a) * h / 2 * r
            path.moveTo(px, py) if k == 0 else path.lineTo(px, py)
        path.close()
    else:
        path.addRRect(skia.RRect.MakeRectXY(skia.Rect.MakeLTRB(x0, y0, x1, y1), it.radius, it.radius))
    if it.rotation:
        path.transform(skia.Matrix.RotateDeg(it.rotation, skia.Point(cx, cy)))
    return path


def _draw_content(canvas: skia.Canvas, p: Placed, reg: FontRegistry) -> None:
    it = p.item
    if isinstance(it, TextItem):
        laid = p.laid
        if it.fill is not None:
            shader_paint = fill_paint(it.fill, laid.bounds())
            spec = replace(it.spec, color=(1, 1, 1, 1))
            laid = textmod.layout(replace(spec, x=laid.x, y=laid.y, valign="top", height=0), reg)
            canvas.saveLayer()
            laid.paragraph.paint(canvas, laid.x, laid.y)
            shader_paint.setBlendMode(skia.BlendMode.kSrcIn)
            canvas.drawRect(skia.Rect.MakeLTRB(*laid.bounds()), shader_paint)
            canvas.restore()
        else:
            laid.paragraph.paint(canvas, laid.x, laid.y)
    elif isinstance(it, ImageItem):
        canvas.drawImageRect(it.skimage(), p.src, p.dst, skia.SamplingOptions(skia.CubicResampler.Mitchell()), None)
    elif isinstance(it, ShapeItem):
        path = _shape_path(it, p.bounds)
        if it.fill is not None and it.kind != "line":
            canvas.drawPath(path, fill_paint(it.fill, p.bounds))
        if it.stroke is not None and it.stroke_width > 0:
            sp = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=it.stroke_width,
                            StrokeCap=skia.Paint.kRound_Cap, StrokeJoin=skia.Paint.kRound_Join)
            sp.setColor4f(skia.Color4f(*it.stroke))
            canvas.drawPath(path, sp)
    else:
        _draw_list(canvas, p.children, reg)


def _draw_one(canvas: skia.Canvas, p: Placed, reg: FontRegistry, blend_override=None) -> None:
    st = p.item.style
    blend = blend_override or BLEND_MODES.get(st.blend, skia.BlendMode.kSrcOver)
    filt = effects_filter(st.effects)
    if st.opacity < 1.0 or blend != skia.BlendMode.kSrcOver or filt is not None:
        paint = skia.Paint(Alphaf=max(0.0, min(1.0, st.opacity)), BlendMode=blend)
        if filt is not None:
            paint.setImageFilter(filt)
        # Only as big as the item plus what its effects reach (not the whole canvas).
        r = effect_reach(st.effects) + 2
        x0, y0, x1, y1 = p.bounds
        canvas.saveLayer(skia.Rect.MakeLTRB(x0 - r, y0 - r, x1 + r, y1 + r), paint)
        _draw_content(canvas, p, reg)
        canvas.restore()
    else:
        _draw_content(canvas, p, reg)


def _draw_list(canvas: skia.Canvas, placed: list[Placed], reg: FontRegistry) -> None:
    i = 0
    while i < len(placed):
        # An item with clip_to_previous is drawn only where the item before it is.
        j = i + 1
        while j < len(placed) and placed[j].item.style.clip_to_previous:
            j += 1
        if j == i + 1:
            _draw_one(canvas, placed[i], reg)
        else:
            canvas.saveLayer()
            _draw_one(canvas, placed[i], reg)
            for k in range(i + 1, j):
                _draw_one(canvas, placed[k], reg, blend_override=skia.BlendMode.kSrcATop)
            canvas.restore()
        i = j


def _paint_scene(canvas: skia.Canvas, scene: Scene, reg: FontRegistry) -> None:
    bg = scene.background
    if isinstance(bg, Gradient) or bg[3] > 0:
        canvas.drawRect(skia.Rect.MakeWH(scene.width, scene.height), fill_paint(bg, (0, 0, scene.width, scene.height)))
    _draw_list(canvas, place_items(scene.items, reg), reg)


def render(scene: Scene, scale: float = 1.0, reg: FontRegistry | None = None) -> np.ndarray:
    """H x W x 4 float32 straight alpha at ``scale`` x the canvas size."""
    reg = reg or registry()
    w, h = max(1, round(scene.width * scale)), max(1, round(scene.height * scale))
    surf = surface(w, h)
    canvas = surf.getCanvas()
    canvas.clear(skia.ColorTRANSPARENT)
    canvas.scale(scale, scale)
    _paint_scene(canvas, scene, reg)
    return to_rgba(surf)


def to_pdf(scene: Scene, path: str, dpi: float = 300.0, reg: FontRegistry | None = None) -> None:
    """Vector RGB PDF of the scene (text stays text) via skia's PDF backend."""
    reg = reg or registry()
    s = 72.0 / dpi
    stream = skia.FILEWStream(path)
    with skia.PDF.MakeDocument(stream) as doc:
        with doc.page(scene.width * s, scene.height * s) as canvas:
            canvas.scale(s, s)
            _paint_scene(canvas, scene, reg)
    stream.flush()
