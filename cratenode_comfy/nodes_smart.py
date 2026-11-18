"""Smart helpers: place a part where the picture is quiet, check text readability, add
just enough scrim, and write copy with a local Ollama model."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from comfy_api.latest import IO, UI

from . import color as col
from . import copywriter, devices, smart
from . import layout as lay
from . import scene as sc
from .fonts import registry
from .nodes_common import ROOT, SceneT

CAT = f"{ROOT}/Smart"
TEXT_COLOR = ["keep", "best contrast"]
INKS = [("white", (1.0, 1.0, 1.0, 1.0)), ("near black", (0.07, 0.07, 0.09, 1.0))]


def _img(arr):
    import torch

    return torch.from_numpy(np.ascontiguousarray(arr, np.float32))[None]


def _ink(mean) -> tuple[str, tuple]:
    n, c, _ = col.best_contrast(mean, INKS)
    return n, c


class CNQuietArea(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNQuietArea", display_name="Find Quiet Area", category=CAT,
            description="Where in an image a box of this size sits on the calmest pixels (fewest edges and "
                        "texture), e.g. for a title over an AI background. Outputs the box, a readable text colour "
                        "for that spot, and a heat map (calm = blue, busy = yellow).",
            inputs=[IO.Image.Input("image"),
                    IO.Float.Input("box_width", default=900.0, min=1.0, max=40000.0),
                    IO.Float.Input("box_height", default=300.0, min=1.0, max=40000.0),
                    IO.Combo.Input("candidates", options=smart.CANDIDATES, default="anywhere",
                                   tooltip="9 positions: only corners, edge centres and the middle"),
                    IO.Float.Input("margin", default=5.0, min=0.0, max=45.0, step=0.5,
                                   tooltip="Keep this % of the short side clear at the edges"),
                    IO.Combo.Input("device", options=devices.MODES, default="cpu")],
            outputs=[IO.Float.Output(display_name="x"), IO.Float.Output(display_name="y"),
                     IO.Float.Output(display_name="width"), IO.Float.Output(display_name="height"),
                     IO.String.Output(display_name="text_color"), IO.Image.Output(display_name="heatmap"),
                     IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, image, box_width, box_height, candidates, margin, device):
        rgb = image[0, :, :, :3].cpu().numpy()
        h, w = rgb.shape[:2]
        m = min(w, h) * margin / 100.0
        dev, note = devices.pick(device, registry().config)
        spot, bm, f = smart.quiet_box(rgb, box_width, box_height, (m, m, w - 2 * m, h - 2 * m), candidates, dev)
        name, ink = _ink(spot.mean_color)
        report = (f"box at ({spot.x:.0f}, {spot.y:.0f}) {spot.w:.0f}x{spot.h:.0f}, busyness {spot.score:.2f} "
                  f"(0 calm, 1 busy); {name} text reads best there; ran on {note}")
        return IO.NodeOutput(spot.x, spot.y, spot.w, spot.h, col.to_hex(ink), _img(smart.heatmap(bm, spot, f)),
                             report)


class CNAutoPlace(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNAutoPlace", display_name="Auto Place", category=CAT,
            description="Place a part (e.g. a title from Text Box) where the design so far is calmest, inside the "
                        "safe area. Optionally switch its text to white or near-black, whichever reads best there.",
            inputs=[SceneT.Input("scene"), SceneT.Input("part"),
                    IO.Image.Input("background", optional=True,
                                   tooltip="Judge this image instead of the design so far (same proportions)"),
                    IO.Combo.Input("area", options=lay.AREAS[:2], default="safe area"),
                    IO.Combo.Input("candidates", options=smart.CANDIDATES, default="anywhere"),
                    IO.Float.Input("padding", default=24.0, min=0.0, max=2000.0,
                                   tooltip="Calm space wanted around the part"),
                    IO.Combo.Input("text_color", options=TEXT_COLOR, default="keep"),
                    IO.Combo.Input("device", options=devices.MODES, default="cpu")],
            outputs=[SceneT.Output(display_name="scene"), IO.Image.Output(display_name="heatmap"),
                     IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, scene, part, area, candidates, padding, text_color, device, background=None):
        b = sc.content_bounds(part.items)
        ink_b = smart.ink_bounds(part.items)  # the letters, not their (often wider) text boxes
        if b is None or ink_b is None:
            raise ValueError("the part is empty")
        pw, ph = b[2] - b[0], b[3] - b[1]
        iw, ih = ink_b[2] - ink_b[0], ink_b[3] - ink_b[1]
        s = min(1.0, 1024 / max(scene.width, scene.height))
        if background is not None:
            import torch

            bg = background[:1].permute(0, 3, 1, 2)[:, :3]
            bg = torch.nn.functional.interpolate(bg, size=(round(scene.height * s), round(scene.width * s)),
                                                 mode="area")
            rgb = bg[0].permute(1, 2, 0).cpu().numpy()
        else:
            r = sc.render(scene, s)
            rgb = r[:, :, :3] * r[:, :, 3:4]
        ax, ay, aw, ah = lay.area_box(scene, area, 0, 0, 0, 0)
        dev, note = devices.pick(device, registry().config)
        spot, bm, f = smart.quiet_box(rgb, (iw + 2 * padding) * s, (ih + 2 * padding) * s,
                                      (ax * s, ay * s, aw * s, ah * s), candidates, dev)
        # Put the part's layout box where its ink lands in the chosen spot.
        box = (spot.x / s + padding - (ink_b[0] - b[0]), spot.y / s + padding - (ink_b[1] - b[1]), pw, ph)
        items = part.items
        name, ink = _ink(spot.mean_color)
        if text_color == "best contrast":
            items = smart._map_items(items, lambda it, k: replace(it, spec=replace(it.spec, color=ink))
                                     if k is not None else it, [0])
        out = scene.add(lay.stack_item([replace(part, items=items)], box, "vertical", 0.0, "center", "middle"))
        report = (f"placed at ({box[0]:.0f}, {box[1]:.0f}), busyness {spot.score:.2f}; {name} text reads best "
                  f"there{' (applied)' if text_color != 'keep' else ''}; ran on {note}")
        return IO.NodeOutput(out, _img(smart.heatmap(bm, replace(spot), f)), report)


class CNReadability(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNReadability", display_name="Readability Check", category=CAT,
            description="WCAG contrast of every text against what is actually behind its letters (the worst 10% "
                        "of those pixels). Large text needs 3:1, body text 4.5:1 (AA). The overlay frames each "
                        "text green (pass) or red (fail).",
            is_output_node=True,
            inputs=[SceneT.Input("scene"), IO.Combo.Input("level", options=list(smart.LEVELS), default="AA")],
            outputs=[IO.String.Output(display_name="report"), IO.Float.Output(display_name="worst"),
                     IO.Boolean.Output(display_name="all_pass"), IO.Image.Output(display_name="overlay")],
        )

    @classmethod
    def execute(cls, scene, level):
        checks = smart.readability(scene, level)
        if not checks:
            return IO.NodeOutput("no text", 0.0, True, _img(sc.render(scene, 0.5)[:, :, :3]),
                                 ui=UI.PreviewText("no text"))
        report = "\n".join(c.line() for c in checks)
        ok = all(c.ok for c in checks)
        ov = smart.overlay(scene, checks, 0.5)
        return IO.NodeOutput(report, round(min(c.worst for c in checks), 2), ok, _img(ov[:, :, :3]),
                             ui=UI.PreviewText(report))


class CNSmartScrim(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSmartScrim", display_name="Smart Scrim", category=CAT,
            description="Put a darkening (or lightening) layer under the last item, only as strong as needed for "
                        "its text to reach the target contrast: a gradient band from the nearer edge, a box, or a "
                        "soft glow. Nothing is added when the text already reads.",
            inputs=[SceneT.Input("scene"),
                    IO.Combo.Input("style", options=smart.SCRIM_STYLES, default="gradient band"),
                    IO.String.Input("color", default="auto", tooltip="auto: black under light text, white under dark"),
                    IO.Float.Input("target_contrast", default=4.5, min=1.0, max=21.0, step=0.1),
                    IO.Float.Input("max_opacity", default=0.85, min=0.05, max=1.0, step=0.05),
                    IO.Float.Input("padding", default=40.0, min=0.0, max=2000.0),
                    IO.Float.Input("corner_radius", default=16.0, min=0.0, max=2000.0, tooltip="Box style")],
            outputs=[SceneT.Output(display_name="scene"), IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, scene, style, color, target_contrast, max_opacity, padding, corner_radius):
        out, report = smart.scrim_for(scene, -1, style, color, target_contrast, max_opacity, padding, corner_radius)
        return IO.NodeOutput(out, report)


class CNCopyWriter(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNCopyWriter", display_name="Copy Writer (Ollama)", category=CAT,
            description="Headlines, shorter text, subtitles, taglines or calls to action from a local Ollama "
                        "model. 'variants' is a list: wired into a Text Box, it makes one design per variant.",
            inputs=[IO.Combo.Input("task", options=list(copywriter.TASKS), default="headlines"),
                    IO.String.Input("text", multiline=True, default="", tooltip="What the copy is about"),
                    IO.String.Input("instructions", multiline=True, default="",
                                    tooltip="Tone, audience, words to use or avoid"),
                    IO.String.Input("model", default="", tooltip="An installed Ollama model, as 'ollama list' shows"),
                    IO.String.Input("host", default="http://127.0.0.1:11434"),
                    IO.Int.Input("count", default=3, min=1, max=20),
                    IO.Int.Input("max_chars", default=60, min=0, max=2000, tooltip="0 = no limit"),
                    IO.Float.Input("temperature", default=0.7, min=0.0, max=2.0, step=0.05),
                    IO.Int.Input("seed", default=0, min=0, max=2**31 - 1, control_after_generate=True)],
            outputs=[IO.String.Output(display_name="text"),
                     IO.String.Output(display_name="variants", is_output_list=True),
                     IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, task, text, instructions, model, host, count, max_chars, temperature, seed):
        variants, report = copywriter.write(task, text, model, host, instructions, count, max_chars, temperature,
                                            seed, registry().config.allowed_hosts)
        return IO.NodeOutput(variants[0], variants, report)


NODES = [CNQuietArea, CNAutoPlace, CNReadability, CNSmartScrim, CNCopyWriter]
