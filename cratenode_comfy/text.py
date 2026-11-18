"""Text boxes: shape, wrap, align, anchor and auto-fit text with skia's Paragraph.

Markup: ``*words*`` switches to the bold weight (``bold_weight``); ``\\*`` is a
literal star. Everything else is plain text; ``\\n`` breaks a line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

import skia

from .fonts import FontRegistry, registry

ALIGNS = ["left", "center", "right"]
VALIGNS = ["top", "middle", "bottom"]
CASES = ["as typed", "UPPER", "lower", "Title"]


@dataclass(frozen=True)
class TextSpec:
    text: str
    family: str = "Inter"
    weight: int = 400
    bold_weight: int = 700
    italic: bool = False
    size: float = 64.0
    color: tuple[float, float, float, float] = (1.0, 1.0, 1.0, 1.0)
    line_height: float = 1.2
    letter_spacing: float = 0.0
    case: str = "as typed"
    x: float = 0.0
    y: float = 0.0
    width: float = 1000.0
    height: float = 0.0  # 0: as tall as the text
    align: str = "left"
    valign: str = "top"
    auto_fit: bool = False
    min_size: float = 12.0


@dataclass
class Laid:
    """A laid-out text box, ready to paint at (x, y)."""

    paragraph: skia.textlayout.Paragraph
    x: float
    y: float
    width: float
    height: float  # content height
    size: float  # font size used (smaller when auto-fit shrank it)

    def bounds(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)


def apply_case(s: str, case: str) -> str:
    if case == "UPPER":
        return s.upper()
    if case == "lower":
        return s.lower()
    if case == "Title":
        return re.sub(r"(^|\s)(\w)", lambda m: m.group(1) + m.group(2).upper(), s)
    return s


def spans(text: str) -> list[tuple[str, bool]]:
    """Split ``*bold*`` markup into (text, bold) runs; an unpaired star is literal."""
    out: list[tuple[str, bool]] = []
    buf, bold, i = "", False, 0
    stars = [m.start() for m in re.finditer(r"(?<!\\)\*", text)]
    usable = set(stars[: len(stars) // 2 * 2])
    while i < len(text):
        c = text[i]
        if c == "\\" and i + 1 < len(text) and text[i + 1] in "*\\":
            buf += text[i + 1]
            i += 2
            continue
        if c == "*" and i in usable:
            if buf:
                out.append((buf, bold))
            buf, bold = "", not bold
        else:
            buf += c
        i += 1
    if buf:
        out.append((buf, bold))
    return out


def _paragraph(spec: TextSpec, size: float, reg: FontRegistry, wrap_width: float) -> skia.textlayout.Paragraph:
    runs = spans(spec.text)
    weights = {spec.weight} | ({spec.bold_weight} if any(b for _, b in runs) else set())
    faces = [reg.require(spec.family, w, spec.italic) for w in sorted(weights)]
    collection = reg.font_collection(faces)
    pstyle = skia.textlayout.ParagraphStyle()
    pstyle.setTextAlign(
        {"center": skia.textlayout.TextAlign.kCenter, "right": skia.textlayout.TextAlign.kRight}.get(
            spec.align, skia.textlayout.TextAlign.kLeft
        )
    )
    builder = skia.textlayout.ParagraphBuilder.make(pstyle, collection, skia.Unicode())
    r, g, b, a = spec.color
    paint = skia.Paint(Color=skia.Color4f(r, g, b, a), AntiAlias=True)
    scale = size / max(spec.size, 1.0)
    for chunk, bold in runs:
        ts = skia.textlayout.TextStyle()
        ts.setFontFamilies([faces[0].family])
        slant = skia.FontStyle.kItalic_Slant if spec.italic else skia.FontStyle.kUpright_Slant
        ts.setFontStyle(skia.FontStyle(spec.bold_weight if bold else spec.weight, skia.FontStyle.kNormal_Width, slant))
        ts.setFontSize(size)
        ts.setHeightOverride(True)
        ts.setHeight(spec.line_height)
        ts.setLetterSpacing(spec.letter_spacing * scale)
        ts.setForegroundPaint(paint)
        builder.pushStyle(ts)
        builder.addText(apply_case(chunk, spec.case))
        builder.pop()
    p = builder.Build()
    p.layout(wrap_width)
    return p


def layout(spec: TextSpec, reg: FontRegistry | None = None) -> Laid:
    reg = reg or registry()
    wrap = spec.width if spec.width > 0 else 100000.0

    def fits(p: skia.textlayout.Paragraph) -> bool:
        tall_ok = spec.height <= 0 or p.Height <= spec.height + 0.5
        wide_ok = spec.width <= 0 or p.LongestLine <= spec.width + 0.5
        return tall_ok and wide_ok and not p.ExceedMaxLines

    size = spec.size
    p = _paragraph(spec, size, reg, wrap)
    if spec.auto_fit and not fits(p):
        lo, hi = min(spec.min_size, spec.size), spec.size
        best = None
        for _ in range(16):
            mid = (lo + hi) / 2
            q = _paragraph(spec, mid, reg, wrap)
            if fits(q):
                lo, best = mid, (mid, q)
            else:
                hi = mid
            if hi - lo < 0.25:
                break
        size, p = best if best else (lo, _paragraph(spec, lo, reg, wrap))
    width = spec.width if spec.width > 0 else p.LongestLine
    if spec.width <= 0:
        p.layout(width + 1)
    content_h = p.Height
    y = spec.y
    if spec.height > 0:
        y += {"middle": (spec.height - content_h) / 2, "bottom": spec.height - content_h}.get(spec.valign, 0.0)
    return Laid(p, spec.x, y, width, content_h, size)


def with_size(spec: TextSpec, **changes) -> TextSpec:
    return replace(spec, **changes)
