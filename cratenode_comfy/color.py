"""Colour: palettes, WCAG contrast, palette from image (k-means in Lab), recolouring
scenes, and brand kits. No ComfyUI imports.

A palette is an ordered tuple of (name, rgba). Brand kits are JSON files::

    {"cratenode_brand": 1, "name": "Example",
     "colors": {"primary": "#1f6feb", "accent": "#f2b134", ...},
     "fonts": {"heading": {"family": "Montserrat", "weight": 800},
               "body": {"family": "Inter", "weight": 400}},
     "logos": {"primary": "logo.png"},        # paths relative to the kit file
     "notes": "..."}
"""

from __future__ import annotations

import colorsys
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from . import scene as sc
from .render import parse_color

# ---- palettes ----


@dataclass(frozen=True)
class Palette:
    colors: tuple = ()  # ((name, (r, g, b, a)), ...)
    name: str = ""

    def names(self) -> list[str]:
        return [n for n, _ in self.colors]

    def get(self, key) -> tuple:
        """By name (case-insensitive), by 1-based index ("2"), or a literal #hex."""
        k = str(key).strip()
        for n, c in self.colors:
            if n.lower() == k.lower():
                return c
        if k.isdigit() and 1 <= int(k) <= len(self.colors):
            return self.colors[int(k) - 1][1]
        if k.startswith("#"):
            return parse_color(k)
        raise KeyError(f"palette has no colour {k!r}; it has {', '.join(self.names()) or 'none'}")

    def hexes(self) -> list[str]:
        return [to_hex(c) for _, c in self.colors]


def to_hex(c) -> str:
    h = "#" + "".join(f"{round(max(0.0, min(1.0, float(x))) * 255):02x}" for x in c[:3])
    a = c[3] if len(c) > 3 else 1.0
    return h if a >= 0.999 else h + f"{round(max(0.0, min(1.0, a)) * 255):02x}"


_HEX = re.compile(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b")


def parse_palette(text: str, name: str = "") -> Palette:
    """``name: #hex`` / ``name = #hex`` / ``name #hex`` lines, or bare #hex values
    (separated by spaces, commas or lines); bare colours are named color_1, color_2, ..."""
    out = []
    for line in (text or "").splitlines():
        line = line.split("//")[0].strip()
        if not line or line.startswith("#") and not _HEX.match(line):
            continue
        found = _HEX.findall(line)
        if not found:
            raise ValueError(f"no #rrggbb colour in palette line {line!r}")
        label = _HEX.sub("", line).strip(" :=,-\t")
        if label and len(found) == 1:
            out.append((label, parse_color(found[0])))
        else:
            out.extend((None, parse_color(h)) for h in found)
    named = []
    for i, (n, c) in enumerate(out, 1):
        named.append((n or f"color_{i}", c))
    return Palette(tuple(named), name)


# ---- contrast (WCAG 2.x) ----


def luminance(c) -> float:
    def lin(v):
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(float(x)) for x in c[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def wcag_grade(ratio: float, large: bool = False) -> str:
    if ratio >= (4.5 if large else 7.0):
        return "AAA"
    if ratio >= (3.0 if large else 4.5):
        return "AA"
    return "fail"


def best_contrast(against, candidates) -> tuple[str, tuple, float]:
    """The (name, colour, ratio) among candidates with the highest contrast."""
    best = max(candidates, key=lambda nc: contrast(nc[1], against))
    return best[0], best[1], contrast(best[1], against)


# ---- palette from image ----


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    rgb = np.clip(rgb, 0, 1)
    lin = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375],
                  [0.2126729, 0.7151522, 0.0721750],
                  [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack([116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1)


def _kmeans(x: np.ndarray, k: int, rng, iters: int = 25) -> tuple[np.ndarray, np.ndarray]:
    # k-means++ seeding
    centers = [x[rng.integers(len(x))]]
    for _ in range(1, k):
        d = np.min(((x[:, None, :] - np.array(centers)[None]) ** 2).sum(-1), axis=1)
        if d.sum() <= 0:
            break
        centers.append(x[rng.choice(len(x), p=d / d.sum())])
    c = np.array(centers)
    for _ in range(iters):
        lab = np.argmin(((x[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
        new = np.array([x[lab == j].mean(0) if np.any(lab == j) else c[j] for j in range(len(c))])
        if np.allclose(new, c, atol=1e-3):
            c = new
            break
        c = new
    lab = np.argmin(((x[:, None, :] - c[None]) ** 2).sum(-1), axis=1)
    return c, lab


SORTS = ["by share", "light to dark", "dark to light", "by hue"]


def palette_from_image(rgba: np.ndarray, count: int = 5, sort: str = "by share", min_distance: float = 8.0,
                       sample: int = 20000, seed: int = 0) -> tuple[Palette, list[float]]:
    """The image's main colours: k-means in Lab on up to ``sample`` opaque pixels.
    Clusters closer than ``min_distance`` (ΔE76) merge. Returns the palette and each
    colour's share of the pixels. Colours are the mean sRGB of each cluster."""
    px = rgba.reshape(-1, rgba.shape[-1])
    if px.shape[1] == 4:
        px = px[px[:, 3] > 0.5]
    rgb = px[:, :3].astype(np.float64)
    if len(rgb) == 0:
        raise ValueError("the image has no opaque pixels")
    rng = np.random.default_rng(seed)
    if len(rgb) > sample:
        rgb = rgb[rng.choice(len(rgb), sample, replace=False)]
    lab = srgb_to_lab(rgb)
    k = max(1, min(int(count), len(np.unique(np.round(rgb * 255), axis=0))))
    # over-cluster, then merge near-duplicates down to ``count``
    centers, labels = _kmeans(lab, min(k + 3, len(lab)), rng)
    groups = [[j] for j in range(len(centers))]
    sizes = [np.sum(labels == j) for j in range(len(centers))]

    def center(g):
        w = np.array([sizes[j] for j in g], float)
        return (centers[g] * w[:, None]).sum(0) / max(w.sum(), 1)

    while True:
        live = [g for g in groups if sum(sizes[j] for j in g) > 0]
        if len(live) <= 1:
            groups = live
            break
        cs = [center(g) for g in live]
        best, pair = None, None
        for a in range(len(live)):
            for b in range(a + 1, len(live)):
                d = float(np.linalg.norm(cs[a] - cs[b]))
                if best is None or d < best:
                    best, pair = d, (a, b)
        if len(live) > k or best < min_distance:
            a, b = pair
            live[a] = live[a] + live[b]
            del live[b]
            groups = live
            continue
        groups = live
        break
    total = len(labels)
    out = []
    for g in groups:
        mask = np.isin(labels, g)
        out.append((rgb[mask].mean(0), mask.sum() / total))
    out.sort(key=lambda t: -t[1])
    if sort == "light to dark":
        out.sort(key=lambda t: -luminance(t[0]))
    elif sort == "dark to light":
        out.sort(key=lambda t: luminance(t[0]))
    elif sort == "by hue":
        out.sort(key=lambda t: colorsys.rgb_to_hsv(*t[0])[0])
    pal = Palette(tuple((f"color_{i}", (float(c[0]), float(c[1]), float(c[2]), 1.0))
                        for i, (c, _) in enumerate(out, 1)), "from image")
    return pal, [float(s) for _, s in out]


# ---- recolouring scenes ----


def _close(a, b, tol: float) -> bool:
    return max(abs(float(x) - float(y)) for x, y in zip(a[:3], b[:3])) <= tol


def recolor(scene: sc.Scene, mapping: list[tuple[tuple, tuple]], tolerance: float = 0.02,
            keep_alpha: bool = True) -> tuple[sc.Scene, int]:
    """Swap colours everywhere (text, shapes, strokes, gradients, effects, background).
    ``mapping`` is [(from_rgba, to_rgba)]; a colour within ``tolerance`` (0..1 per
    channel) of a from-colour becomes its to-colour (keeping its own alpha). Returns
    the scene and how many colours changed."""
    count = [0]

    def c(col):
        if col is None or not isinstance(col, tuple) or len(col) < 3 or not all(
                isinstance(v, (int, float)) for v in col):
            return col
        for src, dst in mapping:
            if _close(col, src, tolerance):
                count[0] += 1
                a = col[3] if keep_alpha and len(col) > 3 else (dst[3] if len(dst) > 3 else 1.0)
                return (dst[0], dst[1], dst[2], a)
        return col

    def fill(f):
        if isinstance(f, sc.Gradient):
            return replace(f, stops=tuple((p, c(col)) for p, col in f.stops))
        return c(f)

    def style(st):
        effs = tuple(replace(e, color=c(e.color)) if hasattr(e, "color") else e for e in st.effects)
        return replace(st, effects=effs) if effs != st.effects else st

    def item(it):
        if isinstance(it, sc.TextItem):
            it = replace(it, spec=replace(it.spec, color=c(it.spec.color)), fill=fill(it.fill) if it.fill else None)
        elif isinstance(it, sc.ShapeItem):
            it = replace(it, fill=fill(it.fill), stroke=c(it.stroke))
        elif isinstance(it, sc.GroupItem):
            it = replace(it, items=tuple(item(x) for x in it.items))
        elif isinstance(it, sc.LayoutItem):
            it = replace(it, parts=tuple(tuple(item(x) for x in p) for p in it.parts))
        return replace(it, style=style(it.style))

    out = replace(scene, background=fill(scene.background), items=tuple(item(x) for x in scene.items))
    return out, count[0]


def parse_mapping(text: str, palette: Palette | None = None) -> list[tuple[tuple, tuple]]:
    """``#from -> #to`` lines; either side may be a palette colour name."""
    out = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or line.startswith("//"):
            continue
        parts = re.split(r"\s*(?:->|=>|→)\s*", line)
        if len(parts) != 2:
            raise ValueError(f"recolour line {line!r} is not 'from -> to'")
        out.append(tuple(resolve_color(p, palette) for p in parts))
    return out


def resolve_color(s: str, palette: Palette | None = None) -> tuple:
    s = str(s).strip()
    if s.startswith("#") or palette is None:
        return parse_color(s)
    return palette.get(s)


# ---- brand kits ----


@dataclass(frozen=True)
class BrandKit:
    name: str
    palette: Palette
    fonts: dict
    logos: dict  # name -> Path
    notes: str = ""
    path: Path | None = None

    def font(self, role: str) -> tuple[str, int]:
        f = self.fonts.get(role) or {}
        return str(f.get("family", "")), int(f.get("weight", 400))


def load_brand(path: str | Path) -> BrandKit:
    path = Path(path)
    d = json.loads(path.read_text(encoding="utf-8"))
    if "cratenode_brand" not in d:
        raise ValueError(f"{path} is not a CrateNode-Comfy brand kit")
    cols = d.get("colors", {})
    items = cols.items() if isinstance(cols, dict) else enumerate(cols, 1)
    pal = Palette(tuple((str(k) if isinstance(cols, dict) else f"color_{k}", parse_color(v)) for k, v in items),
                  d.get("name", path.stem))
    logos = {k: (path.parent / v) for k, v in (d.get("logos") or {}).items()}
    return BrandKit(d.get("name", path.stem), pal, d.get("fonts") or {}, logos, d.get("notes", ""), path)


def find_brands(folders: list[Path]) -> dict[str, Path]:
    """{name: path}: every brand JSON (``*.json`` with "cratenode_brand") in folders; earlier wins."""
    out: dict[str, Path] = {}
    for folder in folders:
        if not folder or not Path(folder).is_dir():
            continue
        for p in sorted(Path(folder).rglob("*.json")):
            try:
                if "cratenode_brand" not in p.read_text(encoding="utf-8")[:400]:
                    continue
            except OSError:
                continue
            name = p.relative_to(folder).with_suffix("").as_posix()
            if name.endswith("/brand"):
                name = name[: -len("/brand")]
            out.setdefault(name, p)
    return out


# ---- swatches ----


def swatch_scene(palette: Palette, cell: int = 160, shares: list[float] | None = None) -> sc.Scene:
    """A strip of swatches with each colour's name and hex, in the most readable ink."""
    from .text import TextSpec

    n = max(1, len(palette.colors))
    s = sc.Scene(cell * n, cell, (1.0, 1.0, 1.0, 1.0))
    for i, (name, col) in enumerate(palette.colors):
        x = i * cell
        s = s.add(sc.ShapeItem("rectangle", x, 0, cell, cell, (col[0], col[1], col[2], 1.0)))
        _, ink, _ = best_contrast(col, [("w", (1.0, 1.0, 1.0, 1.0)), ("k", (0.0, 0.0, 0.0, 1.0))])
        label = f"{name}\n{to_hex(col)}"
        if shares:
            label += f"\n{shares[i] * 100:.0f}%"
        s = s.add(sc.TextItem(TextSpec(label, "Inter", 500, size=max(10, cell // 9), color=ink, x=x + 8,
                                       y=8, width=cell - 16, line_height=1.15)))
    return s
