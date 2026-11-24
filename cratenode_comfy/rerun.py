"""New palettes and looks for runs queued by the server, not the browser.

In the browser, Palette Generator (new_each_run) and Fluid Gradient (randomize) get new
values just before each queued prompt (web/before_run.js). Runs that other packs queue on
the server (CrateUtils-Comfy's triggers) never pass through the browser, so they would
repeat the saved values. ``refresh_prompt`` does the same work on an API-format prompt,
and ``register`` offers it to those packs through a small shared registry (a module in
``sys.modules``), so neither pack has to import the other or load first.
"""

from __future__ import annotations

import random
import sys
import types

REGISTRY = "crate_before_queue"  # sys.modules name; .hooks is a list of fn(prompt, rng) -> int

PALETTE = "CNPaletteGenerator"
FLUID = "CNFluidGradient"
COLORS = tuple(f"color_{i}" for i in range(1, 6))


def _linked(v) -> bool:
    """An API prompt input fed by another node is [node_id, output_index]."""
    return isinstance(v, list)


def _new_palette(ins: dict, rng: random.Random) -> bool:
    if not ins.get("new_each_run", True) or ins.get("locked", False):
        return False
    from . import palettegen as pg

    opts = [ins.get(k, "random" if k == "harmony" else "any") for k in ("harmony", "family", "style")]
    if any(_linked(o) for o in opts):
        return False  # the settings come from another node; can't know them here
    colors = pg.to_hex_list(pg.generate(rng.randrange(2**31), *(str(o) for o in opts)))
    for name, hex_ in zip(COLORS, colors):
        if not _linked(ins.get(name)):
            ins[name] = hex_
    return True


def _new_look(ins: dict, rng: random.Random) -> bool:
    if not ins.get("randomize", False) or _linked(ins.get("randomize")):
        return False
    from . import fluid

    keep_colours = _linked(ins.get("palette"))
    for name, value in fluid.random_look(rng.randrange(2**31)).items():
        if _linked(ins.get(name)) or (keep_colours and name.startswith("color_")):
            continue
        ins[name] = value
    if "preset" in ins and not _linked(ins["preset"]):
        ins["preset"] = fluid.CUSTOM  # the look is no longer a preset's
    return True


def refresh_prompt(prompt: dict, rng: random.Random | None = None) -> int:
    """New colours / looks in place on an API-format prompt; returns how many nodes changed.

    Follows each node's own settings like the browser does: Palette Generator only with
    new_each_run on and locked off, Fluid Gradient only with randomize on; inputs fed by
    a link are left alone, and so are Fluid Gradient's colours when a palette is linked.
    """
    rng = rng or random.SystemRandom()
    n = 0
    for node in (prompt or {}).values():
        if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
            continue
        kind = node.get("class_type")
        if kind == PALETTE:
            n += _new_palette(node["inputs"], rng)
        elif kind == FLUID:
            n += _new_look(node["inputs"], rng)
    return n


def register() -> None:
    """Offer refresh_prompt to packs that queue prompts on the server (once)."""
    reg = sys.modules.get(REGISTRY)
    if reg is None:
        reg = sys.modules.setdefault(REGISTRY, types.ModuleType(REGISTRY))
    hooks = reg.__dict__.setdefault("hooks", [])
    if not any(getattr(h, "__qualname__", "") == refresh_prompt.__qualname__
               and getattr(h, "__module__", "").endswith("rerun") for h in hooks):
        hooks.append(refresh_prompt)
