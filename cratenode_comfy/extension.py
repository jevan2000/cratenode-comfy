"""ComfyUI V3 entry point: registers every node in the pack."""

from __future__ import annotations

import logging

from typing_extensions import override
from comfy_api.latest import ComfyExtension, IO

from . import fonts, nodes_image, nodes_scene


class CrateNodeComfy(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[IO.ComfyNode]]:
        reg = fonts.registry()
        logging.info(
            "CrateNode-Comfy: %d font faces (%s); config %s",
            len(reg.faces), ", ".join(reg.families()[:12]), reg.config.source,
        )
        for p in reg.problems:
            logging.warning("CrateNode-Comfy fonts: %s", p)
        return nodes_scene.NODES + nodes_image.NODES


async def comfy_entrypoint() -> CrateNodeComfy:
    return CrateNodeComfy()
