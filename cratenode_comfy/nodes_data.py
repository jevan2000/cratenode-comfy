"""Templates and data: load / save / fill templates, and CSV / JSON rows that run a
workflow once per row (ComfyUI list execution)."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from comfy_api.latest import IO, UI

from . import render
from . import template as tpl
from .fonts import registry
from .nodes_common import MASK_MEANINGS, ROOT, PaletteT, RowT, SceneT, data_path, mask_to_alpha

CAT = f"{ROOT}/Data"
NONE = "(none)"
N_IMAGES = 3


def _config():
    return registry().config


def _templates() -> dict[str, Path]:
    return tpl.find_templates(_config().template_folders())


def _mtime(p: Path | None):
    try:
        return os.path.getmtime(p) if p else None
    except OSError:
        return None


def parse_values(text: str) -> dict:
    """A JSON object, or ``key: value`` / ``key = value`` lines."""
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        d = json.loads(text)
        if not isinstance(d, dict):
            raise ValueError("values must be a JSON object")
        return {str(k): v if isinstance(v, str) else json.dumps(v) if isinstance(v, (dict, list)) else str(v)
                for k, v in d.items()}
    out = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        sep = min((i for i in (line.find(":"), line.find("=")) if i > 0), default=-1)
        if sep < 0:
            raise ValueError(f"values line {line!r} is not 'key: value'")
        out[line[:sep].strip()] = line[sep + 1:].strip().replace("\\n", "\n")
    return out


class CNLoadTemplate(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        names = sorted(_templates())
        return IO.Schema(
            node_id="CNLoadTemplate", display_name="Load Template", category=CAT,
            description="A saved design (JSON) as a scene. Templates come from your data folder's templates/ "
                        "and the bundled examples. Fill it with Fill Template.",
            inputs=[IO.Combo.Input("template", options=[NONE] + names, default=names[0] if names else NONE),
                    IO.String.Input("path", default="", tooltip="Any template file; used instead of the list when set")],
            outputs=[SceneT.Output(display_name="scene"), IO.String.Output(display_name="slots")],
        )

    @classmethod
    def _path(cls, template, path):
        if (path or "").strip():
            return data_path(path)
        if template == NONE:
            raise ValueError("pick a template or give a path")
        p = _templates().get(template)
        if p is None:
            raise ValueError(f"template {template!r} not found")
        return p

    @classmethod
    def fingerprint_inputs(cls, template, path):
        try:
            return _mtime(cls._path(template, path))
        except (ValueError, PermissionError):
            return None

    @classmethod
    def execute(cls, template, path):
        scene, data = tpl.load(cls._path(template, path))
        info = {"slots": tpl.slots(scene), "placeholders": tpl.placeholders(scene)}
        return IO.NodeOutput(scene, json.dumps(info, indent=1, ensure_ascii=False))


class CNSaveTemplate(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSaveTemplate", display_name="Save as Template", category=CAT,
            description="Write a design to a template JSON (images embedded). Give items a 'slot' name so "
                        "Fill Template can change them, or put {placeholders} in text.",
            is_output_node=True,
            inputs=[SceneT.Input("scene"), IO.String.Input("name", default="my-template",
                                                           tooltip="File name; a/b makes a subfolder"),
                    IO.String.Input("description", default="", multiline=True),
                    IO.Combo.Input("folder", options=["data folder templates", "ComfyUI output"],
                                   tooltip="The data folder is set in config (data_dir); without one, output is used"),
                    IO.Boolean.Input("overwrite", default=False)],
            outputs=[IO.String.Output(display_name="path")],
        )

    @classmethod
    def execute(cls, scene, name, description, folder, overwrite):
        cfg = _config()
        if folder.startswith("data") and cfg.data_dir:
            root = cfg.data_dir / "templates"
        else:
            import folder_paths

            root = Path(folder_paths.get_output_directory()) / "cratenode-templates"
        segs = [tpl.safe_part(s) for s in name.replace("\\", "/").split("/") if s.strip() not in ("", ".", "..")]
        if not segs:
            raise ValueError("give the template a name")
        path = root.joinpath(*segs).with_suffix(".json")
        if path.exists() and not overwrite:
            raise ValueError(f"{path.name} already exists; turn on overwrite or change the name")
        tpl.save(scene, path, "/".join(segs), description)
        n = len(tpl.slots(scene))
        return IO.NodeOutput(str(path), ui=UI.PreviewText(f"saved {path.name} ({n} slots)"))


class CNFillTemplate(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        imgs = []
        for i in range(1, N_IMAGES + 1):
            imgs += [IO.Image.Input(f"image_{i}", optional=True), IO.Mask.Input(f"mask_{i}", optional=True),
                     IO.String.Input(f"slot_{i}", default="", tooltip=f"The image slot image_{i} replaces")]
        return IO.Schema(
            node_id="CNFillTemplate", display_name="Fill Template", category=CAT,
            description="Replace slot text (by slot name), colours (name.color) and {placeholders} from a data row "
                        "and/or the values box, and image slots from images. Layouts reflow to the new text.",
            inputs=[SceneT.Input("scene"), RowT.Input("row", optional=True),
                    PaletteT.Input("palette", optional=True,
                                   tooltip="Lets colour values be palette names (title.color: accent)"),
                    IO.String.Input("values", default="", multiline=True,
                                    tooltip="key: value lines or a JSON object; these win over the row"),
                    IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[0])] + imgs,
            outputs=[SceneT.Output(display_name="scene"), IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, scene, values, mask_meaning, row=None, palette=None, **kw):
        vals = {k: v for k, v in (row or {}).items() if not k.startswith("_")}
        vals.update(parse_values(values))
        images = {}
        for i in range(1, N_IMAGES + 1):
            img, name = kw.get(f"image_{i}"), (kw.get(f"slot_{i}") or "").strip()
            if img is not None and name:
                images[name] = render.comfy_to_rgba(img, mask_to_alpha(kw.get(f"mask_{i}"), mask_meaning))
        out, unused = tpl.fill(scene, vals, images, palette)
        report = "all values used" if not unused else "not in the template: " + ", ".join(unused)
        if unused:
            logging.info("CrateNode-Comfy Fill Template: %s", report)
        return IO.NodeOutput(out, report)


class CNDataRows(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNDataRows", display_name="Data Rows", category=CAT,
            description="Rows from a CSV (with a header line) or JSON file, or pasted text. The row output is a "
                        "list, so everything after it runs once per row (one design per row).",
            inputs=[IO.String.Input("file", default="", tooltip="CSV/JSON path; relative paths look in the data folder"),
                    IO.String.Input("text", default="", multiline=True, tooltip="Pasted CSV or JSON, used when file is empty"),
                    IO.Combo.Input("format", options=["auto", "csv", "json"], default="auto"),
                    IO.Int.Input("start", default=0, min=0, max=1_000_000, tooltip="First row (0 = the first)"),
                    IO.Int.Input("limit", default=0, min=0, max=1_000_000, tooltip="How many rows; 0 = all")],
            outputs=[RowT.Output(display_name="row", is_output_list=True),
                     IO.Int.Output(display_name="count"), IO.String.Output(display_name="columns")],
        )

    @classmethod
    def fingerprint_inputs(cls, file, text, format, start, limit):
        try:
            return _mtime(data_path(file)) if (file or "").strip() else None
        except PermissionError:
            return None

    @classmethod
    def execute(cls, file, text, format, start, limit):
        if (file or "").strip():
            p = data_path(file)
            src = p.read_text(encoding="utf-8-sig")
            fmt = format if format != "auto" else ("json" if p.suffix.lower() == ".json" else "auto")
        else:
            src, fmt = text, format
        rows = tpl.parse_rows(src, fmt)
        for i, r in enumerate(rows):
            r["_index"] = str(i)
        rows = rows[start:start + limit] if limit else rows[start:]
        if not rows:
            raise ValueError("no data rows (check the file, start and limit)")
        cols = [c for c in rows[0] if not c.startswith("_")]
        return IO.NodeOutput(rows, len(rows), ", ".join(cols))


class CNRowValue(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNRowValue", display_name="Row Value", category=CAT,
            description="One column of a data row as text, to wire into any text input (e.g. a Text Box).",
            inputs=[RowT.Input("row"), IO.String.Input("column", default="title"),
                    IO.String.Input("default", default="", tooltip="Used when the column is missing or empty")],
            outputs=[IO.String.Output(display_name="text")],
        )

    @classmethod
    def execute(cls, row, column, default):
        v = row.get(column.strip(), "")
        return IO.NodeOutput(v if str(v).strip() else default)


NODES = [CNLoadTemplate, CNFillTemplate, CNSaveTemplate, CNDataRows, CNRowValue]
