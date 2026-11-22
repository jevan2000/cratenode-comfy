"""Canvas, fills (gradients), safe areas and images in and out of scenes."""

from __future__ import annotations

import dataclasses
from dataclasses import replace

from comfy_api.latest import IO

from . import color as col
from . import convert, fluid, render
from . import scene as sc
from .nodes_common import (CANVAS_PRESETS, MASK_MEANINGS, ROOT, FillT, PaletteT, SceneT, color, flow, flow_inputs,
                           mask_to_alpha, new_part, slot)


BATCH_MODES = ["one image (batch_index)", "every image (one design each)"]
TRANSPARENT = (0.0, 0.0, 0.0, 0.0)


class CNCanvas(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNCanvas", display_name="Canvas", category=f"{ROOT}/Canvas",
            description="Start a design: size (preset or custom), background colour, fill or transparent, and "
                        "safe-area margins.",
            inputs=[
                IO.Combo.Input("preset", options=list(CANVAS_PRESETS), default="YouTube thumbnail / HD 1920x1080"),
                IO.Boolean.Input("landscape_flip", default=False, tooltip="Swap width and height"),
                IO.Int.Input("width", default=1920, min=1, max=16384, tooltip="Used when preset is custom"),
                IO.Int.Input("height", default=1080, min=1, max=16384, tooltip="Used when preset is custom"),
                IO.String.Input("background", default="#000000",
                                tooltip="#rrggbb or #rrggbbaa, or 'transparent'"),
                FillT.Input("background_fill", optional=True, tooltip="A gradient; replaces the background colour"),
                IO.Float.Input("safe_margin", default=5.0, min=0.0, max=45.0, step=0.5,
                               tooltip="Safe area inset, % of the shorter side (layout nodes can use it)"),
                # Last on purpose: saved workflows store widget values by position.
                IO.Boolean.Input("transparent", default=False, optional=True,
                                 tooltip="No background: overlays, logos, PNG/WebP/MOV with alpha. "
                                         "Overrides the background colour and fill"),
            ],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, preset, landscape_flip, width, height, background, safe_margin, background_fill=None,
                transparent=False):
        w, h = CANVAS_PRESETS.get(preset) or (width, height)
        if landscape_flip:
            w, h = h, w
        m = min(w, h) * safe_margin / 100.0
        if transparent or background.strip().lower() in ("transparent", "none", ""):
            bg = TRANSPARENT
        else:
            bg = background_fill if background_fill is not None else color(background)
        return IO.NodeOutput(sc.Scene(w, h, bg, margin=(m, m, m, m)))


class CNSafeArea(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSafeArea", display_name="Safe Area", category=f"{ROOT}/Canvas",
            description="Set the safe-area margins in pixels (layout nodes with area = safe area use them).",
            inputs=[SceneT.Input("scene")] + [
                IO.Float.Input(n, default=96.0, min=0.0, max=10000.0, step=1.0) for n in ("left", "top", "right", "bottom")
            ],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene, left, top, right, bottom):
        return IO.NodeOutput(replace(scene, margin=(left, top, right, bottom)))


def _stops(kw, n=4):
    stops = []
    for i in range(1, n + 1):
        c = (kw.get(f"color_{i}") or "").strip()
        if c:
            stops.append((kw[f"position_{i}"], color(c)))
    if len(stops) < 2:
        raise ValueError("a gradient needs at least two colours")
    return tuple(sorted(stops, key=lambda s: s[0]))


def _stop_inputs(defaults):
    out = []
    for i, (c, p) in enumerate(defaults, 1):
        out += [IO.String.Input(f"color_{i}", default=c, tooltip="#rrggbb[aa]; empty = unused"),
                IO.Float.Input(f"position_{i}", default=p, min=0.0, max=1.0, step=0.01)]
    return out


class CNLinearGradient(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNLinearGradient", display_name="Linear Gradient", category=f"{ROOT}/Fill",
            description="A gradient fill for canvases, shapes and text. Angle 90 = top to bottom.",
            inputs=[IO.Float.Input("angle", default=90.0, min=-360.0, max=360.0, step=1.0)]
                   + _stop_inputs([("#0b1020", 0.0), ("#0f3b40", 1.0), ("", 0.5), ("", 0.75)]),
            outputs=[FillT.Output(display_name="fill")],
        )

    @classmethod
    def execute(cls, angle, **kw):
        return IO.NodeOutput(sc.Gradient("linear", _stops(kw), angle))


class CNRadialGradient(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNRadialGradient", display_name="Radial Gradient", category=f"{ROOT}/Fill",
            description="A gradient from the centre of whatever it fills outward.",
            inputs=_stop_inputs([("#ffffff", 0.0), ("#000000", 1.0), ("", 0.5), ("", 0.75)]),
            outputs=[FillT.Output(display_name="fill")],
        )

    @classmethod
    def execute(cls, **kw):
        return IO.NodeOutput(sc.Gradient("radial", _stops(kw)))


FLUID_COLORS = ["#ff5a1f", "#ff2fa0", "#7a2cff", "#1b3cff", "#13d3ff", ""]


class CNFluidGradient(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        f = lambda name, d, lo, hi, step, tip, adv=False: IO.Float.Input(  # noqa: E731
            name, default=d, min=lo, max=hi, step=step, tooltip=tip, advanced=adv)
        return IO.Schema(
            node_id="CNFluidGradient", display_name="Fluid Gradient", category=f"{ROOT}/Fill",
            description="A flowing, abstract gradient fill (mesh blobs, liquid, twirl, strange marbling, waves, "
                        "motion blur, glass) for canvases, shapes and text. Same settings + seed = same picture; "
                        "change the seed for a new one.",
            inputs=[
                IO.Combo.Input("style", options=fluid.STYLES, default="liquid",
                               tooltip="mesh: soft colour blobs. liquid: silky flowing marble. twirl: a swirl. "
                                       "strange: tight psychedelic marbling. waves: flowing stripes. "
                                       "motion blur: streaked flow. glass: liquid glass with highlights"),
            ] + [IO.String.Input(f"color_{i}", default=c, tooltip="#rrggbb[aa] or a palette name; empty = unused")
                 for i, c in enumerate(FLUID_COLORS, 1)] + [
                IO.Int.Input("seed", default=0, min=0, max=2**31 - 1, control_after_generate=False,
                             tooltip="A different seed gives a different arrangement"),
                f("scale", 1.0, 0.1, 10.0, 0.05, "Feature size: larger = bigger, calmer shapes"),
                f("warp", 1.0, 0.0, 5.0, 0.05, "How much the shapes flow and bend (times the style's own amount)"),
                IO.Int.Input("detail", default=3, min=1, max=8, tooltip="Noise layers: more = finer ripples"),
                f("softness", 1.0, 0.05, 4.0, 0.05, "How softly colours blend; lower = crisper edges"),
                f("bands", 0.0, 0.0, 20.0, 0.5, "Extra repeats of the colours: ripples and stripes"),
                IO.Int.Input("blobs", default=2, min=1, max=6, tooltip="mesh / twirl: points per colour"),
                f("twirl", 0.0, -1440.0, 1440.0, 5.0, "Degrees of swirl, added to the style's own"),
                f("twirl_x", 0.5, -0.5, 1.5, 0.01, "Swirl centre across the fill (0 = left, 1 = right)"),
                f("twirl_y", 0.5, -0.5, 1.5, 0.01, "Swirl centre down the fill (0 = top, 1 = bottom)"),
                f("twirl_radius", 0.6, 0.05, 3.0, 0.01, "How far the swirl reaches, in fill heights"),
                f("rotation", 0.0, -360.0, 360.0, 1.0, "Turns the whole pattern"),
                f("stretch", 1.0, 0.1, 10.0, 0.05, "Above 1 stretches the shapes sideways, below 1 upright"),
                f("blur", 0.0, 0.0, 2.0, 0.01, "Motion blur length in fill heights, added to the style's own"),
                f("blur_angle", 0.0, -360.0, 360.0, 1.0, "Motion blur direction; 0 = left to right"),
                f("glass", 0.0, 0.0, 2.0, 0.05, "Glassy highlights and refraction, added to the style's own"),
                f("grain", 0.02, 0.0, 1.0, 0.01, "Film grain (also hides banding)"),
                f("brightness", 0.0, -1.0, 1.0, 0.01, "Lighter or darker"),
                f("contrast", 1.0, 0.0, 3.0, 0.01, "1 = as the colours are"),
                f("saturation", 1.0, 0.0, 3.0, 0.01, "0 = grey, 1 = as the colours are"),
                f("hue_shift", 0.0, -180.0, 180.0, 1.0, "Turns every colour around the colour wheel"),
                f("vignette", 0.0, 0.0, 1.0, 0.01, "Darker edges"),
                f("evolve", 0.0, -1000.0, 1000.0, 0.01, "Moves through the pattern; animate or step it for a "
                                                         "flowing gradient"),
                PaletteT.Input("palette", optional=True,
                               tooltip="Use these colours (in order) instead of color_1..6, or resolve colour names"),
            ],
            outputs=[FillT.Output(display_name="fill")],
        )

    @classmethod
    def execute(cls, style, seed, palette=None, **kw):
        if palette is not None and getattr(palette, "colors", ()):
            cols = [c for _, c in palette.colors][:8]
        else:
            cols = [col.resolve_color(c, palette) for i in range(1, 7) if (c := (kw.get(f"color_{i}") or "").strip())]
        if len(cols) < 2:
            raise ValueError("a fluid gradient needs at least two colours")
        n = len(cols)
        stops = tuple((i / (n - 1), tuple(float(v) for v in c)) for i, c in enumerate(cols))
        names = {f.name for f in dataclasses.fields(fluid.FluidGradient)} - {"kind", "stops", "angle", "style", "seed"}
        opts = {k: v for k, v in kw.items() if k in names}
        return IO.NodeOutput(fluid.FluidGradient(stops=stops, style=style, seed=int(seed), **opts))


class CNAddImage(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNAddImage", display_name="Add Image", category=f"{ROOT}/Image",
            description="Put an image (e.g. an AI background or a logo) into a box: fit, fill (crop) or stretch. "
                        "Box size 0 = to the canvas edge.",
            inputs=[
                SceneT.Input("scene", optional=True),
                IO.Image.Input("image"),
                IO.Mask.Input("mask", optional=True),
                IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[0]),
                IO.Combo.Input("mode", options=render.FIT_MODES, default="fill"),
                IO.Float.Input("x", default=0.0, min=-20000, max=20000),
                IO.Float.Input("y", default=0.0, min=-20000, max=20000),
                IO.Float.Input("box_width", default=0.0, min=0.0, max=40000),
                IO.Float.Input("box_height", default=0.0, min=0.0, max=40000),
                IO.Int.Input("batch_index", default=0, min=0, max=4096, advanced=True,
                             tooltip="Which image of a batch to use"),
            ] + flow_inputs(),
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, image, mode, x, y, box_width, box_height, scene=None, mask=None,
                mask_meaning=MASK_MEANINGS[0], batch_index=0, **kw):
        scene = new_part(scene)
        i = min(batch_index, image.shape[0] - 1)
        rgba = render.comfy_to_rgba(image, mask_to_alpha(mask, mask_meaning), index=i)
        w = box_width or (scene.width - x)
        h = box_height or (scene.height - y)
        return IO.NodeOutput(scene.add(sc.ImageItem(rgba, x, y, w, h, mode, flow=flow(kw), name=slot(kw))))


class CNImageToScene(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNImageToScene", display_name="Image to Scene", category=f"{ROOT}/Image",
            search_aliases=["image to scene", "convert image", "embed image", "AI image into design"],
            description="Bring an image (an AI generation, a photo, any IMAGE) into a design. Without a scene: a new "
                        "canvas the image's size. With a scene: the image goes under the design (an AI background "
                        "behind sharp type), on top of it, or replaces it while keeping the canvas, fitted to the "
                        "canvas (fill crops, fit letterboxes). A batch can give one design per image (a list: "
                        "the rest of the graph runs once per image).",
            inputs=[IO.Image.Input("image"), IO.Mask.Input("mask", optional=True),
                    IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[0]),
                    IO.Float.Input("safe_margin", default=5.0, min=0.0, max=45.0, step=0.5,
                                   tooltip="For a new canvas"),
                    SceneT.Input("scene", optional=True, tooltip="Put the image into this design"),
                    IO.Combo.Input("place", options=convert.PLACES, default=convert.PLACES[0], optional=True,
                                   tooltip="Where the image goes when a scene is connected"),
                    IO.Combo.Input("fit", options=convert.FITS, default="fill", optional=True,
                                   tooltip="How the image covers the canvas: fill crops, fit letterboxes"),
                    IO.Combo.Input("batch", options=BATCH_MODES, default=BATCH_MODES[0], optional=True),
                    IO.Int.Input("batch_index", default=0, min=0, max=4096, optional=True,
                                 tooltip="Which image of a batch, for 'one image'"),
                    IO.String.Input("slot", default="", optional=True,
                                    tooltip="A name for the image item (an image slot in a template)")],
            outputs=[SceneT.Output(display_name="scene", is_output_list=True)],
        )

    @classmethod
    def execute(cls, image, safe_margin, mask=None, mask_meaning=MASK_MEANINGS[0], scene=None,
                place=convert.PLACES[0], fit="fill", batch=BATCH_MODES[0], batch_index=0, slot=""):
        alpha = mask_to_alpha(mask, mask_meaning)
        n = image.shape[0]
        indices = range(n) if batch == BATCH_MODES[1] else [min(batch_index, n - 1)]
        scenes = [convert.image_into_scene(render.comfy_to_rgba(image, alpha, index=i), scene, place, fit,
                                           safe_margin, (slot or "").strip()) for i in indices]
        return IO.NodeOutput(scenes)


NODES = [CNCanvas, CNSafeArea, CNLinearGradient, CNRadialGradient, CNFluidGradient, CNAddImage, CNImageToScene]
