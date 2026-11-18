"""Print: CMYK PDFs with bleed and crop marks, soft proofing, and CMYK values."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from comfy_api.latest import IO, UI

from . import cmyk as cmk
from . import color as col
from . import printpdf
from . import scene as sc
from . import template as tpl
from .fonts import registry
from .nodes_common import ROOT, PaletteT, RowT, SceneT, with_warnings

CAT = f"{ROOT}/Print"
CONFIG = "(config)"
NONE = "(none: uncalibrated)"
SYSTEM_COLOR = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "spool" / "drivers" / "color"


def _profiles() -> dict[str, Path]:
    """CMYK ICC profiles in the data folder's color/ and the system colour folder."""
    cfg = registry().config
    folders = ([cfg.data_dir / "color"] if cfg.data_dir else []) + [SYSTEM_COLOR]
    out = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for p in sorted(list(folder.glob("*.ic[cm]")) + list(folder.glob("*.IC[CM]"))):
            try:
                head = p.read_bytes()[:20]
            except OSError:
                continue
            if head[16:20] == b"CMYK":  # ICC header: data colour space
                out.setdefault(p.name, p)
    return out


def profile_inputs():
    return [
        IO.Combo.Input("profile", options=[CONFIG] + sorted(_profiles()) + [NONE], default=CONFIG,
                       tooltip="The CMYK ICC profile: the one in the config (cmyk_profile), one found in the data "
                               "folder's color/ or the system colour folder, or none (uncalibrated)"),
        IO.Combo.Input("intent", options=list(cmk.INTENTS), default="relative colorimetric"),
        IO.Boolean.Input("black_point", default=True, tooltip="Black point compensation"),
        IO.Boolean.Input("pure_black", default=True, tooltip="#000000 prints as 0/0/0/100 (K only)"),
        IO.String.Input("cmyk_values", multiline=True, default="",
                        tooltip="Exact values for vector colours (text, shapes, gradients): '#1f6feb = 90 55 0 0' "
                                "or 'primary = 90 55 0 0' (percent), one per line. Images use the profile."),
        PaletteT.Input("palette", optional=True, tooltip="Lets cmyk_values use colour names"),
    ]


def converter(profile, intent, black_point, pure_black, cmyk_values, palette=None) -> cmk.CMYK:
    if profile == CONFIG:
        path = registry().config.cmyk_profile or None
    elif profile == NONE:
        path = None
    else:
        path = _profiles().get(profile)
        if path is None:
            raise ValueError(f"profile {profile!r} not found")
    return cmk.CMYK(path, intent, black_point, cmk.parse_overrides(cmyk_values, palette), pure_black)


class CNSavePrintPDF(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSavePrintPDF", display_name="Save Print PDF (CMYK)", category=CAT,
            description="A CMYK PDF for print. vector: text stays text, flat colours get exact CMYK, images go "
                        "through the profile. flatten: one CMYK image through the profile (blend modes look as on "
                        "screen; exact values don't apply). Bleed: make the canvas trim + 2 x bleed ('canvas "
                        "includes bleed', see the Canvas presets), or extend a solid background colour.",
            is_output_node=True,
            inputs=[SceneT.Input("scene"),
                    IO.String.Input("filename_prefix", default="print/design",
                                    tooltip="{column} from a data row, {date}, {time}, {index}"),
                    RowT.Input("row", optional=True),
                    IO.Float.Input("dpi", default=300.0, min=10.0, max=2400.0, tooltip="Canvas pixels per inch"),
                    IO.Combo.Input("mode", options=printpdf.MODES, default="vector"),
                    IO.Combo.Input("bleed_mode", options=printpdf.BLEED_MODES, default="canvas includes bleed"),
                    IO.Float.Input("bleed", default=0.125, min=0.0, max=2.0, step=0.0625, tooltip="Inches"),
                    IO.Boolean.Input("crop_marks", default=True),
                    IO.Boolean.Input("output_intent", default=True, tooltip="Embed the CMYK profile as the "
                                                                            "PDF's output intent"),
                    IO.Float.Input("raster_dpi", default=300.0, min=72.0, max=2400.0, tooltip="flatten mode")]
                   + profile_inputs(),
            outputs=[IO.String.Output(display_name="path"), IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, scene, filename_prefix, dpi, mode, bleed_mode, bleed, crop_marks, output_intent, raster_dpi,
                profile, intent, black_point, pure_black, cmyk_values, row=None, palette=None):
        import folder_paths

        cm = converter(profile, intent, black_point, pure_black, cmyk_values, palette)
        out_dir, base, counter, _, _ = folder_paths.get_save_image_path(
            tpl.format_name(filename_prefix, row), folder_paths.get_output_directory(), scene.width, scene.height)
        path = os.path.join(out_dir, f"{base}_{counter:05}_.pdf")
        info = printpdf.print_pdf(scene, path, cm, dpi, mode, bleed, bleed_mode, crop_marks, output_intent,
                                  raster_dpi, title=base)
        tw, th = info["trim_in"]
        conv = ", ".join(f"{v} {k}" for k, v in info["converted"].items()) or "nothing to convert"
        report = (f"{os.path.basename(path)}: trim {tw:.3f} x {th:.3f} in, bleed {info['bleed_in']:.3f} in, "
                  f"{mode}; CMYK via {info['profile']}; converted {conv}")
        if not info["calibrated"]:
            report += "\nWARNING: no CMYK profile, colours are uncalibrated. Set cmyk_profile in the config."
        report = with_warnings(report, scene.items)
        return IO.NodeOutput(path, report, ui=UI.PreviewText(report))


class CNSoftProof(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSoftProof", display_name="Soft Proof (CMYK)", category=CAT,
            description="How a design or image will look printed through the CMYK profile, and a mask of the "
                        "colours that shift more than the threshold (out of gamut).",
            inputs=[SceneT.Input("scene", optional=True), IO.Image.Input("image", optional=True),
                    IO.Float.Input("scale", default=0.5, min=0.05, max=4.0, step=0.05, tooltip="For a scene"),
                    IO.Float.Input("threshold", default=6.0, min=0.5, max=50.0, step=0.5,
                                   tooltip="Colour difference (ΔE) counted as out of gamut")] + profile_inputs(),
            outputs=[IO.Image.Output(display_name="proof"), IO.Mask.Output(display_name="out_of_gamut"),
                     IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, scale, threshold, profile, intent, black_point, pure_black, cmyk_values, scene=None,
                image=None, palette=None):
        import torch

        cm = converter(profile, intent, black_point, pure_black, cmyk_values, palette)
        if scene is not None:
            r = sc.render(scene, scale)
            rgb = r[:, :, :3] * r[:, :, 3:4] + (1 - r[:, :, 3:4])
        elif image is not None:
            rgb = image[0, :, :, :3].cpu().numpy()
        else:
            raise ValueError("connect a scene or an image")
        u8 = np.round(np.clip(rgb, 0, 1) * 255).astype(np.uint8)
        proof = cm.proof(u8)
        h, w = u8.shape[:2]
        de = np.linalg.norm(col.srgb_to_lab(u8.reshape(-1, 3) / 255.0) - col.srgb_to_lab(proof.reshape(-1, 3) / 255.0),
                            axis=1).reshape(h, w)
        out = de > threshold
        report = (f"{out.mean() * 100:.1f}% of pixels shift more than ΔE {threshold:g} (largest {de.max():.1f}); "
                  f"profile: {cm.name}")
        img = torch.from_numpy(proof.astype(np.float32) / 255.0)[None]
        return IO.NodeOutput(img, torch.from_numpy(out.astype(np.float32))[None], report)


class CNCMYKValues(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNCMYKValues", display_name="CMYK Values", category=CAT,
            description="The CMYK a colour will print with (through the profile, or your exact value).",
            is_output_node=True,
            inputs=[IO.String.Input("color", default="#1f6feb", tooltip="#hex, or a palette colour name")]
                   + profile_inputs(),
            outputs=[IO.String.Output(display_name="cmyk"), IO.Float.Output(display_name="c"),
                     IO.Float.Output(display_name="m"), IO.Float.Output(display_name="y"),
                     IO.Float.Output(display_name="k")],
        )

    @classmethod
    def execute(cls, color, profile, intent, black_point, pure_black, cmyk_values, palette=None):
        cm = converter(profile, intent, black_point, pure_black, cmyk_values, palette)
        rgb = col.resolve_color(color, palette)
        c = cm.color(rgb[:3])
        text = f"{col.to_hex(rgb)} -> C/M/Y/K {cmk.fmt_cmyk(c)} ({cm.name})"
        return IO.NodeOutput(cmk.fmt_cmyk(c), *(round(v * 100, 1) for v in c), ui=UI.PreviewText(text))


NODES = [CNSavePrintPDF, CNSoftProof, CNCMYKValues]
