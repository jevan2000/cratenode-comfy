"""Shapes: rectangle (rounded), ellipse, line, polygon, star."""

from __future__ import annotations

from comfy_api.latest import IO

from . import scene as sc
from .nodes_common import ROOT, FillT, SceneT, flow, flow_inputs, new_part
from .nodes_common import color as to_color


class CNShape(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNShape", display_name="Shape", category=f"{ROOT}/Shapes",
            description="A rectangle, ellipse, line, polygon or star in a box. A line runs from the box's "
                        "top-left to its bottom-right corner (height 0 = horizontal).",
            inputs=[
                SceneT.Input("scene", optional=True),
                IO.Combo.Input("shape", options=sc.SHAPES, default="rectangle"),
                IO.Float.Input("x", default=96.0, min=-20000, max=20000),
                IO.Float.Input("y", default=96.0, min=-20000, max=20000),
                IO.Float.Input("width", default=400.0, min=0.0, max=40000),
                IO.Float.Input("height", default=200.0, min=0.0, max=40000),
                IO.String.Input("color", default="#ffffff", tooltip="Fill colour; empty = no fill"),
                FillT.Input("fill", optional=True, tooltip="Gradient fill; replaces the colour"),
                IO.String.Input("stroke_color", default="", tooltip="Outline colour; empty = none"),
                IO.Float.Input("stroke_width", default=0.0, min=0.0, max=1000.0),
                IO.Float.Input("corner_radius", default=0.0, min=0.0, max=10000.0, tooltip="Rectangles"),
                IO.Int.Input("sides", default=5, min=3, max=64, tooltip="Polygon sides / star points"),
                IO.Float.Input("inner_ratio", default=0.5, min=0.05, max=1.0, step=0.01, tooltip="Stars"),
                IO.Float.Input("rotation", default=0.0, min=-360.0, max=360.0, step=1.0),
            ] + flow_inputs(),
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, shape, x, y, width, height, color, stroke_color, stroke_width, corner_radius, sides,
                inner_ratio, rotation, scene=None, fill=None, **kw):
        scene = new_part(scene)
        f = fill if fill is not None else (to_color(color) if color.strip() else None)
        stroke = to_color(stroke_color) if stroke_color.strip() else None
        if shape == "line" and stroke is None:
            stroke = f if isinstance(f, tuple) else (1.0, 1.0, 1.0, 1.0)
            stroke_width = stroke_width or 4.0
        item = sc.ShapeItem(shape, x, y, width, height, f, stroke, stroke_width, corner_radius, sides,
                            inner_ratio, rotation, flow=flow(kw))
        return IO.NodeOutput(scene.add(item))


NODES = [CNShape]
