"""ComfyUI V3 entry point: registers every node in the pack."""

from __future__ import annotations

import logging

from typing_extensions import override
from comfy_api.latest import ComfyExtension, IO

from . import fonts, nodes_canvas, nodes_data, nodes_effects, nodes_layout, nodes_output, nodes_shapes, nodes_type


class CrateNodeComfy(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[IO.ComfyNode]]:
        reg = fonts.registry()
        logging.info("CrateNode-Comfy: %d font faces, %d families; config %s",
                     len(reg.faces), len(reg.families()), reg.config.source)
        for p in reg.problems:
            logging.warning("CrateNode-Comfy fonts: %s", p)
        return (nodes_canvas.NODES + nodes_type.NODES + nodes_shapes.NODES + nodes_layout.NODES
                + nodes_effects.NODES + nodes_output.NODES + nodes_data.NODES)


async def comfy_entrypoint() -> CrateNodeComfy:
    return CrateNodeComfy()
