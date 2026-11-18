"""Type: text boxes."""

from __future__ import annotations

from comfy_api.latest import IO

from . import scene as sc
from .nodes_common import ROOT, FillT, SceneT, flow, flow_inputs, new_part, slot, text_inputs, text_spec


class CNTextBox(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNTextBox", display_name="Text Box", category=f"{ROOT}/Type",
            description="Text in a box: wrapping, alignment, vertical anchoring, auto-fit, *bold* words. "
                        "Leave 'scene' empty to make a part for Stack, Place or Grid.",
            inputs=[SceneT.Input("scene", optional=True), FillT.Input("fill", optional=True,
                    tooltip="Gradient text; replaces the colour")] + text_inputs() + flow_inputs(),
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene=None, fill=None, **kw):
        scene = new_part(scene)
        fl, name = flow(kw), slot(kw)
        item = sc.TextItem(text_spec(kw), fill=fill if isinstance(fill, sc.Gradient) else None, flow=fl, name=name)
        out = scene.add(item)
        sc.resolve(out)  # fail here (e.g. missing font) rather than at render
        return IO.NodeOutput(out)


NODES = [CNTextBox]
