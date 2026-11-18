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
import threading
from collections import OrderedDict

from comfy_api.latest import IO

from . import color as col
from . import nodes_canvas, nodes_color, nodes_effects, nodes_shapes, nodes_type
from . import preview as pv
from . import scene as sc
from . import text as textmod
from .nodes_common import QUIET  # set while rendering a preview: no licence warnings in the log

MAX_W, MAX_H = 320, 200

_KINDS = {
    "CNCanvas": "canvas", "CNTextBox": "part", "CNShape": "part",
    "CNLinearGradient": "fill", "CNRadialGradient": "fill",
    "CNPalette": "palette", "CNSafeArea": "safe", "CNContrast": "contrast",
    "CNDropShadow": "effect", "CNOuterGlow": "effect", "CNOutline": "effect", "CNBlur": "effect",
    "CNOpacityBlend": "effect", "CNClipToPrevious": "effect",
}


def _classes() -> dict:
    mods = (nodes_canvas, nodes_type, nodes_shapes, nodes_color, nodes_effects)
    return {c.define_schema().node_id: c for m in mods for c in m.NODES}


_CLASS_CACHE: dict = {}


def node_class(node_type: str):
    if not _CLASS_CACHE:
        _CLASS_CACHE.update(_classes())
    return _CLASS_CACHE.get(node_type)


def previewable() -> list[str]:
    return sorted(k for k in _KINDS if node_class(k) is not None)


def widget_kwargs(cls, widgets: dict) -> dict:
    """Only the node's own widget inputs, with simple values (no links, no unknown names)."""
    schema = cls.define_schema()
    names = {i.id for i in schema.inputs if isinstance(i, IO.WidgetInput)}
    return {k: v for k, v in widgets.items() if k in names and isinstance(v, (str, int, float, bool))}


def _sample() -> sc.Scene:
    """A small design for nodes that change an existing one: a teal panel and coral "Aa"."""
    s = sc.Scene(1, 1).add(sc.ShapeItem("rectangle", 0, 40, 220, 120, (0.1, 0.65, 0.63, 1.0), radius=14))
    spec = textmod.TextSpec("Aa", "Montserrat", 900, size=150, color=(1.0, 0.42, 0.36, 1.0), x=30, y=0, width=320)
    return s.add(sc.TextItem(spec))


def _note(out) -> str:
    ui = getattr(out, "ui", None)
    if ui is None:
        return ""
    d = ui.as_dict() if hasattr(ui, "as_dict") else ui
    text = d.get("text") if isinstance(d, dict) else None
    return " ".join(map(str, text)) if text else ""


def render(node_type: str, widgets: dict) -> tuple[bytes, str]:
    """(PNG, note) for one node's current widget values."""
    cls = node_class(node_type)
    kind = _KINDS.get(node_type)
    if cls is None or kind is None:
        raise ValueError(f"no live preview for {node_type}")
    kw = widget_kwargs(cls, widgets)
    QUIET.on = True
    try:
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
        img = pv.preview(sc.Scene(MAX_W, 90, result), 1.0)
    elif kind == "palette":
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

    @routes.post("/cratenode/preview")
    async def _preview(request):
        import asyncio

        try:
            data = await request.json()
            png, note = await asyncio.get_running_loop().run_in_executor(
                None, render_cached, str(data.get("type", "")), dict(data.get("widgets") or {}))
        except Exception as e:  # a half-typed colour, a missing font, ...
            return web.json_response({"error": str(e)[:300]}, status=400)
        return web.Response(body=png, content_type="image/png", headers={"X-CN-Note": note.encode(
            "ascii", "replace").decode()[:300]})

    _ROUTES_ADDED = True
    logging.info("CrateNode-Comfy: live previews for %d node types", len(previewable()))
