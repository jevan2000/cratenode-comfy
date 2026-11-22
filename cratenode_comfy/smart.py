"""Smart design helpers: where an image is quiet, whether text is readable, and how
strong a scrim must be to make it readable. No models: image statistics in torch
(CPU, or the GPU through devices.pick).

- ``busyness``: 0..1 per pixel, how much is going on (edges + local contrast).
- ``quiet_box``: the box of a given size, inside an area, over the calmest pixels.
- ``readability``: WCAG contrast of every text item against what is behind its glyphs.
- ``scrim_for``: the weakest scrim (box, gradient band or soft glow) that reaches a
  target contrast behind an item.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

from . import color as col
from . import scene as sc
from .fonts import FontRegistry, registry

ANALYSIS_SIDE = 512  # analyse at most this many pixels on the long side


# ---- busyness ----


def busyness(rgb: np.ndarray, device=None, max_side: int = ANALYSIS_SIDE) -> tuple[np.ndarray, float]:
    """(map, factor): a 0..1 activity map at reduced size, and map pixels per image pixel."""
    import torch
    import torch.nn.functional as F

    dev = device or torch.device("cpu")
    h, w = rgb.shape[:2]
    f = min(1.0, max_side / max(h, w))
    x = torch.from_numpy(np.ascontiguousarray(rgb[:, :, :3], dtype=np.float32)).to(dev).permute(2, 0, 1)[None]
    if f < 1.0:
        x = F.interpolate(x, size=(max(1, round(h * f)), max(1, round(w * f))), mode="area")
    y = (0.2126 * x[:, 0] + 0.7152 * x[:, 1] + 0.0722 * x[:, 2])[:, None]  # luma
    kx = torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=torch.float32, device=dev)[None, None] / 4
    yp = F.pad(y, (1, 1, 1, 1), mode="replicate")
    gx, gy = F.conv2d(yp, kx), F.conv2d(yp, kx.transpose(2, 3))
    edges = torch.sqrt(gx * gx + gy * gy)
    k = 9
    mean = F.avg_pool2d(F.pad(y, (k // 2,) * 4, mode="replicate"), k, 1)
    sq = F.avg_pool2d(F.pad(y * y, (k // 2,) * 4, mode="replicate"), k, 1)
    std = torch.sqrt(torch.clamp(sq - mean * mean, min=0))
    act = 0.6 * edges / 0.25 + 0.4 * std / 0.25  # both ~0.25 on a hard, busy texture
    s = 15
    act = F.avg_pool2d(F.pad(act, (s // 2,) * 4, mode="replicate"), s, 1)
    return torch.clamp(act, 0, 1)[0, 0].float().cpu().numpy(), f


def _integral(m: np.ndarray) -> np.ndarray:
    ii = np.zeros((m.shape[0] + 1, m.shape[1] + 1), np.float64)
    ii[1:, 1:] = m.cumsum(0).cumsum(1)
    return ii


def _box_mean(ii, x0, y0, x1, y1):
    return (ii[y1, x1] - ii[y0, x1] - ii[y1, x0] + ii[y0, x0]) / max(1, (x1 - x0) * (y1 - y0))


@dataclass
class Spot:
    x: float
    y: float
    w: float
    h: float
    score: float  # mean busyness inside, 0 = calm
    mean_color: tuple

    @property
    def box(self):
        return (self.x, self.y, self.w, self.h)


CANDIDATES = ["anywhere", "9 positions"]


def quiet_box(rgb: np.ndarray, w: float, h: float, area=None, candidates: str = "anywhere", device=None,
              busy: tuple | None = None) -> tuple[Spot, np.ndarray, float]:
    """The w x h box inside ``area`` (x, y, aw, ah; default the whole image) whose pixels
    are calmest. Returns the spot, the busyness map and its scale factor."""
    H, W = rgb.shape[:2]
    ax, ay, aw, ah = area or (0, 0, W, H)
    w, h = min(w, aw), min(h, ah)
    m, f = busy or busyness(rgb, device)
    ii = _integral(m)
    mh, mw = m.shape

    def score(x, y):
        x0, y0 = int(round(x * f)), int(round(y * f))
        x1, y1 = max(x0 + 1, int(round((x + w) * f))), max(y0 + 1, int(round((y + h) * f)))
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(mw, x1), min(mh, y1)
        return _box_mean(ii, x0, y0, x1, y1)

    if candidates == "9 positions":
        xs = [ax, ax + (aw - w) / 2, ax + aw - w]
        ys = [ay, ay + (ah - h) / 2, ay + ah - h]
    else:
        step = max(4.0, min(w, h) / 6, 2.0 / f)
        xs = list(np.arange(ax, ax + aw - w + 1e-6, step)) + [ax + aw - w]
        ys = list(np.arange(ay, ay + ah - h + 1e-6, step)) + [ay + ah - h]
    best = None
    for y in ys:
        for x in xs:
            s = score(x, y)
            if best is None or s < best[0] - 1e-9:
                best = (s, x, y)
    s, x, y = best
    xi0, yi0 = int(max(0, x)), int(max(0, y))
    region = rgb[yi0:int(min(H, y + h)), xi0:int(min(W, x + w)), :3]
    mean = tuple(float(v) for v in region.reshape(-1, 3).mean(0)) + (1.0,) if region.size else (0, 0, 0, 1)
    return Spot(float(x), float(y), float(w), float(h), float(s), mean), m, f


def heatmap(m: np.ndarray, spot: Spot | None = None, f: float = 1.0) -> np.ndarray:
    """An RGB picture of the busyness map (calm = dark blue, busy = yellow) with the spot outlined."""
    a = np.clip(m, 0, 1)[:, :, None]
    lo, hi = np.array([0.05, 0.1, 0.3]), np.array([1.0, 0.85, 0.2])
    img = lo * (1 - a) + hi * a
    if spot is not None:
        x0, y0 = int(spot.x * f), int(spot.y * f)
        x1, y1 = min(img.shape[1] - 1, int((spot.x + spot.w) * f)), min(img.shape[0] - 1, int((spot.y + spot.h) * f))
        for t in range(2):
            img[max(0, y0 + t), x0:x1 + 1] = img[max(0, y1 - t), x0:x1 + 1] = (0.2, 1.0, 0.4)
            img[y0:y1 + 1, max(0, x0 + t)] = img[y0:y1 + 1, max(0, x1 - t)] = (0.2, 1.0, 0.4)
    return img.astype(np.float32)


def ink_bounds(items: tuple, reg: FontRegistry | None = None, max_side: int = 1024):
    """(x0, y0, x1, y1) of what items actually draw (letters, not their text boxes), or None."""
    reg = reg or registry()
    b = sc.content_bounds(items, reg)
    if b is None:
        return None
    # shadows, glows and strokes reach past the items' boxes
    pad = 4.0 + max((sc.effect_reach(it.style.effects) + sc.stroke_reach(it) for it in items), default=0.0)
    w, h = b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad
    s = min(1.0, max_side / max(w, h))
    part = sc.Scene(max(1, math.ceil(w)), max(1, math.ceil(h)),
                    items=(sc.GroupItem(items=items, dx=pad - b[0], dy=pad - b[1]),))
    a = sc.render(part, s, reg)[:, :, 3]
    ys, xs = np.where(a > 0.02)
    if not len(xs):
        return None
    return (b[0] - pad + xs.min() / s, b[1] - pad + ys.min() / s, b[0] - pad + (xs.max() + 1) / s,
            b[1] - pad + (ys.max() + 1) / s)


# ---- text-only and text-free renders ----


def _map_items(items: tuple, fn, counter: list) -> tuple:
    """Rebuild items depth first (same order as template.walk), calling fn(item, k) on
    each text item with its index k and fn(item, None) on other leaves."""
    out = []
    for it in items:
        if isinstance(it, sc.GroupItem):
            out.append(replace(it, items=_map_items(it.items, fn, counter)))
        elif isinstance(it, sc.LayoutItem):
            out.append(replace(it, parts=tuple(_map_items(p, fn, counter) for p in it.parts)))
        elif isinstance(it, sc.TextItem):
            k = counter[0]
            counter[0] += 1
            out.append(fn(it, k))
        else:
            out.append(fn(it, None))
    return tuple(out)


def text_items(items: tuple) -> list:
    found = []
    _map_items(items, lambda it, k: found.append(it) or it if k is not None else it, [0])
    return found


def _invisible(it):
    return sc.with_style(it, opacity=0.0)


def without_text(scene: sc.Scene) -> sc.Scene:
    """Everything except the text (text and its effects become invisible; layout unchanged)."""
    return replace(scene, items=_map_items(scene.items, lambda it, k: _invisible(it) if k is not None else it, [0]))


def only_text(scene: sc.Scene, index: int) -> sc.Scene:
    """Only text item ``index`` (its glyphs, no effects) on a transparent canvas."""
    def fn(it, k):
        if k == index:
            return replace(sc.with_style(it, effects=(), opacity=1.0, blend="normal"), fill=None,
                           spec=replace(it.spec, color=(1.0, 1.0, 1.0, 1.0)))
        return _invisible(it)

    return replace(scene, background=(0.0, 0.0, 0.0, 0.0), items=_map_items(scene.items, fn, [0]))


def _glyph_mask(scene, k, scale, reg):
    a = sc.render(only_text(scene, k), scale, reg)[:, :, 3]
    return a > 0.5


def _dilate(mask: np.ndarray, r: int) -> np.ndarray:
    """Grow a boolean mask by r pixels (box), via an integral image."""
    if r <= 0:
        return mask
    ii = _integral(mask.astype(np.float32))
    h, w = mask.shape
    ys, xs = np.arange(h), np.arange(w)
    y0, y1 = np.clip(ys - r, 0, h), np.clip(ys + r + 1, 0, h)
    x0, x1 = np.clip(xs - r, 0, w), np.clip(xs + r + 1, 0, w)
    s = ii[y1][:, x1] - ii[y0][:, x1] - ii[y1][:, x0] + ii[y0][:, x0]
    return s > 0


# ---- readability ----


def _lin(c):
    c = np.asarray(c, np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lum(rgb: np.ndarray) -> np.ndarray:
    l = _lin(rgb)
    return 0.2126 * l[..., 0] + 0.7152 * l[..., 1] + 0.0722 * l[..., 2]


def ratios(text_lum: float, bg_rgb: np.ndarray) -> np.ndarray:
    lb = lum(bg_rgb)
    hi, lo = np.maximum(lb, text_lum), np.minimum(lb, text_lum)
    return (hi + 0.05) / (lo + 0.05)


def text_color(it: sc.TextItem) -> tuple:
    """The text's colour; for gradient text, the average of its stops."""
    if it.fill is not None:
        cs = np.array([c[:3] for _, c in it.fill.stops], np.float64)
        return tuple(cs.mean(0)) + (1.0,)
    return it.spec.color


def is_large(spec) -> bool:
    """WCAG large text: 18 pt (24 px), or 14 pt (18.67 px) bold."""
    return spec.size >= 24 or (spec.size >= 18.66 and spec.weight >= 700)


LEVELS = {"AA": (4.5, 3.0), "AAA": (7.0, 4.5)}


@dataclass
class TextCheck:
    index: int
    name: str
    text: str
    size: float
    large: bool
    worst: float  # 10th percentile contrast over the pixels behind the glyphs
    median: float
    need: float
    effects: bool  # has a shadow / glow / outline (helps; not counted)
    bounds: tuple  # x0, y0, x1, y1 in canvas pixels

    @property
    def ok(self) -> bool:
        return self.worst >= self.need

    def line(self) -> str:
        label = self.name or (self.text[:28] + ("…" if len(self.text) > 28 else ""))
        flag = "ok  " if self.ok else "FAIL"
        extra = " (has shadow/outline: check by eye)" if self.effects and not self.ok else ""
        return (f"{flag} {label!r}: {self.worst:.2f}:1 worst, {self.median:.2f}:1 typical, needs {self.need:g}:1"
                f" ({'large' if self.large else 'body'} text){extra}")


def _bg(scene, scale, reg):
    bg = sc.render(without_text(scene), scale, reg)
    a = bg[:, :, 3:4]
    return bg[:, :, :3] * a  # transparent canvas counts as black


def readability(scene: sc.Scene, level: str = "AA", scale: float | None = None,
                reg: FontRegistry | None = None) -> list[TextCheck]:
    reg = reg or registry()
    scale = scale or min(1.0, 1024 / max(scene.width, scene.height))
    bg = _bg(scene, scale, reg)
    normal, large = LEVELS[level]
    out = []
    for k, it in enumerate(text_items(scene.items)):
        mask = _glyph_mask(scene, k, scale, reg)
        if not mask.any():
            continue
        behind = _dilate(mask, max(1, round(2 * scale)))
        r = ratios(lum(np.array(text_color(it)[:3])), bg[behind])
        ys, xs = np.where(mask)
        b = (xs.min() / scale, ys.min() / scale, (xs.max() + 1) / scale, (ys.max() + 1) / scale)
        lg = is_large(it.spec)
        has_fx = any(isinstance(e, (sc.Shadow, sc.Glow, sc.Outline)) for e in it.style.effects)
        out.append(TextCheck(k, it.name, it.spec.text, it.spec.size, lg, float(np.percentile(r, 10)),
                             float(np.median(r)), large if lg else normal, has_fx, b))
    return out


def overlay(scene: sc.Scene, checks: list[TextCheck], scale: float = 0.5, reg=None) -> np.ndarray:
    """The design with a green (pass) or red (fail) frame around each text."""
    s = scene
    for c in checks:
        x0, y0, x1, y1 = c.bounds
        colr = (0.15, 0.85, 0.35, 1.0) if c.ok else (1.0, 0.15, 0.15, 1.0)
        s = s.add(sc.ShapeItem("rectangle", x0 - 6, y0 - 6, x1 - x0 + 12, y1 - y0 + 12, None, colr,
                               max(2.0, 3 / scale)))
    return sc.render(s, scale, reg)


# ---- scrims ----

SCRIM_STYLES = ["gradient band", "box", "soft glow"]


def needed_alpha(text_rgb, bg: np.ndarray, scrim_rgb, target: float, max_alpha: float = 0.9) -> tuple[float, float]:
    """The smallest scrim opacity making the 10th-percentile contrast reach ``target``
    (bisection; compositing in sRGB as skia does). Returns (alpha, achieved ratio)."""
    tl = lum(np.array(text_rgb[:3]))
    sr = np.array(scrim_rgb[:3])

    def worst(a):
        return float(np.percentile(ratios(tl, bg * (1 - a) + sr * a), 10))

    if worst(0.0) >= target:
        return 0.0, worst(0.0)
    if worst(max_alpha) < target:
        return max_alpha, worst(max_alpha)
    lo, hi = 0.0, max_alpha
    for _ in range(18):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if worst(mid) < target else (lo, mid)
    return hi, worst(hi)


def scrim_for(scene: sc.Scene, target_index: int = -1, style: str = "gradient band", color: str = "auto",
              target: float = 4.5, max_alpha: float = 0.85, padding: float = 32.0, radius: float = 16.0,
              reg: FontRegistry | None = None) -> tuple[sc.Scene, str]:
    """Insert a scrim just under top-level item ``target_index`` (default the last), only as
    strong as needed for every text inside it to reach ``target`` contrast."""
    reg = reg or registry()
    if not scene.items:
        raise ValueError("the scene is empty")
    ti = target_index % len(scene.items)
    target_item = scene.items[ti]
    texts_before = len(text_items(scene.items[:ti]))
    inner = text_items((target_item,))
    if not inner:
        raise ValueError("the target item has no text")
    scale = min(1.0, 1024 / max(scene.width, scene.height))
    bg = _bg(scene, scale, reg)
    masks = [_glyph_mask(scene, texts_before + j, scale, reg) for j in range(len(inner))]
    union = np.logical_or.reduce(masks)
    if not union.any():
        raise ValueError("the target's text is not on the canvas")
    ys, xs = np.where(union)
    x0, y0, x1, y1 = xs.min() / scale, ys.min() / scale, (xs.max() + 1) / scale, (ys.max() + 1) / scale
    light = np.mean([lum(np.array(text_color(t)[:3])) for t in inner]) > 0.18
    scrim = col.parse_color(color) if color.strip().lower() != "auto" else (
        (0.0, 0.0, 0.0, 1.0) if light else (1.0, 1.0, 1.0, 1.0))
    alpha, before = 0.0, math.inf
    for t, m in zip(inner, masks):
        behind = bg[_dilate(m, max(1, round(2 * scale)))]
        tl = lum(np.array(text_color(t)[:3]))
        before = min(before, float(np.percentile(ratios(tl, behind), 10)))
        alpha = max(alpha, needed_alpha(text_color(t), behind, scrim, target, max_alpha)[0])
    if alpha <= 0.0:
        return scene, f"no scrim needed: worst contrast already {before:.2f}:1"
    # A soft or faded edge lightens the scrim right next to the text: allow for it.
    alpha = min(max_alpha, alpha * (1.15 if style != "box" else 1.0))
    c = scrim[:3]
    W, H = scene.width, scene.height
    if style == "box":
        item = sc.ShapeItem("rectangle", x0 - padding, y0 - padding, x1 - x0 + 2 * padding, y1 - y0 + 2 * padding,
                            c + (alpha,), radius=radius, name="scrim")
    elif style == "soft glow":
        item = sc.with_style(sc.ShapeItem("rectangle", x0 - padding, y0 - padding, x1 - x0 + 2 * padding,
                                          y1 - y0 + 2 * padding, c + (alpha,), radius=padding, name="scrim"),
                             effects=(sc.Blur(padding),))
    else:  # gradient band from the nearer edge (top or bottom), solid behind the text
        lower = (y0 + y1) / 2 > H / 2
        fade = max(padding * 3, (y1 - y0) * 0.75)
        if lower:
            top = max(0.0, y0 - padding - fade)
            solid = (y0 - padding - top) / max(1.0, H - top)
            stops = ((0.0, c + (0.0,)), (max(0.0, min(1.0, solid)), c + (alpha,)), (1.0, c + (alpha,)))
            item = sc.ShapeItem("rectangle", 0, top, W, H - top, sc.Gradient("linear", stops, 90.0), name="scrim")
        else:
            bottom = min(float(H), y1 + padding + fade)
            solid = (y1 + padding) / max(1.0, bottom)
            stops = ((0.0, c + (alpha,)), (max(0.0, min(1.0, solid)), c + (alpha,)), (1.0, c + (0.0,)))
            item = sc.ShapeItem("rectangle", 0, 0, W, bottom, sc.Gradient("linear", stops, 90.0), name="scrim")
    items = scene.items[:ti] + (item,) + scene.items[ti:]
    out = replace(scene, items=items)
    after = min(c.worst for c in readability(out, reg=reg)[texts_before:texts_before + len(inner)])
    return out, (f"{style} scrim {col.to_hex(c)} at {alpha * 100:.0f}% opacity: worst contrast "
                 f"{before:.2f}:1 -> {after:.2f}:1 (target {target:g}:1)")
