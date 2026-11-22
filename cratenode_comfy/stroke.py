"""Stroke styles for shapes: alignment, dashes, caps and joins, a second (double) line,
and drawing the stroke behind the fill.

A style is written as short text, so it fits in one widget, a saved workflow and the API:

    align=inside; dash=3,2; offset=0; cap=round; join=miter; double=6,2,inside; behind=1

Every key is optional; an empty style is the plain centred stroke with round ends and
corners. Lengths are in multiples of the stroke width, so a style keeps its look at any
width: dash lengths and ``offset``, and ``double=gap,width[,inside|outside]`` (the gap
and the second line's width).

Strokes are turned into outlines (skia path ops), so inside/outside strokes and double
lines stay vector shapes in PDF output and need no layers.
"""

from __future__ import annotations

from dataclasses import dataclass

import skia

ALIGNS = ("center", "inside", "outside")
CAPS = ("round", "butt", "square")
JOINS = ("round", "miter", "bevel")
SIDES = ("inside", "outside")

# Presets the stroke editor offers (name -> style text). Kept here so tests check them.
PRESETS = {
    "Solid": "",
    "Dashed": "dash=3,2; cap=butt",
    "Long dash": "dash=6,3; cap=butt",
    "Short dash": "dash=1.5,1.5; cap=butt",
    "Dotted": "dash=0,2; cap=round",
    "Dash dot": "dash=4,2,0,2; cap=round",
    "Double": "double=0.75,1,inside",
    "Thick + thin": "double=0.5,0.3,inside",
    "Thin + thick": "double=0.6,2,inside",
    "Outer ring": "double=1,0.4,outside",
    "Inside border": "align=inside; join=miter",
    "Outside border": "align=outside; join=miter",
    "Sharp corners": "join=miter; cap=square",
    "Behind the fill": "behind=1",
}


@dataclass(frozen=True)
class StrokeStyle:
    align: str = "center"
    dash: tuple = ()  # on, off, on, off ... in stroke widths; () = solid
    offset: float = 0.0  # dash phase, in stroke widths
    cap: str = "round"
    join: str = "round"
    double_gap: float = 0.0  # space between the lines, in stroke widths
    double_width: float = 0.0  # second line's width, in stroke widths; 0 = no second line
    double_side: str = "inside"
    behind: bool = False  # draw the stroke under the fill


def _num(key: str, text: str) -> float:
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"stroke_style {key}: {text!r} is not a number") from None


def parse(text: str) -> StrokeStyle | None:
    """The style for ``text``; None for an empty style (the plain stroke)."""
    text = (text or "").strip()
    if not text:
        return None
    kw: dict = {}
    for part in text.replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        key, sep, value = part.partition("=")
        key, value = key.strip().lower(), value.strip().lower()
        if not sep:
            raise ValueError(f"stroke_style: expected key=value, got {part!r}")
        if key == "align":
            if value not in ALIGNS:
                raise ValueError(f"stroke_style align must be one of {', '.join(ALIGNS)}")
            kw["align"] = value
        elif key == "dash":
            nums = tuple(_num(key, v) for v in value.replace(" ", ",").split(",") if v)
            if nums and (len(nums) % 2 or any(n < 0 for n in nums) or sum(nums) <= 0):
                raise ValueError("stroke_style dash needs pairs of on,off lengths (in stroke widths), e.g. 3,2")
            kw["dash"] = nums
        elif key == "offset":
            kw["offset"] = _num(key, value)
        elif key == "cap":
            if value not in CAPS:
                raise ValueError(f"stroke_style cap must be one of {', '.join(CAPS)}")
            kw["cap"] = value
        elif key == "join":
            if value not in JOINS:
                raise ValueError(f"stroke_style join must be one of {', '.join(JOINS)}")
            kw["join"] = value
        elif key == "double":
            bits = [b.strip() for b in value.split(",") if b.strip()]
            if len(bits) not in (2, 3):
                raise ValueError("stroke_style double is gap,width[,inside|outside] in stroke widths, e.g. 0.75,1")
            kw["double_gap"], kw["double_width"] = max(0.0, _num(key, bits[0])), max(0.0, _num(key, bits[1]))
            if len(bits) == 3:
                if bits[2] not in SIDES:
                    raise ValueError("stroke_style double side must be inside or outside")
                kw["double_side"] = bits[2]
        elif key == "behind":
            kw["behind"] = value in ("1", "true", "yes", "on")
        else:
            raise ValueError(f"stroke_style: unknown key {key!r} (align, dash, offset, cap, join, double, behind)")
    return StrokeStyle(**kw)


def to_text(st: StrokeStyle | None) -> str:
    """The text form of a style (only what differs from the plain stroke)."""
    if st is None:
        return ""
    d = StrokeStyle()
    out = []
    if st.align != d.align:
        out.append(f"align={st.align}")
    if st.dash:
        out.append("dash=" + ",".join(f"{n:g}" for n in st.dash))
    if st.offset:
        out.append(f"offset={st.offset:g}")
    if st.cap != d.cap:
        out.append(f"cap={st.cap}")
    if st.join != d.join:
        out.append(f"join={st.join}")
    if st.double_width > 0:
        out.append(f"double={st.double_gap:g},{st.double_width:g},{st.double_side}")
    if st.behind:
        out.append("behind=1")
    return "; ".join(out)


# ---- geometry ----

_CAP = {"round": skia.Paint.kRound_Cap, "butt": skia.Paint.kButt_Cap, "square": skia.Paint.kSquare_Cap}
_JOIN = {"round": skia.Paint.kRound_Join, "miter": skia.Paint.kMiter_Join, "bevel": skia.Paint.kBevel_Join}


def _outline(path: skia.Path, width: float, st: StrokeStyle, unit: float, dashed: bool) -> skia.Path:
    """The filled outline of ``path`` stroked at ``width`` (dashes measured in ``unit``)."""
    paint = skia.Paint(AntiAlias=True, Style=skia.Paint.kStroke_Style, StrokeWidth=max(0.01, width),
                       StrokeCap=_CAP[st.cap], StrokeJoin=_JOIN[st.join], StrokeMiter=8.0)
    if dashed and st.dash:
        # a 0-length dash with a round or square cap is a dot
        iv = [max(0.001, n * unit) for n in st.dash]
        paint.setPathEffect(skia.DashPathEffect.Make(iv, st.offset * unit))
    out = skia.Path()
    paint.getFillPath(path, out)
    return out


def _band(path: skia.Path, closed: bool, lo: float, hi: float, st: StrokeStyle, unit: float) -> skia.Path:
    """Everything between signed distances lo..hi from the path (negative = inside)."""
    if hi <= lo:
        return skia.Path()
    if abs(lo + hi) < 1e-6:  # centred on the path: a plain stroke
        return _outline(path, hi - lo, st, unit, True)
    if not closed:  # an open path (a line) has no inside: the band runs on both sides
        far, near = max(abs(lo), abs(hi)), (0.0 if lo < 0 < hi else min(abs(lo), abs(hi)))
        out = _outline(path, 2 * far, st, unit, True)
        if near > 0:
            out = skia.Op(out, _outline(path, 2 * near, st, unit, False), skia.PathOp.kDifference_PathOp)
        return out
    out = skia.Path()
    if lo < 0:  # the inside part
        p, q = -lo, max(0.0, -hi)
        part = skia.Op(_outline(path, 2 * p, st, unit, True), path, skia.PathOp.kIntersect_PathOp)
        if q > 0:
            part = skia.Op(part, _outline(path, 2 * q, st, unit, False), skia.PathOp.kDifference_PathOp)
        out = skia.Op(out, part, skia.PathOp.kUnion_PathOp)
    if hi > 0:  # the outside part
        p, q = hi, max(0.0, lo)
        part = skia.Op(_outline(path, 2 * p, st, unit, True), path, skia.PathOp.kDifference_PathOp)
        if q > 0:
            part = skia.Op(part, _outline(path, 2 * q, st, unit, False), skia.PathOp.kDifference_PathOp)
        out = skia.Op(out, part, skia.PathOp.kUnion_PathOp)
    return out


def _main(st: StrokeStyle, width: float, closed: bool) -> tuple[float, float]:
    align = st.align if closed else "center"
    return {"center": (-width / 2, width / 2), "inside": (-width, 0.0), "outside": (0.0, width)}[align]


def outline(path: skia.Path, width: float, st: StrokeStyle | None, closed: bool = True) -> skia.Path:
    """The whole stroke (main line and any second line) as a filled path."""
    st = st or StrokeStyle()
    lo, hi = _main(st, width, closed)
    out = _band(path, closed, lo, hi, st, width)
    if st.double_width > 0:
        gap, w2 = st.double_gap * width, st.double_width * width
        if st.double_side == "outside" or not closed:
            b = (hi + gap, hi + gap + w2)
        else:
            b = (lo - gap - w2, lo - gap)
        out = skia.Op(out, _band(path, closed, b[0], b[1], st, width), skia.PathOp.kUnion_PathOp)
    return out


def reach(st: StrokeStyle | None, width: float) -> float:
    """How far the stroke can reach outside the shape's path (for crops and layers)."""
    if width <= 0:
        return 0.0
    st = st or StrokeStyle()
    far = {"center": width / 2, "inside": 0.0, "outside": width}[st.align]
    if st.double_width > 0:
        extra = (st.double_gap + st.double_width) * width
        if st.double_side == "outside":
            far += extra
        far = max(far, width / 2 + extra)  # a line's second line goes on both sides
    # miter corners poke out further
    return far * (4.0 if st.join == "miter" else 1.0) + (width if st.cap == "square" else 0.0)
