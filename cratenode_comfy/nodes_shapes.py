"""Shapes: rectangle (rounded), ellipse, line, polygon, star."""

from __future__ import annotations

from comfy_api.latest import IO

from . import scene as sc
from . import stroke as strokemod
from .nodes_common import ROOT, FillT, SceneT, flow, flow_inputs, new_part, slot
from .nodes_common import color as to_color


class CNShape(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNShape", display_name="Shape", category=f"{ROOT}/Shapes",
            description="A rectangle, ellipse, line, polygon or star in a box. A line runs from the box's "
                        "top-left to its bottom-right corner (height 0 = horizontal). For an outline-only "
                        "shape, set a stroke and fill_opacity 0.",
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
            ] + flow_inputs() + [
                # Last on purpose: saved workflows store widget values by position, so a new
                # widget must come after every existing one or old values shift into it.
                IO.Float.Input("fill_opacity", default=1.0, min=0.0, max=1.0, step=0.01, optional=True,
                               tooltip="Opacity of the fill (colour or gradient), not the outline. "
                                       "0 = no fill: with a stroke, an outline-only shape"),
                IO.String.Input("stroke_style", default="", optional=True,
                                tooltip="How the stroke is drawn; click the field for the stroke editor. Text "
                                        "form: align=center|inside|outside; dash=3,2 (on,off in stroke widths); "
                                        "offset=0; cap=round|butt|square; join=round|miter|bevel; "
                                        "double=gap,width[,inside|outside] (pixels); behind=1 (under the fill). "
                                        "Empty = a plain centred stroke."),
            ],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, shape, x, y, width, height, color, stroke_color, stroke_width, corner_radius, sides,
                inner_ratio, rotation, scene=None, fill=None, fill_opacity=1.0, stroke_style="", **kw):
        scene = new_part(scene)
        base = fill if fill is not None else (to_color(color) if color.strip() else None)
        stroke = to_color(stroke_color) if stroke_color.strip() else None
        if shape == "line" and stroke is None:  # a line is drawn in its colour, whatever the fill opacity
            stroke = base if isinstance(base, tuple) else (1.0, 1.0, 1.0, 1.0)
            stroke_width = stroke_width or 4.0
        f = sc.fade_fill(base, fill_opacity)
        item = sc.ShapeItem(shape, x, y, width, height, f, stroke, stroke_width, corner_radius, sides,
                            inner_ratio, rotation, flow=flow(kw), name=slot(kw),
                            stroke_style=strokemod.parse(stroke_style))
        return IO.NodeOutput(scene.add(item))


NODES = [CNShape]
