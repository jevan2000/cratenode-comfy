"""Templates and data: scenes as JSON with named slots, data rows from CSV/JSON,
filling slots from a row, and filename templates.

No ComfyUI imports, so all of it is unit-testable.

A template file is::

    {"cratenode_template": 1, "name": "...", "description": "...",
     "slots": [{"name": "title", "kind": "text", "default": "..."}, ...],
     "scene": {"type": "Scene", ...}}

``slots`` is a summary for people and agents; the scene is the source of truth.
Items are dataclasses written as ``{"type": ClassName, field: value}`` with fields
left out when they equal the default. Images are embedded (JPEG when opaque, else PNG).
"""

from __future__ import annotations

import base64
import csv
import io
import json
import re
import time
from dataclasses import MISSING, fields, is_dataclass, replace
from pathlib import Path

import numpy as np
from PIL import Image

from . import scene as sc
from . import text as textmod
from .render import parse_color

VERSION = 1
_CLASSES = {c.__name__: c for c in (
    sc.Scene, sc.TextItem, sc.ImageItem, sc.ShapeItem, sc.GroupItem, sc.LayoutItem, sc.Style, sc.Flow,
    sc.Gradient, sc.Shadow, sc.Glow, sc.Outline, sc.Blur, textmod.TextSpec)}


# ---- scene <-> JSON ----

def _encode_image(rgba: np.ndarray) -> dict:
    u8 = np.round(np.clip(rgba, 0, 1) * 255).astype(np.uint8)
    buf = io.BytesIO()
    if u8[:, :, 3].min() == 255:
        Image.fromarray(u8[:, :, :3], "RGB").save(buf, "JPEG", quality=92, subsampling=0)
        fmt = "jpeg"
    else:
        Image.fromarray(u8, "RGBA").save(buf, "PNG", optimize=True)
        fmt = "png"
    return {"image": fmt, "data": base64.b64encode(buf.getvalue()).decode("ascii")}


def decode_image(d: dict) -> np.ndarray:
    im = Image.open(io.BytesIO(base64.b64decode(d["data"]))).convert("RGBA")
    return np.asarray(im, dtype=np.float32) / 255.0


def _default(f):
    if f.default is not MISSING:
        return f.default
    if f.default_factory is not MISSING:  # type: ignore[misc]
        return f.default_factory()  # type: ignore[misc]
    return MISSING


def to_data(obj):
    """Plain JSON-able data for a scene, item or any value inside one."""
    if isinstance(obj, np.ndarray):
        return _encode_image(obj)
    if is_dataclass(obj):
        out = {"type": type(obj).__name__}
        for f in fields(obj):
            if not f.init:
                continue
            v = getattr(obj, f.name)
            d = _default(f)
            if d is not MISSING and not isinstance(v, np.ndarray) and v == d:
                continue
            out[f.name] = to_data(v)
        return out
    if isinstance(obj, (tuple, list)):
        return [to_data(v) for v in obj]
    return obj


def from_data(v):
    """The inverse of ``to_data`` (lists come back as tuples, as the scene model uses)."""
    if isinstance(v, dict):
        if "image" in v and "data" in v:
            return decode_image(v)
        cls = _CLASSES.get(v.get("type", ""))
        if cls is None:
            raise ValueError(f"unknown template object type {v.get('type')!r}")
        known = {f.name for f in fields(cls) if f.init}
        return cls(**{k: from_data(x) for k, x in v.items() if k != "type" and k in known})
    if isinstance(v, list):
        return tuple(from_data(x) for x in v)
    return v


# ---- slots ----

def walk(items: tuple):
    """Every item, depth first, including inside groups and layouts."""
    for it in items:
        yield it
        if isinstance(it, sc.GroupItem):
            yield from walk(it.items)
        elif isinstance(it, sc.LayoutItem):
            for part in it.parts:
                yield from walk(part)


def _hex(c) -> str:
    return "#" + "".join(f"{round(max(0, min(1, x)) * 255):02x}" for x in c[:4]).removesuffix("ff")


def slots(scene: sc.Scene) -> list[dict]:
    out, seen = [], set()
    for it in walk(scene.items):
        if not it.name or it.name in seen:
            continue
        seen.add(it.name)
        if isinstance(it, sc.TextItem):
            out.append({"name": it.name, "kind": "text", "default": it.spec.text, "color": _hex(it.spec.color)})
        elif isinstance(it, sc.ImageItem):
            h, w = it.rgba.shape[:2]
            out.append({"name": it.name, "kind": "image", "default": f"{w}x{h} image"})
        elif isinstance(it, sc.ShapeItem):
            c = _hex(it.fill) if isinstance(it.fill, tuple) else "gradient"
            out.append({"name": it.name, "kind": "shape", "color": c})
        else:
            out.append({"name": it.name, "kind": "group"})
    return out


def placeholders(scene: sc.Scene) -> list[str]:
    """``{key}`` placeholders used in any text."""
    keys = []
    for it in walk(scene.items):
        if isinstance(it, sc.TextItem):
            for k in re.findall(r"\{([A-Za-z0-9_ .-]+)\}", it.spec.text):
                if k not in keys:
                    keys.append(k)
    return keys


# ---- filling ----

def _fill_text(t: str, values: dict) -> str:
    def sub(m):
        k = m.group(1)
        return str(values[k]) if k in values else m.group(0)

    return re.sub(r"\{([A-Za-z0-9_ .-]+)\}", sub, t)


def fill(scene: sc.Scene, values: dict | None = None, images: dict | None = None,
         palette=None) -> tuple[sc.Scene, list[str]]:
    """Fill named slots and ``{key}`` placeholders.

    - ``values[name]`` replaces the text of a text slot;
    - ``values["name.color"]`` recolours a text or shape slot (#rrggbb[aa]);
    - ``{key}`` anywhere in any text is replaced by ``values[key]``;
    - ``images[name]`` (H x W x 4 float) replaces an image slot.

    With a ``palette`` (color.Palette), colour values may be palette names ("primary").

    Returns the new scene and the value/image keys that matched nothing.
    """

    def to_color(v):
        v = str(v).strip()
        return palette.get(v) if palette is not None and not v.startswith("#") else parse_color(v)

    values = {str(k): v for k, v in (values or {}).items()}
    images = images or {}
    used: set[str] = set()

    def one(it):
        if isinstance(it, sc.GroupItem):
            return replace(it, items=tuple(one(x) for x in it.items))
        if isinstance(it, sc.LayoutItem):
            return replace(it, parts=tuple(tuple(one(x) for x in p) for p in it.parts))
        name = it.name
        if isinstance(it, sc.TextItem):
            spec = it.spec
            if name and name in values:
                spec = replace(spec, text=str(values[name]))
                used.add(name)
            new_text = _fill_text(spec.text, values)
            if new_text != spec.text:
                used.update(k for k in values if "{" + k + "}" in spec.text)
                spec = replace(spec, text=new_text)
            if name and f"{name}.color" in values:
                spec = replace(spec, color=to_color(values[f"{name}.color"]))
                used.add(f"{name}.color")
            return replace(it, spec=spec) if spec is not it.spec else it
        if isinstance(it, sc.ShapeItem) and name and f"{name}.color" in values:
            used.add(f"{name}.color")
            return replace(it, fill=to_color(values[f"{name}.color"]))
        if isinstance(it, sc.ImageItem) and name and name in images:
            used.add(name)
            return replace(it, rgba=images[name])
        return it

    out = replace(scene, items=tuple(one(x) for x in scene.items))
    unused = [k for k in list(values) + list(images) if k not in used]
    return out, unused


# ---- files ----

def template_data(scene: sc.Scene, name: str = "", description: str = "") -> dict:
    return {"cratenode_template": VERSION, "name": name, "description": description,
            "slots": slots(scene), "placeholders": placeholders(scene), "scene": to_data(scene)}


def save(scene: sc.Scene, path: str | Path, name: str = "", description: str = "") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template_data(scene, name or path.stem, description), indent=1,
                               ensure_ascii=False), encoding="utf-8")
    return path


def load(path: str | Path) -> tuple[sc.Scene, dict]:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if "cratenode_template" not in d or "scene" not in d:
        raise ValueError(f"{path} is not a CrateNode-Comfy template")
    if d["cratenode_template"] > VERSION:
        raise ValueError(f"{path} is template version {d['cratenode_template']}; this pack reads {VERSION}")
    scene = from_data(d["scene"])
    if not isinstance(scene, sc.Scene):
        raise ValueError(f"{path}: 'scene' is not a Scene")
    return scene, d


def find_templates(folders: list[Path]) -> dict[str, Path]:
    """{name: path} for *.json templates in folders (earlier folders win), names relative to the folder."""
    out: dict[str, Path] = {}
    for folder in folders:
        if not folder or not Path(folder).is_dir():
            continue
        for p in sorted(Path(folder).rglob("*.json")):
            name = p.relative_to(folder).with_suffix("").as_posix()
            out.setdefault(name, p)
    return out


# ---- data rows ----

def parse_rows(text: str, fmt: str = "auto") -> list[dict]:
    """Rows from CSV (header line) or JSON (a list of objects, or {"rows": [...]}).
    Every value becomes a string; blank CSV lines are skipped."""
    text = text.lstrip("﻿")
    if fmt == "auto":
        fmt = "json" if text.lstrip()[:1] in "[{" else "csv"
    if fmt == "json":
        d = json.loads(text)
        if isinstance(d, dict):
            d = d.get("rows", [d])
        if not isinstance(d, list) or not all(isinstance(r, dict) for r in d):
            raise ValueError("JSON rows must be a list of objects (or {\"rows\": [...]})")
        rows = d
    else:
        reader = csv.DictReader(io.StringIO(text))
        rows = [r for r in reader if any((v or "").strip() for v in r.values())]
    return [{str(k).strip(): ("" if v is None else v if isinstance(v, str) else json.dumps(v)
                               if isinstance(v, (dict, list)) else str(v))
             for k, v in r.items() if k is not None} for r in rows]


def load_rows(path: str | Path) -> list[dict]:
    p = Path(path)
    return parse_rows(p.read_text(encoding="utf-8-sig"), "json" if p.suffix.lower() == ".json" else "csv")


# ---- filenames ----

_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


def safe_part(v: str, limit: int = 80) -> str:
    """A value made safe for one path segment (no slashes, no reserved characters)."""
    s = _UNSAFE.sub("-", str(v).replace("*", ""))  # drop *bold* markup
    s = re.sub(r"\s*-[\s-]*", "-", s)  # "Peace: Now" -> "Peace-Now", not "Peace- Now"
    s = re.sub(r"\s+", " ", s)
    return s[:limit].strip(" .-") or "_"


def format_name(template: str, row: dict | None = None, index: int | None = None) -> str:
    """Fill ``{key}`` in a filename template from a row, plus {date}, {time} and {index}
    (1-based, 3 digits). Values cannot add folders; the template itself can."""
    row = dict(row or {})
    if index is None and str(row.get("_index", "")).isdigit():
        index = int(row["_index"])
    now = time.localtime()
    extra = {"date": time.strftime("%Y-%m-%d", now), "time": time.strftime("%H%M%S", now)}
    if index is not None:
        extra["index"] = f"{index + 1:03d}"

    def sub(m):
        k = m.group(1)
        if k in row:
            return safe_part(row[k])
        if k in extra:
            return extra[k]
        raise ValueError(f"filename template uses {{{k}}}, but the row has only: {', '.join(row) or 'no columns'}")

    return re.sub(r"\{([A-Za-z0-9_ .-]+)\}", sub, template)
