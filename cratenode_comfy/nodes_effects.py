"""Effects: drop shadow, outer glow, outline, blur, opacity and blend, clipping."""

from __future__ import annotations

from comfy_api.latest import IO

from . import scene as sc
from .nodes_common import ROOT, SceneT, apply_to_target, color, target_input

CAT = f"{ROOT}/Effects"


def _effect_node(node_id, name, description, extra_inputs, make):
    class Node(IO.ComfyNode):
        @classmethod
        def define_schema(cls):
            return IO.Schema(node_id=node_id, display_name=name, category=CAT, description=description,
                             inputs=[SceneT.Input("scene"), target_input()] + extra_inputs(),
                             outputs=[SceneT.Output(display_name="scene")])

        @classmethod
        def execute(cls, scene, target, **kw):
            eff = make(kw)
            return IO.NodeOutput(apply_to_target(scene, target, lambda it: sc.add_effect(it, eff)))

    Node.__name__ = node_id
    return Node


def _color_inputs(default="#000000", opacity=0.6):
    return [IO.String.Input("color", default=default),
            IO.Float.Input("opacity", default=opacity, min=0.0, max=1.0, step=0.05)]


CNDropShadow = _effect_node(
    "CNDropShadow", "Drop Shadow", "A soft shadow under the item (or the whole scene).",
    lambda: [IO.Float.Input("dx", default=0.0, min=-2000, max=2000), IO.Float.Input("dy", default=8.0, min=-2000, max=2000),
             IO.Float.Input("blur", default=24.0, min=0.0, max=2000)] + _color_inputs(),
    lambda kw: sc.Shadow(kw["dx"], kw["dy"], kw["blur"], color(kw["color"]), kw["opacity"]),
)

CNOuterGlow = _effect_node(
    "CNOuterGlow", "Outer Glow", "A soft glow around the item; spread grows it before blurring.",
    lambda: [IO.Float.Input("blur", default=24.0, min=0.0, max=2000), IO.Float.Input("spread", default=0.0, min=0.0, max=500)]
            + _color_inputs("#ffffff", 0.8),
    lambda kw: sc.Glow(kw["blur"], kw["spread"], color(kw["color"]), kw["opacity"]),
)

CNOutline = _effect_node(
    "CNOutline", "Outline", "A solid outline around the item's shape (text, cut-out images, shapes).",
    lambda: [IO.Float.Input("width", default=6.0, min=0.0, max=500)] + _color_inputs("#000000", 1.0),
    lambda kw: sc.Outline(kw["width"], color(kw["color"]), kw["opacity"]),
)

CNBlur = _effect_node(
    "CNBlur", "Blur", "Blur the item (or the whole scene so far, e.g. a background).",
    lambda: [IO.Float.Input("radius", default=12.0, min=0.0, max=2000)],
    lambda kw: sc.Blur(kw["radius"]),
)


class CNOpacityBlend(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNOpacityBlend", display_name="Opacity & Blend", category=CAT,
            description="Opacity and blend mode (multiply, screen, overlay, ...) of the item or the whole scene.",
            inputs=[SceneT.Input("scene"), target_input(),
                    IO.Float.Input("opacity", default=1.0, min=0.0, max=1.0, step=0.05),
                    IO.Combo.Input("blend", options=list(sc.BLEND_MODES), default="normal")],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene, target, opacity, blend):
        return IO.NodeOutput(apply_to_target(scene, target, lambda it: sc.with_style(it, opacity=opacity, blend=blend)))


class CNClipToPrevious(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNClipToPrevious", display_name="Clip to Previous", category=CAT,
            description="Show the last item only where the item before it is (a clipping mask): e.g. a photo "
                        "inside text, or a texture inside a shape.",
            inputs=[SceneT.Input("scene"), IO.Boolean.Input("clip", default=True)],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene, clip):
        if len(scene.items) < 2:
            raise ValueError("clipping needs two items: the shape to clip to, then the item to clip")
        return IO.NodeOutput(scene.map_last(lambda it: sc.with_style(it, clip_to_previous=clip)))


NODES = [CNDropShadow, CNOuterGlow, CNOutline, CNBlur, CNOpacityBlend, CNClipToPrevious]
