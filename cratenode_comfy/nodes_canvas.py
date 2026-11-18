"""Canvas, fills (gradients), safe areas and images in and out of scenes."""

from __future__ import annotations

from dataclasses import replace

from comfy_api.latest import IO

from . import render
from . import scene as sc
from .nodes_common import (CANVAS_PRESETS, MASK_MEANINGS, ROOT, FillT, SceneT, color, flow, flow_inputs,
                           mask_to_alpha, new_part)


class CNCanvas(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNCanvas", display_name="Canvas", category=f"{ROOT}/Canvas",
            description="Start a design: size (preset or custom), background colour or fill, and safe-area margins.",
            inputs=[
                IO.Combo.Input("preset", options=list(CANVAS_PRESETS), default="YouTube thumbnail / HD 1920x1080"),
                IO.Boolean.Input("landscape_flip", default=False, tooltip="Swap width and height"),
                IO.Int.Input("width", default=1920, min=1, max=16384, tooltip="Used when preset is custom"),
                IO.Int.Input("height", default=1080, min=1, max=16384, tooltip="Used when preset is custom"),
                IO.String.Input("background", default="#000000", tooltip="#rrggbb or #rrggbbaa (alpha 00 = transparent)"),
                FillT.Input("background_fill", optional=True, tooltip="A gradient; replaces the background colour"),
                IO.Float.Input("safe_margin", default=5.0, min=0.0, max=45.0, step=0.5,
                               tooltip="Safe area inset, % of the shorter side (layout nodes can use it)"),
            ],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, preset, landscape_flip, width, height, background, safe_margin, background_fill=None):
        w, h = CANVAS_PRESETS.get(preset) or (width, height)
        if landscape_flip:
            w, h = h, w
        m = min(w, h) * safe_margin / 100.0
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
        return IO.NodeOutput(scene.add(sc.ImageItem(rgba, x, y, w, h, mode, flow=flow(kw))))


class CNImageToScene(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNImageToScene", display_name="Image to Scene", category=f"{ROOT}/Image",
            description="Start a design from an image: the canvas takes the image's size and the image fills it.",
            inputs=[IO.Image.Input("image"), IO.Mask.Input("mask", optional=True),
                    IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[0]),
                    IO.Float.Input("safe_margin", default=5.0, min=0.0, max=45.0, step=0.5)],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, image, safe_margin, mask=None, mask_meaning=MASK_MEANINGS[0]):
        rgba = render.comfy_to_rgba(image, mask_to_alpha(mask, mask_meaning))
        h, w = rgba.shape[:2]
        m = min(w, h) * safe_margin / 100.0
        return IO.NodeOutput(sc.Scene(w, h, margin=(m, m, m, m)).add(sc.ImageItem(rgba, 0, 0, w, h, "stretch")))


NODES = [CNCanvas, CNSafeArea, CNLinearGradient, CNRadialGradient, CNAddImage, CNImageToScene]
