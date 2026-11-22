"""Layout: Stack, Place, Grid and Layers. Parts are scenes (e.g. Text Box or Shape
with no scene input); they are measured by their content, so nothing needs
pixel arithmetic."""

from __future__ import annotations

from comfy_api.latest import IO

from . import layout as lay
from . import scene as sc
from .nodes_common import ROOT, SceneT

CAT = f"{ROOT}/Layout"
N_STACK, N_GRID, N_LAYERS = 6, 9, 6


def _area_inputs(default_area="safe area"):
    return [
        IO.Combo.Input("area", options=lay.AREAS, default=default_area,
                       tooltip="Where to place: the safe area, the whole canvas, or the custom box below"),
        IO.Float.Input("x", default=0.0, min=-20000, max=20000, advanced=True),
        IO.Float.Input("y", default=0.0, min=-20000, max=20000, advanced=True),
        IO.Float.Input("box_width", default=0.0, min=0.0, max=40000, advanced=True, tooltip="0 = to the canvas edge"),
        IO.Float.Input("box_height", default=0.0, min=0.0, max=40000, advanced=True, tooltip="0 = to the canvas edge"),
    ]


def _base(scene, parts):
    """The scene to add to, or a transparent canvas the size of the first part."""
    if scene is not None:
        return scene
    first = next((p for p in parts if p is not None), None)
    return sc.Scene(first.width, first.height, margin=first.margin) if first else sc.Scene(1920, 1080)


def _box(base, area, x, y, box_width, box_height):
    return lay.area_box(base, area, x, y, box_width, box_height)


class CNStack(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNStack", display_name="Stack", category=CAT,
            description="Lay parts out in a column or row with a gap, then place the group in an area. "
                        "A part that grows (a wrapped title) pushes the ones after it.",
            inputs=[SceneT.Input("scene", optional=True, tooltip="Add the stack to this scene")]
                   + [SceneT.Input(f"part_{i}", optional=True) for i in range(1, N_STACK + 1)]
                   + [
                       IO.Combo.Input("direction", options=lay.DIRECTIONS, default="vertical"),
                       IO.Float.Input("gap", default=24.0, min=-2000, max=2000),
                       IO.Combo.Input("align", options=lay.H_POS, default="center"),
                       IO.Combo.Input("valign", options=lay.V_POS, default="middle"),
                   ] + _area_inputs(),
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, direction, gap, align, valign, area, x, y, box_width, box_height, scene=None, **parts):
        ps = [parts.get(f"part_{i}") for i in range(1, N_STACK + 1)]
        base = _base(scene, ps)
        item = lay.stack_item([p for p in ps if p is not None], _box(base, area, x, y, box_width, box_height),
                              direction, gap, align, valign)
        return IO.NodeOutput(base.add(item) if item.parts else base)


class CNPlace(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNPlace", display_name="Place", category=CAT,
            description="Move a part into an area at an alignment (e.g. a logo bottom-right of the safe area).",
            inputs=[SceneT.Input("scene", optional=True), SceneT.Input("part"),
                    IO.Combo.Input("align", options=lay.H_POS, default="right"),
                    IO.Combo.Input("valign", options=lay.V_POS, default="bottom")] + _area_inputs(),
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, part, align, valign, area, x, y, box_width, box_height, scene=None):
        base = _base(scene, [part])
        item = lay.stack_item([part], _box(base, area, x, y, box_width, box_height), "vertical", 0.0, align, valign)
        return IO.NodeOutput(base.add(item) if item.parts else base)


class CNGrid(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNGrid", display_name="Grid", category=CAT,
            description="Parts in equal cells, left to right then top to bottom.",
            inputs=[SceneT.Input("scene", optional=True)]
                   + [SceneT.Input(f"part_{i}", optional=True) for i in range(1, N_GRID + 1)]
                   + [
                       IO.Int.Input("columns", default=3, min=1, max=12),
                       IO.Float.Input("gap_x", default=24.0, min=0.0, max=2000),
                       IO.Float.Input("gap_y", default=24.0, min=0.0, max=2000),
                       IO.Combo.Input("align", options=lay.H_POS, default="center"),
                       IO.Combo.Input("valign", options=lay.V_POS, default="middle"),
                   ] + _area_inputs() + [
                       # Last on purpose: saved workflows store widget values by position.
                       IO.Combo.Input("direction", options=lay.DIRECTIONS, default="vertical", optional=True,
                                      tooltip="vertical: parts fill each row left to right and the grid grows "
                                              "down (columns = parts per row). horizontal: parts fill each "
                                              "column top to bottom and the grid grows to the right (the "
                                              "count is parts per column, shown as 'rows')."),
                   ],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, columns, gap_x, gap_y, align, valign, area, x, y, box_width, box_height, scene=None,
                direction="vertical", **parts):
        ps = [parts.get(f"part_{i}") for i in range(1, N_GRID + 1)]
        base = _base(scene, ps)
        item = lay.grid_item([p for p in ps if p is not None], _box(base, area, x, y, box_width, box_height),
                             columns, gap_x, gap_y, align, valign, direction)
        return IO.NodeOutput(base.add(item) if item.parts else base)


class CNLayers(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNLayers", display_name="Layers", category=CAT,
            description="Put scenes on top of each other where they are (layer_1 at the bottom).",
            inputs=[SceneT.Input("scene", optional=True, tooltip="The bottom layer and the canvas")]
                   + [SceneT.Input(f"layer_{i}", optional=True) for i in range(1, N_LAYERS + 1)],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene=None, **layers):
        ls = [layers.get(f"layer_{i}") for i in range(1, N_LAYERS + 1)]
        base = _base(scene, ls)
        for layer in ls:
            if layer is not None and layer.items:
                base = base.add(sc.GroupItem(items=layer.items))
        return IO.NodeOutput(base)


NODES = [CNStack, CNPlace, CNGrid, CNLayers]
