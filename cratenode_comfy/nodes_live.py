"""Live previews on the nodes, before anything runs.

The browser (web/live_preview.js) posts a node's type and its current widget values to
``/cratenode/preview``; this module runs that node's own ``execute`` on them and returns
a small PNG. Because the node's real code draws the preview, it always matches what
running the workflow will make (fonts, effects, colours).

Nodes that need an upstream design (effects, Safe Area) are shown applied to a small
sample. Values arriving through links can't be known before running, so their widget
value (the last one set) is used.
"""

from __future__ import annotations

import json
import logging

import numpy as np
import threading
from collections import OrderedDict

from comfy_api.latest import IO

from . import color as col
from . import layout as lay
from . import nodes_canvas, nodes_color, nodes_effects, nodes_layout, nodes_shapes, nodes_type
from . import preview as pv
from . import scene as sc
from . import text as textmod
from .nodes_common import QUIET  # set while rendering a preview: no licence warnings in the log

MAX_W, MAX_H = 320, 200

_KINDS = {
    "CNCanvas": "canvas", "CNTextBox": "part", "CNShape": "part",
    "CNLinearGradient": "fill", "CNRadialGradient": "fill", "CNFluidGradient": "fill",
    "CNPalette": "palette", "CNSafeArea": "safe", "CNContrast": "contrast",
    "CNDropShadow": "effect", "CNOuterGlow": "effect", "CNOutline": "effect", "CNBlur": "effect",
    "CNOpacityBlend": "effect", "CNClipToPrevious": "effect",
    "CNGrid": "grid",
    "CNRandomColor": "random",
    "CNPaletteGenerator": "palette",
}


def _classes() -> dict:
    mods = (nodes_canvas, nodes_type, nodes_shapes, nodes_color, nodes_effects, nodes_layout)
    return {c.define_schema().node_id: c for m in mods for c in m.NODES}


_CLASS_CACHE: dict = {}


def node_class(node_type: str):
    if not _CLASS_CACHE:
        _CLASS_CACHE.update(_classes())
    return _CLASS_CACHE.get(node_type)


def previewable() -> list[str]:
    return sorted(k for k in _KINDS if node_class(k) is not None)


MAX_BODY = 64 * 1024  # bytes per preview request
MAX_TEXT = 4000  # characters per text value


def widget_kwargs(cls, widgets: dict) -> dict:
    """Only the node's own widget inputs, with simple values (no links, no unknown names)."""
    schema = cls.define_schema()
    names = {i.id for i in schema.inputs if isinstance(i, IO.WidgetInput)}
    out = {k: v for k, v in widgets.items() if k in names and isinstance(v, (str, int, float, bool))}
    for k, v in out.items():
        if isinstance(v, str) and len(v) > MAX_TEXT:
            raise ValueError(f"{k} is too long for a live preview ({len(v)} characters; up to {MAX_TEXT})")
    return out


def _sample() -> sc.Scene:
    """A small design for nodes that change an existing one: a teal panel and coral "Aa"."""
    s = sc.Scene(1, 1).add(sc.ShapeItem("rectangle", 0, 40, 220, 120, (0.1, 0.65, 0.63, 1.0), radius=14))
    spec = textmod.TextSpec("Aa", "Montserrat", 900, size=150, color=(1.0, 0.42, 0.36, 1.0), x=30, y=0, width=320)
    return s.add(sc.TextItem(spec))


LAYOUT_CANVAS = (1920, 1080, (96.0, 96.0, 96.0, 96.0))  # the stand-in canvas for layout previews
_TILE_SIZES = [(300, 180), (220, 260), (340, 140), (260, 220), (200, 160), (320, 240), (240, 140),
               (280, 200), (180, 220)]
_TILE_COLORS = ["#19a7a1", "#ff6b5b", "#f2b544", "#5b8def", "#9b6bd6", "#4fbf6a", "#e86aa6", "#3fb6d9",
                "#c98a4b"]


def sample_parts(n: int) -> list[sc.Scene]:
    """Numbered stand-in parts of different sizes, so alignment inside the cells shows."""
    parts = []
    for i in range(n):
        w, h = _TILE_SIZES[i % len(_TILE_SIZES)]
        fill = col.resolve_color(_TILE_COLORS[i % len(_TILE_COLORS)])
        spec = textmod.TextSpec(str(i + 1), "Montserrat", 800, size=min(w, h) * 0.5, color=(1.0, 1.0, 1.0, 0.95),
                                x=0, y=h / 2 - min(w, h) * 0.33, width=w, align="center")
        parts.append(sc.Scene(1, 1).add(sc.ShapeItem("rectangle", 0, 0, w, h, fill, radius=14))
                     .add(sc.TextItem(spec)))
    return parts


def _linked_parts(widgets: dict, most: int) -> int:
    """How many part inputs are connected (the browser sends ``__parts``); 0 = unknown."""
    try:
        return max(0, min(most, int(widgets.get("__parts") or 0)))
    except (TypeError, ValueError):
        return 0


def _grid_preview(cls, kw: dict, widgets: dict):
    """The grid with stand-in parts on a 1920 x 1080 canvas, its area (cyan) and cells (grey)."""
    n = _linked_parts(widgets, nodes_layout.N_GRID) or 6
    w, h, margin = LAYOUT_CANVAS
    base = sc.Scene(w, h, margin=margin)  # transparent, so the guides can go under the parts
    parts = {f"part_{i + 1}": p for i, p in enumerate(sample_parts(n))}
    out = cls.execute(scene=base, **kw, **parts)
    scale = pv.fit_scale(w, h, MAX_W, MAX_H)
    rgba = sc.render(out.args[0], scale)
    img = np.empty(rgba.shape[:2] + (3,), np.float32)
    img[:] = (0.12, 0.13, 0.16)
    bx, by, bw, bh = lay.area_box(base, kw.get("area", "safe area"), kw.get("x", 0.0), kw.get("y", 0.0),
                                  kw.get("box_width", 0.0), kw.get("box_height", 0.0))
    cells, cols, rows = lay.grid_cells(n, (bx, by, bw, bh), kw.get("columns", 3), float(kw.get("gap_x", 24.0)),
                                       float(kw.get("gap_y", 24.0)), kw.get("direction", "vertical"))
    for x0, y0, cw, ch in cells:
        pv._dashed_rect(img, x0 * scale, y0 * scale, (x0 + cw) * scale, (y0 + ch) * scale, (0.45, 0.48, 0.55),
                        1, dash=3)
    pv._dashed_rect(img, bx * scale, by * scale, (bx + bw) * scale, (by + bh) * scale, pv.SAFE, 1)
    a = rgba[:, :, 3:4]
    img = rgba[:, :, :3] * a + img * (1 - a)  # the parts over the guides
    shown = "connected" if _linked_parts(widgets, nodes_layout.N_GRID) else "sample"
    fill = "filling down" if kw.get("direction") == "horizontal" else "filling across"
    on = ", on grid lines" if kw.get("placement") == "on grid line" else ""
    return img, f"{cols} x {rows} cells, {fill}{on}, {n} {shown} parts (stand-ins)"


def _note(out) -> str:
    ui = getattr(out, "ui", None)
    if ui is None:
        return ""
    d = ui.as_dict() if hasattr(ui, "as_dict") else ui
    text = d.get("text") if isinstance(d, dict) else None
    return " ".join(map(str, text)) if text else ""


# Nodes whose output the preview may work out when it arrives through a link: cheap,
# made from widget values only (no scene or image inputs).
RESOLVABLE = {"CNRandomColor"}


def resolve_links(widgets: dict) -> dict:
    """Widget values with linked ones replaced by what their source node gives now.

    The browser sends ``__links``: {input name: {type, slot, widgets}} for inputs fed by
    another CrateNode node. Sources outside RESOLVABLE, or giving anything but plain
    text / numbers, keep the widget's own value."""
    links = widgets.get("__links")
    if not isinstance(links, dict):
        return widgets
    out = dict(widgets)
    for name, spec in list(links.items())[:16]:
        if not isinstance(spec, dict) or spec.get("type") not in RESOLVABLE:
            continue
        cls = _resolvable_class(spec["type"])
        try:
            res = cls.execute(**widget_kwargs(cls, dict(spec.get("widgets") or {})))
            value = res.args[int(spec.get("slot", 0))]
        except Exception:  # a half-typed value upstream: keep the widget's value
            continue
        if isinstance(value, (str, int, float, bool)):
            out[name] = value
    return out


def _resolvable_class(node_type: str):
    return {c.define_schema().node_id: c for c in nodes_color.NODES}.get(node_type)


def render(node_type: str, widgets: dict) -> tuple[bytes, str]:
    """(PNG, note) for one node's current widget values."""
    cls = node_class(node_type)
    kind = _KINDS.get(node_type)
    if cls is None or kind is None:
        raise ValueError(f"no live preview for {node_type}")
    widgets = resolve_links(widgets)
    kw = widget_kwargs(cls, widgets)
    QUIET.on = True
    try:
        if kind == "grid":
            img, note = _grid_preview(cls, kw, widgets)
            return pv.to_png(img), note
        if kind in ("effect", "safe"):
            base = sc.Scene(1920, 1080, (0.12, 0.13, 0.16, 1.0)) if kind == "safe" else _sample()
            out = cls.execute(scene=base, **kw)
        else:
            out = cls.execute(**kw)
    finally:
        QUIET.on = False
    note = _note(out)
    result = out.args[0]
    if kind == "canvas":
        img = pv.preview(result, pv.fit_scale(result.width, result.height, MAX_W, MAX_H), None, "safe area")
        note = note or f"{result.width} x {result.height}"
    elif kind == "safe":
        img = pv.preview(result, pv.fit_scale(1920, 1080, MAX_W, MAX_H), None, "safe area")
    elif kind == "part" or kind == "effect":
        img = pv.part_preview(result, MAX_W, MAX_H)
    elif kind == "fill":
        # a fluid gradient is a picture: show it 16:9; plain gradients fit a strip
        img = pv.preview(sc.Scene(MAX_W, 180 if node_type == "CNFluidGradient" else 90, result), 1.0)
    elif kind in ("palette", "random"):
        if kind == "random":  # the colours this seed gives (the next run, once the seed moves on)
            result = out.args[1]
            note = out.args[3].splitlines()[0] if len(result.colors) == 1 else f"{len(result.colors)} colours"
        s = col.swatch_scene(result, cell=96)
        img = pv.preview(s, min(1.0, pv.fit_scale(s.width, s.height, MAX_W, MAX_H)))
    else:  # contrast: the text colour on the background, with the grade
        ratio, grade = out.args[0], out.args[1]
        fg = col.resolve_color(kw.get("text_color", "#ffffff"))
        bg = col.resolve_color(kw.get("background", "#000000"))
        spec = textmod.TextSpec(f"Aa  {grade}", "Inter", 700, size=34, color=fg, x=0, y=30, width=MAX_W,
                                align="center")
        img = pv.preview(sc.Scene(MAX_W, 110, bg).add(sc.TextItem(spec)), 1.0)
        note = f"contrast {ratio}:1"
    return pv.to_png(img), note


_LRU: OrderedDict = OrderedDict()
_LOCK = threading.Lock()


def render_cached(node_type: str, widgets: dict) -> tuple[bytes, str]:
    key = node_type + json.dumps(widgets, sort_keys=True, default=str)
    with _LOCK:
        if key in _LRU:
            _LRU.move_to_end(key)
            return _LRU[key]
    hit = render(node_type, widgets)
    with _LOCK:
        _LRU[key] = hit
        while len(_LRU) > 64:
            _LRU.popitem(last=False)
    return hit


_ROUTES_ADDED = False


def add_routes() -> None:
    """Register the preview endpoints on ComfyUI's server (once)."""
    global _ROUTES_ADDED
    if _ROUTES_ADDED:
        return
    try:
        from aiohttp import web
        from server import PromptServer
    except Exception:  # not inside ComfyUI (tests, scripts)
        return
    routes = PromptServer.instance.routes

    @routes.get("/cratenode/previewable")
    async def _previewable(request):
        return web.json_response(previewable())

    @routes.get("/cratenode/fluid_presets")
    async def _fluid_presets(request):
        from . import fluid

        return web.json_response({name: fluid.preset_values(name) for name in fluid.PRESETS})

    @routes.post("/cratenode/preview")
    async def _preview(request):
        import asyncio

        if (request.content_length or 0) > MAX_BODY:
            return web.json_response({"error": "preview request too large"}, status=413)
        try:
            data = json.loads((await request.content.read(MAX_BODY + 1))[:MAX_BODY + 1])
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            png, note = await asyncio.get_running_loop().run_in_executor(
                None, render_cached, str(data.get("type", "")), dict(data.get("widgets") or {}))
        except Exception as e:  # a half-typed colour, a missing font, ...
            return web.json_response({"error": str(e)[:300]}, status=400)
        return web.Response(body=png, content_type="image/png", headers={"X-CN-Note": note.encode(
            "ascii", "replace").decode()[:300]})

    @routes.post("/cratenode/palette")
    async def _palette(request):
        """Five new colours for Palette Generator's Generate button (and before runs)."""
        import random as _random

        from . import palettegen as pg

        if (request.content_length or 0) > MAX_BODY:
            return web.json_response({"error": "request too large"}, status=413)
        try:
            data = json.loads((await request.content.read(MAX_BODY + 1))[:MAX_BODY + 1] or b"{}")
            if not isinstance(data, dict):
                raise ValueError("expected a JSON object")
            seed = data.get("seed")
            seed = _random.SystemRandom().randrange(2**31) if seed is None else int(seed)
            colors = pg.generate(seed, str(data.get("harmony", "random")), str(data.get("family", "any")),
                                 str(data.get("style", "any")))
        except Exception as e:  # an unknown harmony, family or style
            return web.json_response({"error": str(e)[:300]}, status=400)
        return web.json_response({"colors": pg.to_hex_list(colors), "seed": seed})

    _ROUTES_ADDED = True
    logging.info("CrateNode-Comfy: live previews for %d node types", len(previewable()))
