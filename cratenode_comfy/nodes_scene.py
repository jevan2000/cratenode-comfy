"""Spike pipeline A: a vector SCENE flows between nodes and is rendered at the end."""

from __future__ import annotations

import os
from dataclasses import replace

from comfy_api.latest import IO, UI

from . import render
from . import scene as scene_mod
from .nodes_common import MASK_MEANINGS, mask_to_alpha, shadow_inputs, text_inputs, text_spec

Scene = IO.Custom("CN_SCENE")
CAT = "CrateNode-Comfy/spike: scene"


class CNSceneCanvas(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSceneCanvas",
            display_name="Canvas (scene)",
            category=CAT,
            description="Start a vector design: canvas size and background colour.",
            inputs=[
                IO.Int.Input("width", default=1920, min=1, max=16384),
                IO.Int.Input("height", default=1080, min=1, max=16384),
                IO.String.Input("background", default="#000000ff", tooltip="#rrggbb or #rrggbbaa (00 alpha = transparent)"),
            ],
            outputs=[Scene.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, width, height, background) -> IO.NodeOutput:
        return IO.NodeOutput(scene_mod.Scene(width, height, render.parse_color(background)))


class CNSceneImage(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSceneImage",
            display_name="Add Image (scene)",
            category=CAT,
            description="Place an image in a box: fit, fill (crop) or stretch. Box size 0 = the whole canvas.",
            inputs=[
                Scene.Input("scene"),
                IO.Image.Input("image"),
                IO.Mask.Input("mask", optional=True),
                IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[0]),
                IO.Combo.Input("mode", options=render.FIT_MODES, default="fill"),
                IO.Float.Input("x", default=0.0, min=-10000, max=10000),
                IO.Float.Input("y", default=0.0, min=-10000, max=10000),
                IO.Float.Input("box_width", default=0.0, min=0.0, max=20000),
                IO.Float.Input("box_height", default=0.0, min=0.0, max=20000),
                IO.Boolean.Input("below_previous", default=False),
                IO.Float.Input("gap", default=24.0, min=-1000, max=1000),
            ],
            outputs=[Scene.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene, image, mode, x, y, box_width, box_height, below_previous, gap,
                mask=None, mask_meaning=MASK_MEANINGS[0]) -> IO.NodeOutput:
        rgba = render.comfy_to_rgba(image, mask_to_alpha(mask, mask_meaning))
        w = box_width or (scene.width - x)
        h = box_height or (scene.height - y)
        item = scene_mod.ImageItem(rgba, x, y, w, h, mode, flow=scene_mod.Flow(below_previous, gap))
        return IO.NodeOutput(scene.add(item))



class CNSceneText(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSceneText",
            display_name="Add Text Box (scene)",
            category=CAT,
            description="Add a text box. With below_previous, its top sits under the previous item, so a "
                        "title that wraps pushes it down.",
            inputs=[Scene.Input("scene")] + text_inputs() + [
                IO.Boolean.Input("below_previous", default=False),
                IO.Float.Input("gap", default=24.0, min=-1000, max=1000),
            ],
            outputs=[Scene.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene, below_previous, gap, **kw) -> IO.NodeOutput:
        item = scene_mod.TextItem(text_spec(kw), flow=scene_mod.Flow(below_previous, gap))
        scene_mod.resolve(scene.add(item))  # fail here (missing font) rather than at render
        return IO.NodeOutput(scene.add(item))


class CNSceneShadow(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSceneShadow",
            display_name="Drop Shadow on Last Item (scene)",
            category=CAT,
            inputs=[Scene.Input("scene")] + shadow_inputs(),
            outputs=[Scene.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene, dx, dy, blur, shadow_color, opacity) -> IO.NodeOutput:
        sh = scene_mod.Shadow(dx, dy, blur, render.parse_color(shadow_color), opacity)
        return IO.NodeOutput(scene.map_last(lambda it: replace(it, shadow=sh)))


class CNSceneRender(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSceneRender",
            display_name="Render Scene",
            category=CAT,
            description="Rasterise the design. scale 2 renders at twice the canvas size, still sharp.",
            inputs=[Scene.Input("scene"), IO.Float.Input("scale", default=1.0, min=0.05, max=8.0, step=0.05)],
            outputs=[IO.Image.Output(display_name="image"), IO.Mask.Output(display_name="alpha")],
        )

    @classmethod
    def execute(cls, scene, scale) -> IO.NodeOutput:
        img, alpha = render.rgba_to_comfy(scene_mod.render(scene, scale))
        return IO.NodeOutput(img, alpha)


class CNSceneSavePDF(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSceneSavePDF",
            display_name="Save Scene as PDF",
            category=CAT,
            description="Vector RGB PDF (text stays text) in the output folder.",
            is_output_node=True,
            inputs=[
                Scene.Input("scene"),
                IO.String.Input("filename_prefix", default="design"),
                IO.Float.Input("dpi", default=300.0, min=10.0, max=2400.0, tooltip="Canvas pixels per inch"),
            ],
            outputs=[IO.String.Output(display_name="path")],
        )

    @classmethod
    def execute(cls, scene, filename_prefix, dpi) -> IO.NodeOutput:
        import folder_paths

        out_dir, base, counter, sub, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), scene.width, scene.height
        )
        path = os.path.join(out_dir, f"{base}_{counter:05}_.pdf")
        scene_mod.to_pdf(scene, path, dpi)
        return IO.NodeOutput(path, ui=UI.PreviewText(f"saved {os.path.basename(path)}"))


NODES = [CNSceneCanvas, CNSceneImage, CNSceneText, CNSceneShadow, CNSceneRender, CNSceneSavePDF]
