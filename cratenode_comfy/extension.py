"""ComfyUI V3 entry point: registers every node in the pack."""

from __future__ import annotations

import logging

from typing_extensions import override
from comfy_api.latest import ComfyExtension, IO

from . import __version__
from . import (fonts, nodes_canvas, nodes_color, nodes_data, nodes_effects, nodes_layout, nodes_motion, nodes_output,
               nodes_print, nodes_shapes, nodes_smart, nodes_type)


class CrateNodeComfy(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[IO.ComfyNode]]:
        reg = fonts.registry()
        logging.info("CrateNode-Comfy %s: %d font faces, %d families; config %s",
                     __version__, len(reg.faces), len(reg.families()), reg.config.source)
        for p in reg.problems:
            logging.warning("CrateNode-Comfy fonts: %s", p)
        try:
            from . import nodes_live

            nodes_live.add_routes()  # live previews on the nodes (web/live_preview.js)
        except Exception as e:  # previews are a convenience; never block loading the nodes
            logging.warning("CrateNode-Comfy: live previews unavailable: %s", e)
        from . import rerun

        rerun.register()  # new palettes / looks on server-queued runs (CrateUtils-Comfy triggers)
        return (nodes_canvas.NODES + nodes_type.NODES + nodes_shapes.NODES + nodes_layout.NODES
                + nodes_effects.NODES + nodes_output.NODES + nodes_data.NODES
                + nodes_color.NODES + nodes_motion.NODES + nodes_smart.NODES + nodes_print.NODES)


async def comfy_entrypoint() -> CrateNodeComfy:
    return CrateNodeComfy()
