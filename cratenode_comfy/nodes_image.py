"""Spike pipeline B: every node outputs pixels (IMAGE + MASK at canvas size) and
layers are composited with masks, the way most ComfyUI packs work.

MASK here is coverage (1 = opaque). LoadImage's MASK is the opposite
(1 = transparent); nodes that take a mask say which they expect.
"""

from __future__ import annotations

import numpy as np
import skia

from comfy_api.latest import IO

from . import render
from . import scene as scene_mod
from .nodes_common import MASK_MEANINGS, mask_to_alpha, shadow_inputs, text_inputs, text_spec

CAT = "CrateNode-Comfy/spike: image"


def _canvas_inputs():
    return [
        IO.Int.Input("canvas_width", default=1920, min=1, max=16384),
        IO.Int.Input("canvas_height", default=1080, min=1, max=16384),
    ]


class CNImgCanvas(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNImgCanvas",
            display_name="Canvas (image)",
            category=CAT,
            inputs=_canvas_inputs() + [IO.String.Input("color", default="#000000")],
            outputs=[IO.Image.Output(display_name="image")],
        )

    @classmethod
    def execute(cls, canvas_width, canvas_height, color) -> IO.NodeOutput:
        s = scene_mod.Scene(canvas_width, canvas_height, render.parse_color(color))
        img, _ = render.rgba_to_comfy(scene_mod.render(s))
        return IO.NodeOutput(img)


class CNImgText(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNImgText",
            display_name="Text Layer (image)",
            category=CAT,
            description="Text on a transparent canvas-sized layer. 'bottom' is the y of the text's last line, "
                        "for wiring the next layer's y.",
            inputs=_canvas_inputs() + text_inputs() + [
                IO.Float.Input("below_y", optional=True, force_input=True,
                               tooltip="Connect another text layer's 'bottom' to start below it (y is then ignored)"),
                IO.Float.Input("gap", default=24.0, min=-1000, max=1000, tooltip="Space under below_y"),
            ],
            outputs=[
                IO.Image.Output(display_name="image"),
                IO.Mask.Output(display_name="mask"),
                IO.Float.Output(display_name="bottom"),
            ],
        )

    @classmethod
    def execute(cls, canvas_width, canvas_height, gap=24.0, below_y=None, **kw) -> IO.NodeOutput:
        if below_y is not None:
            kw = dict(kw, y=below_y + gap)
        item = scene_mod.TextItem(text_spec(kw))
        s = scene_mod.Scene(canvas_width, canvas_height).add(item)
        bottom = scene_mod.resolve(s)[0].bounds[3]
        img, mask = render.rgba_to_comfy(scene_mod.render(s))
        return IO.NodeOutput(img, mask, float(bottom))


class CNImgPlace(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNImgPlace",
            display_name="Place Image (image)",
            category=CAT,
            description="Fit, fill or stretch an image into a box on a transparent canvas-sized layer.",
            inputs=_canvas_inputs() + [
                IO.Image.Input("image"),
                IO.Mask.Input("mask", optional=True),
                IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[0]),
                IO.Combo.Input("mode", options=render.FIT_MODES, default="fit"),
                IO.Float.Input("x", default=0.0, min=-10000, max=10000),
                IO.Float.Input("y", default=0.0, min=-10000, max=10000),
                IO.Float.Input("box_width", default=0.0, min=0.0, max=20000),
                IO.Float.Input("box_height", default=0.0, min=0.0, max=20000),
            ],
            outputs=[IO.Image.Output(display_name="image"), IO.Mask.Output(display_name="mask")],
        )

    @classmethod
    def execute(cls, canvas_width, canvas_height, image, mode, x, y, box_width, box_height,
                mask=None, mask_meaning=MASK_MEANINGS[0]) -> IO.NodeOutput:
        rgba = render.comfy_to_rgba(image, mask_to_alpha(mask, mask_meaning))
        w = box_width or (canvas_width - x)
        h = box_height or (canvas_height - y)
        s = scene_mod.Scene(canvas_width, canvas_height).add(scene_mod.ImageItem(rgba, x, y, w, h, mode))
        img, m = render.rgba_to_comfy(scene_mod.render(s))
        return IO.NodeOutput(img, m)


class CNImgShadow(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNImgShadow",
            display_name="Drop Shadow (image)",
            category=CAT,
            description="Add a drop shadow under a layer (image + coverage mask).",
            inputs=[IO.Image.Input("image"), IO.Mask.Input("mask")] + shadow_inputs(),
            outputs=[IO.Image.Output(display_name="image"), IO.Mask.Output(display_name="mask")],
        )

    @classmethod
    def execute(cls, image, mask, dx, dy, blur, shadow_color, opacity) -> IO.NodeOutput:
        rgba = render.comfy_to_rgba(image, mask)
        h, w = rgba.shape[:2]
        surf = render.surface(w, h)
        canvas = surf.getCanvas()
        canvas.clear(skia.ColorTRANSPARENT)
        canvas.drawImage(
            render.image_from_rgba(rgba), 0, 0,
            paint=render.shadow_paint(dx, dy, blur, render.parse_color(shadow_color), opacity),
        )
        img, m = render.rgba_to_comfy(render.to_rgba(surf))
        return IO.NodeOutput(img, m)


class CNImgComposite(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNImgComposite",
            display_name="Composite Layer (image)",
            category=CAT,
            description="Put a layer (image + coverage mask) over a base image of the same size.",
            inputs=[
                IO.Image.Input("base"),
                IO.Image.Input("layer"),
                IO.Mask.Input("layer_mask"),
                IO.Float.Input("opacity", default=1.0, min=0.0, max=1.0, step=0.05),
            ],
            outputs=[IO.Image.Output(display_name="image")],
        )

    @classmethod
    def execute(cls, base, layer, layer_mask, opacity) -> IO.NodeOutput:
        if base.shape[1:3] != layer.shape[1:3]:
            raise ValueError(f"base is {tuple(base.shape[1:3])} but the layer is {tuple(layer.shape[1:3])}")
        a = (layer_mask[..., None] * opacity).to(base.dtype)
        out = base[..., :3] * (1 - a) + layer[..., :3] * a
        return IO.NodeOutput(out.clamp(0, 1))


NODES = [CNImgCanvas, CNImgText, CNImgPlace, CNImgShadow, CNImgComposite]
