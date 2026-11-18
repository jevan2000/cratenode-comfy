"""Colour: palettes, palette from image, brand kits, picking colours by name or
contrast, a contrast check, and recolouring a design."""

from __future__ import annotations

import os

import numpy as np
from comfy_api.latest import IO, UI

from . import color as col
from . import render
from . import scene as sc
from .fonts import registry
from .nodes_common import MASK_MEANINGS, ROOT, PaletteT, SceneT, mask_to_alpha

CAT = f"{ROOT}/Colour"
NONE = "(none)"
PICK_MODES = ["by name or number", "best contrast against", "lightest", "darkest"]


def _swatches(palette, shares=None):
    return render.rgba_to_comfy(sc.render(col.swatch_scene(palette, shares=shares)))[0]


def _brands():
    return col.find_brands(registry().config.brand_folders())


class CNPalette(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNPalette", display_name="Palette", category=CAT,
            description="A named colour palette: 'name: #hex' lines, or plain #hex values (named color_1, ...).",
            inputs=[IO.String.Input("colors", multiline=True,
                                    default="primary: #1f6feb\nsecondary: #0b1d3a\naccent: #f2b134\nlight: #f5f7fa\ndark: #111418"),
                    IO.String.Input("name", default="")],
            outputs=[PaletteT.Output(display_name="palette"), IO.Image.Output(display_name="swatches")],
        )

    @classmethod
    def execute(cls, colors, name):
        pal = col.parse_palette(colors, name)
        if not pal.colors:
            raise ValueError("the palette has no colours")
        return IO.NodeOutput(pal, _swatches(pal))


class CNPaletteFromImage(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNPaletteFromImage", display_name="Palette from Image", category=CAT,
            description="The main colours of an image (k-means in Lab colour space, CPU). Similar colours merge; "
                        "transparent pixels (by the mask) are ignored.",
            inputs=[IO.Image.Input("image"), IO.Mask.Input("mask", optional=True),
                    IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[0]),
                    IO.Int.Input("count", default=5, min=1, max=16),
                    IO.Combo.Input("sort", options=col.SORTS, default=col.SORTS[0]),
                    IO.Float.Input("min_distance", default=8.0, min=0.0, max=100.0, step=0.5,
                                   tooltip="Merge colours closer than this (ΔE; ~2 is barely visible)"),
                    IO.Int.Input("seed", default=0, min=0, max=2**31 - 1, advanced=True)],
            outputs=[PaletteT.Output(display_name="palette"), IO.Image.Output(display_name="swatches"),
                     IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, image, count, sort, min_distance, seed, mask=None, mask_meaning=MASK_MEANINGS[0]):
        rgba = render.comfy_to_rgba(image, mask_to_alpha(mask, mask_meaning))
        pal, shares = col.palette_from_image(rgba, count, sort, min_distance, seed=seed)
        report = "\n".join(f"{n}: {col.to_hex(c)}  {s * 100:.1f}%" for (n, c), s in zip(pal.colors, shares))
        return IO.NodeOutput(pal, _swatches(pal, shares), report)


class CNBrandKit(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        names = sorted(_brands())
        return IO.Schema(
            node_id="CNBrandKit", display_name="Brand Kit", category=CAT,
            description="A brand kit (JSON in your data folder's brand/): its palette, heading and body fonts, "
                        "and a logo. Wire the fonts into a Text Box's font_override and the logo into Add Image "
                        "(set its mask_meaning to alpha).",
            inputs=[IO.Combo.Input("kit", options=[NONE] + names, default=names[0] if names else NONE),
                    IO.String.Input("path", default="", tooltip="Any brand kit file; used instead of the list when set"),
                    IO.String.Input("logo", default="primary", tooltip="Which logo of the kit")],
            outputs=[PaletteT.Output(display_name="palette"),
                     IO.String.Output(display_name="heading_font"), IO.Int.Output(display_name="heading_weight"),
                     IO.String.Output(display_name="body_font"), IO.Int.Output(display_name="body_weight"),
                     IO.Image.Output(display_name="logo"), IO.Mask.Output(display_name="logo_alpha"),
                     IO.Image.Output(display_name="swatches"), IO.String.Output(display_name="notes")],
        )

    @classmethod
    def _path(cls, kit, path):
        if (path or "").strip():
            return registry().config.resolve_data_path(path)
        if kit == NONE:
            raise ValueError("pick a brand kit or give a path")
        p = _brands().get(kit)
        if p is None:
            raise ValueError(f"brand kit {kit!r} not found")
        return p

    @classmethod
    def fingerprint_inputs(cls, kit, path, logo):
        try:
            return os.path.getmtime(cls._path(kit, path))
        except (OSError, ValueError):
            return None

    @classmethod
    def execute(cls, kit, path, logo):
        from PIL import Image

        bk = col.load_brand(cls._path(kit, path))
        hf, hw = bk.font("heading")
        bf, bw = bk.font("body")
        lp = bk.logos.get(logo.strip()) or next(iter(bk.logos.values()), None)
        if lp is not None and lp.is_file():
            rgba = np.asarray(Image.open(lp).convert("RGBA"), np.float32) / 255.0
        else:
            rgba = np.zeros((64, 64, 4), np.float32)
        img, alpha = render.rgba_to_comfy(rgba)
        return IO.NodeOutput(bk.palette, hf, hw, bf, bw, img, alpha, _swatches(bk.palette), bk.notes)


class CNPickColor(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNPickColor", display_name="Pick Color", category=CAT,
            description="One palette colour as #hex text, to wire into any colour input: by name or number, the "
                        "most readable against another colour, or the lightest / darkest.",
            inputs=[PaletteT.Input("palette"), IO.Combo.Input("mode", options=PICK_MODES, default=PICK_MODES[0]),
                    IO.String.Input("name", default="primary", tooltip="A colour name, or its number (1 = first)"),
                    IO.String.Input("against", default="#000000",
                                    tooltip="For best contrast: the background (#hex or a palette name)")],
            outputs=[IO.String.Output(display_name="color"), IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, palette, mode, name, against):
        if mode == PICK_MODES[1]:
            bg = col.resolve_color(against, palette)
            n, c, r = col.best_contrast(bg, palette.colors)
            return IO.NodeOutput(col.to_hex(c), f"{n} on {col.to_hex(bg)}: {r:.2f}:1 ({col.wcag_grade(r)})")
        if mode in PICK_MODES[2:]:
            pick = max if mode == "lightest" else min
            n, c = pick(palette.colors, key=lambda nc: col.luminance(nc[1]))
            return IO.NodeOutput(col.to_hex(c), n)
        return IO.NodeOutput(col.to_hex(palette.get(name)), name)


class CNContrast(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNContrast", display_name="Contrast Check", category=CAT,
            description="WCAG contrast ratio of text on a background. Body text needs 4.5:1 (AA), large text 3:1.",
            is_output_node=True,
            inputs=[IO.String.Input("text_color", default="#ffffff"), IO.String.Input("background", default="#1f6feb"),
                    PaletteT.Input("palette", optional=True, tooltip="Lets the colours be palette names"),
                    IO.Boolean.Input("large_text", default=False, tooltip="24px+, or 18.7px+ bold")],
            outputs=[IO.Float.Output(display_name="ratio"), IO.String.Output(display_name="grade")],
        )

    @classmethod
    def execute(cls, text_color, background, large_text, palette=None):
        r = col.contrast(col.resolve_color(text_color, palette), col.resolve_color(background, palette))
        grade = f"{r:.2f}:1 {col.wcag_grade(r, large_text)}"
        return IO.NodeOutput(round(r, 2), grade, ui=UI.PreviewText(grade))


class CNRecolor(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNRecolor", display_name="Recolor Scene", category=CAT,
            description="Swap colours throughout a design (text, shapes, strokes, gradients, effects, background): "
                        "'#from -> #to' lines; with a palette, either side can be a colour name.",
            inputs=[SceneT.Input("scene"),
                    IO.String.Input("mapping", multiline=True, default="#ffffff -> accent"),
                    PaletteT.Input("palette", optional=True),
                    IO.Float.Input("tolerance", default=0.02, min=0.0, max=1.0, step=0.01,
                                   tooltip="How close a colour must be (per channel, 0..1) to be swapped")],
            outputs=[SceneT.Output(display_name="scene"), IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, scene, mapping, tolerance, palette=None):
        out, n = col.recolor(scene, col.parse_mapping(mapping, palette), tolerance)
        return IO.NodeOutput(out, f"{n} colour{'s' if n != 1 else ''} changed")


NODES = [CNPalette, CNPaletteFromImage, CNBrandKit, CNPickColor, CNContrast, CNRecolor]
