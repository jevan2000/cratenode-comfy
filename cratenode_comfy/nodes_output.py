"""Output: render a scene to IMAGE/MASK, export PNG/JPEG/WebP, or save a vector PDF."""

from __future__ import annotations

import os

from comfy_api.latest import IO, UI

from . import export, render
from . import template as tpl
from . import scene as sc
from .nodes_common import MASK_MEANINGS, ROOT, RowT, SceneT, mask_to_alpha, with_warnings

CAT = f"{ROOT}/Output"
NAME_TIP = ("{column} takes a value from the data row; also {date}, {time}, {index} (row number), "
            "and ComfyUI's %date:yyyy-MM-dd%, %width%, %height%. a/b makes a subfolder")


class CNRender(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNRender", display_name="Render Scene", category=CAT,
            description="Turn a design into an IMAGE and its alpha MASK (1 = opaque) for any ComfyUI node. "
                        "scale 2 renders at twice the canvas size, still sharp.",
            inputs=[SceneT.Input("scene"), IO.Float.Input("scale", default=1.0, min=0.05, max=8.0, step=0.05)],
            outputs=[IO.Image.Output(display_name="image"), IO.Mask.Output(display_name="alpha")],
        )

    @classmethod
    def execute(cls, scene, scale):
        img, alpha = render.rgba_to_comfy(sc.render(scene, scale))
        return IO.NodeOutput(img, alpha)


class CNSavePDF(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSavePDF", display_name="Save PDF", category=CAT,
            description="Vector RGB PDF (text stays text, fonts embedded) in the output folder.",
            is_output_node=True,
            inputs=[SceneT.Input("scene"), IO.String.Input("filename_prefix", default="design",
                                                           tooltip=NAME_TIP),
                    RowT.Input("row", optional=True, tooltip="A data row for {column} names"),
                    IO.Float.Input("dpi", default=300.0, min=10.0, max=2400.0, tooltip="Canvas pixels per inch")],
            outputs=[IO.String.Output(display_name="path")],
        )

    @classmethod
    def execute(cls, scene, filename_prefix, dpi, row=None):
        import folder_paths

        filename_prefix = tpl.format_name(filename_prefix, row)
        out_dir, base, counter, _, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), scene.width, scene.height)
        path = os.path.join(out_dir, f"{base}_{counter:05}_.pdf")
        sc.to_pdf(scene, path, dpi)
        return IO.NodeOutput(path, ui=UI.PreviewText(with_warnings(f"saved {os.path.basename(path)}", scene.items)))


class CNExport(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNExport", display_name="Export Image", category=CAT,
            description="Save a design (or any IMAGE batch) as PNG, JPEG or WebP. Transparency is kept in PNG/WebP; "
                        "JPEG is flattened onto the matte colour. max_kb lowers JPEG/WebP quality until the file fits "
                        "(e.g. 2000 for a YouTube thumbnail). Filename prefix accepts %date:yyyy-MM-dd%-style "
                        "ComfyUI variables and %width%/%height%.",
            is_output_node=True,
            inputs=[
                SceneT.Input("scene", optional=True, tooltip="A design; rendered at scale"),
                IO.Image.Input("image", optional=True, tooltip="Or any IMAGE (batch); used when no scene is connected"),
                IO.Mask.Input("alpha", optional=True, tooltip="Transparency for image"),
                IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[1],
                               tooltip="Render Scene's alpha is coverage (1 = opaque); Load Image's mask is the reverse"),
                IO.Combo.Input("format", options=list(export.FORMATS), default="png"),
                IO.Int.Input("quality", default=92, min=1, max=100, tooltip="JPEG and lossy WebP"),
                IO.Boolean.Input("webp_lossless", default=False),
                IO.Boolean.Input("transparent", default=True, tooltip="Keep transparency (PNG / WebP)"),
                IO.String.Input("matte", default="#ffffff", tooltip="Colour behind transparent areas when flattening"),
                IO.Float.Input("scale", default=1.0, min=0.05, max=8.0, step=0.05,
                               tooltip="Scenes re-render sharp; images are resampled"),
                IO.Float.Input("dpi", default=0.0, min=0.0, max=2400.0, tooltip="Written to PNG/JPEG; 0 = none"),
                IO.Int.Input("max_kb", default=0, min=0, max=1_000_000, tooltip="File size limit; 0 = none"),
                IO.Boolean.Input("embed_workflow", default=True, tooltip="PNG / WebP carry the workflow, like Save Image"),
                IO.String.Input("filename_prefix", default="design", tooltip=NAME_TIP),
                RowT.Input("row", optional=True, tooltip="A data row for {column} names"),
            ],
            outputs=[IO.String.Output(display_name="paths"), IO.String.Output(display_name="report")],
            hidden=[IO.Hidden.prompt, IO.Hidden.extra_pnginfo],
        )

    @classmethod
    def execute(cls, format, quality, webp_lossless, transparent, matte, scale, dpi, max_kb, embed_workflow,
                filename_prefix, scene=None, image=None, alpha=None, mask_meaning=MASK_MEANINGS[1], row=None):
        import folder_paths

        filename_prefix = tpl.format_name(filename_prefix, row)
        if scene is not None:
            frames = [sc.render(scene, scale)]
        elif image is not None:
            mask = mask_to_alpha(alpha, mask_meaning)
            frames = [export.resize(render.comfy_to_rgba(image, mask, i), scale) for i in range(image.shape[0])]
        else:
            raise ValueError("connect a scene or an image")
        h, w = frames[0].shape[:2]
        out_dir, base, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), w, h)
        paths, results, lines = [], [], []
        for i, rgba in enumerate(frames):
            opts = export.ExportOptions(format, quality, webp_lossless, transparent, matte, dpi, max_kb)
            if embed_workflow:
                opts.extra = cls._metadata(format, export.to_pil(rgba[:1, :1], True))
            enc = export.encode(rgba, opts)
            name = f"{base.replace('%batch_num%', str(i))}_{counter:05}_{export.EXT[format]}"
            path = os.path.join(out_dir, name)
            with open(path, "wb") as f:
                f.write(enc.data)
            counter += 1
            paths.append(path)
            results.append(UI.SavedResult(name, subfolder, IO.FolderType.output))
            q = f", quality {enc.quality}" if enc.quality is not None else ""
            warn = "" if enc.fits else f" — over the {max_kb} KB limit"
            lines.append(f"{name}: {rgba.shape[1]}x{rgba.shape[0]}, {enc.kb:.0f} KB{q}{warn}")
        report = "\n".join(lines)
        if scene is not None:
            report = with_warnings(report, scene.items)
        return IO.NodeOutput("\n".join(paths), report, ui=UI.SavedImages(results))

    @classmethod
    def _metadata(cls, fmt, probe):
        """Workflow metadata the way ComfyUI's own savers write it (PNG text chunks, WebP EXIF)."""
        try:
            if fmt == "png":
                info = UI.ImageSaveHelper._create_png_metadata(cls)
                return {"pnginfo": info} if info is not None else {}
            if fmt == "webp":
                return {"exif": UI.ImageSaveHelper._create_webp_metadata(probe, cls)}
        except Exception:  # metadata is a nicety; never fail an export over it
            pass
        return {}


NODES = [CNRender, CNExport, CNSavePDF]
