"""Types, inputs and helpers shared by every node family."""

from __future__ import annotations

import threading
from dataclasses import replace

from comfy_api.latest import IO

from . import render, text
from . import scene as sc
from .fonts import registry

SceneT = IO.Custom("CN_SCENE")
FillT = IO.Custom("CN_FILL")
RowT = IO.Custom("CN_ROW")  # one data row: {column: text}
PaletteT = IO.Custom("CN_PALETTE")  # color.Palette

ROOT = "CrateNode-Comfy"
MASK_MEANINGS = ["LoadImage (1 = transparent)", "alpha (1 = opaque)"]
TARGETS = ["last item", "whole scene"]

# name: (width, height)
CANVAS_PRESETS = {
    "custom": None,
    "YouTube thumbnail / HD 1920x1080": (1920, 1080),
    "4K UHD 3840x2160": (3840, 2160),
    "Instagram square 1080x1080": (1080, 1080),
    "Instagram portrait 1080x1350": (1080, 1350),
    "Story / Reel / TikTok 1080x1920": (1080, 1920),
    "Facebook cover 1640x624": (1640, 624),
    "X / Twitter header 1500x500": (1500, 500),
    "LinkedIn banner 1584x396": (1584, 396),
    "Slide 16:9 1920x1080": (1920, 1080),
    "US Letter @300dpi 2550x3300": (2550, 3300),
    "A4 @300dpi 2480x3508": (2480, 3508),
    "Tabloid 11x17 @300dpi 3300x5100": (3300, 5100),
    "Poster 18x24 @150dpi 2700x3600": (2700, 3600),
    "Postcard 6x4 @300dpi 1800x1200": (1800, 1200),
    # print sizes with 1/8 in (3 mm for A4) bleed on every side: trim + 2 x bleed
    "US Letter + 1/8in bleed @300dpi 2625x3375": (2625, 3375),
    "A4 + 3mm bleed @300dpi 2551x3579": (2551, 3579),
    "Postcard 6x4 + 1/8in bleed @300dpi 1875x1275": (1875, 1275),
}


def font_options() -> list[str]:
    fams = registry().families()
    return fams or ["Inter"]


def default_font(prefer=("Montserrat", "Inter")) -> str:
    fams = font_options()
    for p in prefer:
        if p in fams:
            return p
    return fams[0]


def color(s: str) -> tuple:
    return render.parse_color(s)


QUIET = threading.local()  # live previews set QUIET.on: no warnings in the log for them


def font_warnings(items) -> list[str]:
    """Licence warnings for the fonts the text in ``items`` uses (never an error).
    Scoped licences are checked against ``licence_scope`` in the config."""
    import logging

    from .template import walk

    reg = registry()
    scope = reg.config.licence_scope or None
    out = []
    for it in walk(tuple(items)):
        if not isinstance(it, sc.TextItem):
            continue
        sp = it.spec
        weights = {sp.weight} | ({sp.bold_weight} if "*" in sp.text else set())
        for w in sorted(weights):
            face = reg.resolve(sp.family, w, sp.italic)
            msg = reg.licence_warning(face, scope) if face is not None else None
            if msg and msg not in out:
                out.append(msg)
    if not getattr(QUIET, "on", False):
        for m in out:
            logging.warning("CrateNode-Comfy font licence: %s", m)
    return out


def with_warnings(report: str, items) -> str:
    w = font_warnings(items)
    return report + "".join(f"\nFONT LICENCE: {m}" for m in w)


def new_part(scene):
    """The scene to add to, or a fresh transparent part (for Stack, Place, Grid)."""
    return scene if scene is not None else sc.Scene(1920, 1080)


def flow_inputs() -> list:
    return [
        IO.Boolean.Input("below_previous", default=False,
                         tooltip="Sit under the previous item (its bottom + gap) instead of at y"),
        IO.Float.Input("gap", default=24.0, min=-2000, max=2000, step=1.0),
        IO.String.Input("slot", default="", optional=True, tooltip="A name for this item in a template "
                        "(Fill Template replaces its text, image or colour by this name)"),
    ]


def flow(kw) -> sc.Flow:
    return sc.Flow(kw.pop("below_previous", False), kw.pop("gap", 24.0))


def slot(kw) -> str:
    return (kw.pop("slot", "") or "").strip()


def text_inputs() -> list:
    return [
        IO.String.Input("text", default="Your *headline* here", multiline=True,
                        tooltip="*words* use the bold weight; \\* is a literal star; new lines break"),
        IO.Combo.Input("font", options=font_options(), default=default_font(),
                       tooltip="Fonts from your font folders and the bundled fonts"),
        IO.String.Input("font_override", default="", advanced=True,
                        tooltip="Any installed system font family; used instead of 'font' when set"),
        IO.Int.Input("weight", default=700, min=100, max=1000, step=100),
        IO.Int.Input("bold_weight", default=900, min=100, max=1000, step=100, tooltip="Weight for *marked* words"),
        IO.Boolean.Input("italic", default=False),
        IO.Float.Input("size", default=96.0, min=4.0, max=4000.0, step=1.0, tooltip="Font size in pixels"),
        IO.String.Input("color", default="#ffffff", tooltip="#rrggbb or #rrggbbaa"),
        IO.Combo.Input("align", options=text.ALIGNS, default="center"),
        IO.Combo.Input("valign", options=text.VALIGNS, default="top",
                       tooltip="With a box height: bottom keeps the last line in place, extra lines grow upward"),
        IO.Combo.Input("case", options=text.CASES, default="as typed"),
        IO.Float.Input("x", default=96.0, min=-20000, max=20000, step=1.0),
        IO.Float.Input("y", default=96.0, min=-20000, max=20000, step=1.0),
        IO.Float.Input("box_width", default=1728.0, min=0.0, max=40000, step=1.0, tooltip="Wrap width; 0 = no wrapping"),
        IO.Float.Input("box_height", default=0.0, min=0.0, max=40000, step=1.0, tooltip="0 = as tall as the text"),
        IO.Boolean.Input("auto_fit", default=False, tooltip="Shrink the font until the text fits the box"),
        IO.Float.Input("min_size", default=12.0, min=1.0, max=4000.0, step=1.0, advanced=True),
        IO.Float.Input("line_height", default=1.15, min=0.5, max=4.0, step=0.05, advanced=True),
        IO.Float.Input("letter_spacing", default=0.0, min=-100.0, max=400.0, step=0.5, advanced=True),
    ]


def text_spec(kw: dict) -> text.TextSpec:
    family = (kw.get("font_override") or "").strip() or kw["font"]
    return text.TextSpec(
        text=kw["text"], family=family, weight=kw["weight"], bold_weight=kw["bold_weight"],
        italic=kw["italic"], size=kw["size"], color=color(kw["color"]), align=kw["align"],
        valign=kw["valign"], case=kw["case"], x=kw["x"], y=kw["y"], width=kw["box_width"],
        height=kw["box_height"], auto_fit=kw["auto_fit"], min_size=kw["min_size"],
        line_height=kw["line_height"], letter_spacing=kw["letter_spacing"],
    )


def target_input() -> IO.Combo.Input:
    return IO.Combo.Input("target", options=TARGETS, default=TARGETS[0],
                          tooltip="last item: the item added just before; whole scene: everything so far, as one")


def apply_to_target(scene: sc.Scene, target: str, fn) -> sc.Scene:
    """Change the last item, or wrap everything into one group and change that."""
    if not scene.items:
        raise ValueError("the scene has no items yet; add something first")
    if target == "whole scene":
        return replace(scene, items=(fn(sc.GroupItem(items=scene.items)),))
    return scene.map_last(fn)


def mask_to_alpha(mask, meaning: str):
    """Our MASK convention is coverage (1 = opaque); LoadImage's is 1 = transparent."""
    if mask is None:
        return None
    return 1.0 - mask if meaning == MASK_MEANINGS[0] else mask
