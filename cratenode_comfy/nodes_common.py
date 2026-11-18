"""Inputs shared by both spike pipelines."""

from __future__ import annotations

from comfy_api.latest import IO

from . import render, text

MASK_MEANINGS = ["LoadImage (1 = transparent)", "alpha (1 = opaque)"]


def text_inputs() -> list:
    return [
        IO.String.Input("text", default="Your *headline* here", multiline=True,
                        tooltip="*words* use the bold weight; \\* is a literal star"),
        IO.String.Input("font_family", default="Montserrat",
                        tooltip="Family from the font folders, the bundled fonts (Inter, Montserrat) or the system"),
        IO.Int.Input("weight", default=700, min=100, max=1000, step=100),
        IO.Int.Input("bold_weight", default=900, min=100, max=1000, step=100, tooltip="Weight for *marked* words"),
        IO.Float.Input("size", default=96.0, min=4.0, max=2000.0, step=1.0, tooltip="Font size in pixels"),
        IO.String.Input("color", default="#ffffff", tooltip="#rrggbb or #rrggbbaa"),
        IO.Combo.Input("align", options=text.ALIGNS, default="center"),
        IO.Combo.Input("valign", options=text.VALIGNS, default="top",
                       tooltip="With a box height: bottom keeps the last line in place, extra lines grow upward"),
        IO.Combo.Input("case", options=text.CASES, default="as typed"),
        IO.Float.Input("x", default=96.0, min=-10000, max=10000, step=1.0),
        IO.Float.Input("y", default=96.0, min=-10000, max=10000, step=1.0),
        IO.Float.Input("box_width", default=1728.0, min=0.0, max=20000, step=1.0, tooltip="Wrap width; 0 = no wrapping"),
        IO.Float.Input("box_height", default=0.0, min=0.0, max=20000, step=1.0, tooltip="0 = as tall as the text"),
        IO.Boolean.Input("auto_fit", default=False, tooltip="Shrink the font until the text fits the box"),
        IO.Float.Input("min_size", default=12.0, min=1.0, max=2000.0, step=1.0, advanced=True),
        IO.Float.Input("line_height", default=1.15, min=0.5, max=4.0, step=0.05, advanced=True),
        IO.Float.Input("letter_spacing", default=0.0, min=-50.0, max=200.0, step=0.5, advanced=True),
    ]


def text_spec(kw: dict) -> text.TextSpec:
    return text.TextSpec(
        text=kw["text"],
        family=kw["font_family"],
        weight=kw["weight"],
        bold_weight=kw["bold_weight"],
        size=kw["size"],
        color=render.parse_color(kw["color"]),
        align=kw["align"],
        valign=kw["valign"],
        case=kw["case"],
        x=kw["x"],
        y=kw["y"],
        width=kw["box_width"],
        height=kw["box_height"],
        auto_fit=kw["auto_fit"],
        min_size=kw["min_size"],
        line_height=kw["line_height"],
        letter_spacing=kw["letter_spacing"],
    )


def shadow_inputs() -> list:
    return [
        IO.Float.Input("dx", default=0.0, min=-500, max=500, step=1.0),
        IO.Float.Input("dy", default=8.0, min=-500, max=500, step=1.0),
        IO.Float.Input("blur", default=24.0, min=0.0, max=500, step=1.0),
        IO.String.Input("shadow_color", default="#000000"),
        IO.Float.Input("opacity", default=0.6, min=0.0, max=1.0, step=0.05),
    ]


def mask_to_alpha(mask, meaning: str):
    """Our MASK convention is coverage (1 = opaque); LoadImage's is 1 = transparent."""
    if mask is None:
        return None
    return 1.0 - mask if meaning == MASK_MEANINGS[0] else mask
