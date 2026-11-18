"""Output: render a scene to IMAGE/MASK, or save it as a vector PDF."""

from __future__ import annotations

import os

from comfy_api.latest import IO, UI

from . import render
from . import scene as sc
from .nodes_common import ROOT, SceneT

CAT = f"{ROOT}/Output"


class CNRender(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNRender", display_name="Render Scene", category=CAT,
            description="Turn a design into an IMAGE and its alpha MASK (1 = opaque) for any ComfyUI node. "
                        "scale 2 renders at twice the canvas size, still sharp.",
            inputs=[SceneT.Input("scene"), IO.Float.Input("scale", default=1.0, min=0.05, max=8.0, step=0.05)],
            outputs=[IO.Image.Output(display_name="image"), IO.Mask.Output(display_name="alpha")],
        )

    @classmethod
    def execute(cls, scene, scale):
        img, alpha = render.rgba_to_comfy(sc.render(scene, scale))
        return IO.NodeOutput(img, alpha)


class CNSavePDF(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSavePDF", display_name="Save PDF", category=CAT,
            description="Vector RGB PDF (text stays text, fonts embedded) in the output folder.",
            is_output_node=True,
            inputs=[SceneT.Input("scene"), IO.String.Input("filename_prefix", default="design"),
                    IO.Float.Input("dpi", default=300.0, min=10.0, max=2400.0, tooltip="Canvas pixels per inch")],
            outputs=[IO.String.Output(display_name="path")],
        )

    @classmethod
    def execute(cls, scene, filename_prefix, dpi):
        import folder_paths

        out_dir, base, counter, _, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), scene.width, scene.height)
        path = os.path.join(out_dir, f"{base}_{counter:05}_.pdf")
        sc.to_pdf(scene, path, dpi)
        return IO.NodeOutput(path, ui=UI.PreviewText(f"saved {os.path.basename(path)}"))


NODES = [CNRender, CNSavePDF]
