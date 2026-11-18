"""Print PDFs in CMYK.

The design is first written by skia's PDF backend (vector: text stays text, fonts
embedded, exactly as the preview). That PDF is then converted to CMYK with pypdf:

- colour operators (``rg``/``RG``, DeviceRGB ``sc``/``scn``) become ``k``/``K`` with
  values from the CMYK converter (exact overrides first);
- gradients (shadings, type 2 and stitched type 3 functions) get CMYK end colours;
- RGB images (photos, and effects skia rasterised) go through the ICC profile;
- transparency groups blend in DeviceCMYK. Soft masks stay as they are.

"flatten" mode renders the whole design to one image first (at ``raster_dpi``),
which some print shops prefer and which keeps blend modes looking as in RGB.

Then the page boxes: TrimBox / BleedBox, optional crop marks in registration
colour, and an OutputIntent carrying the CMYK profile.
"""

from __future__ import annotations

import os
import tempfile
from collections import Counter
from pathlib import Path

import numpy as np

from . import scene as sc
from .cmyk import CMYK
from .fonts import FontRegistry, registry

MODES = ["vector", "flatten"]
BLEED_MODES = ["canvas includes bleed", "extend background", "none"]
MARK_GAP = 4.5  # pt between the bleed edge and a crop mark
MARK_LEN = 18.0  # pt


class _Converter:
    def __init__(self, cm: CMYK):
        self.cm = cm
        self.seen: set = set()
        self.stats = Counter()

    def _once(self, obj) -> bool:
        ref = getattr(obj, "indirect_reference", None)
        key = (ref.idnum, ref.generation) if ref is not None else id(obj)
        if key in self.seen:
            return False
        self.seen.add(key)
        return True

    def _cmyk_operands(self, operands):
        from pypdf.generic import FloatObject

        rgb = [float(v) for v in operands]
        return [FloatObject(round(v, 4)) for v in self.cm.color(rgb)]

    def operations(self, ops: list) -> list:
        from pypdf.generic import NameObject

        out, fill_rgb, stroke_rgb = [], False, False
        for operands, op in ops:
            if op in (b"rg", b"RG") and len(operands) == 3:
                operands, op = self._cmyk_operands(operands), (b"k" if op == b"rg" else b"K")
                self.stats["colours"] += 1
            elif op in (b"cs", b"CS") and operands:
                rgb = operands[0] == "/DeviceRGB"
                if op == b"cs":
                    fill_rgb = rgb
                else:
                    stroke_rgb = rgb
                if rgb:
                    operands = [NameObject("/DeviceCMYK")]
            elif op in (b"sc", b"scn") and fill_rgb and len(operands) == 3:
                operands = self._cmyk_operands(operands)
                self.stats["colours"] += 1
            elif op in (b"SC", b"SCN") and stroke_rgb and len(operands) == 3:
                operands = self._cmyk_operands(operands)
                self.stats["colours"] += 1
            out.append((operands, op))
        return out

    def content(self, stream, pdf):
        from pypdf.generic import ContentStream

        cs = ContentStream(stream, pdf)
        cs.operations = self.operations(cs.operations)
        stream.set_data(cs.get_data())

    def group(self, obj):
        from pypdf.generic import NameObject

        g = obj.get("/Group")
        if g is not None:
            g = g.get_object()
            if g.get("/CS") == "/DeviceRGB":
                g[NameObject("/CS")] = NameObject("/DeviceCMYK")

    def function(self, f):
        from pypdf.generic import ArrayObject, FloatObject, NameObject

        f = f.get_object()
        if not self._once(f):
            return
        ft = int(f.get("/FunctionType", -1))
        if ft == 2:
            for key in ("/C0", "/C1"):
                vals = [float(v) for v in f.get(key, [0, 0, 0] if key == "/C0" else [1, 1, 1])]
                if len(vals) == 3:
                    f[NameObject(key)] = ArrayObject([FloatObject(round(v, 4)) for v in self.cm.color(vals)])
            self.stats["gradient stops"] += 2
        elif ft == 3:
            for sub in f["/Functions"]:
                self.function(sub)
        else:
            raise ValueError(f"cannot convert a type {ft} PDF function to CMYK; use flatten mode")

    def shading(self, sh):
        from pypdf.generic import ArrayObject, FloatObject, NameObject

        sh = sh.get_object()
        if not self._once(sh):
            return
        if sh.get("/ColorSpace") != "/DeviceRGB":
            return
        sh[NameObject("/ColorSpace")] = NameObject("/DeviceCMYK")
        fn = sh.get("/Function")
        if isinstance(fn, ArrayObject) or (fn is not None and isinstance(fn.get_object(), ArrayObject)):
            raise ValueError("cannot convert per-channel PDF functions to CMYK; use flatten mode")
        if fn is not None:
            self.function(fn)
        if "/Background" in sh:
            bg = [float(v) for v in sh["/Background"]]
            sh[NameObject("/Background")] = ArrayObject([FloatObject(v) for v in self.cm.color(bg)])

    def image(self, img):
        from pypdf.generic import NameObject

        if img.get("/ColorSpace") != "/DeviceRGB" or int(img.get("/BitsPerComponent", 8)) != 8:
            if img.get("/ColorSpace") not in ("/DeviceGray", "/DeviceCMYK", None):
                self.stats["images left as they were"] += 1
            return
        w, h = int(img["/Width"]), int(img["/Height"])
        arr = np.frombuffer(img.get_data(), np.uint8)[: w * h * 3].reshape(h, w, 3)
        cmyk = self.cm.image(arr, exact=False)  # exact values are for vector colours only
        for key in ("/DecodeParms", "/Decode"):
            if key in img:
                del img[key]
        img[NameObject("/Filter")] = NameObject("/FlateDecode")
        img[NameObject("/ColorSpace")] = NameObject("/DeviceCMYK")
        img.set_data(cmyk.tobytes())
        self.stats["images"] += 1

    def resources(self, res, pdf):
        if res is None:
            return
        res = res.get_object()
        for x in (res.get("/XObject") or {}).values():
            x = x.get_object()
            if not self._once(x):
                continue
            if x.get("/Subtype") == "/Image":
                self.image(x)
            elif x.get("/Subtype") == "/Form":
                self.content(x, pdf)
                self.group(x)
                self.resources(x.get("/Resources"), pdf)
        for p in (res.get("/Pattern") or {}).values():
            p = p.get_object()
            if not self._once(p):
                continue
            if int(p.get("/PatternType", 0)) == 2:
                self.shading(p["/Shading"])
            else:
                self.content(p, pdf)
                self.resources(p.get("/Resources"), pdf)
        for s in (res.get("/Shading") or {}).values():
            self.shading(s)
        # Soft masks (/ExtGState /SMask /G) stay in RGB: they only carry transparency.

    def page(self, page, pdf):
        from pypdf.generic import ContentStream

        cs = ContentStream(page.get_contents(), pdf)
        cs.operations = self.operations(cs.operations)
        page.replace_contents(cs)
        self.group(page)
        self.resources(page.get("/Resources"), pdf)


def _box(x0, y0, x1, y1):
    from pypdf.generic import ArrayObject, FloatObject

    return ArrayObject([FloatObject(round(v, 3)) for v in (x0, y0, x1, y1)])


def _mark_ops(trim, bleed):
    """Crop marks in registration colour (100/100/100/100), outside the bleed."""
    from pypdf.generic import FloatObject

    x0, y0, x1, y1 = trim
    d = bleed + MARK_GAP
    lines = []
    for x, sx in ((x0, -1), (x1, 1)):
        for y, sy in ((y0, -1), (y1, 1)):
            lines.append(((x + sx * d, y), (x + sx * (d + MARK_LEN), y)))  # horizontal, at the trim line
            lines.append(((x, y + sy * d), (x, y + sy * (d + MARK_LEN))))  # vertical
    f = lambda v: FloatObject(round(v, 3))  # noqa: E731
    ops = [([], b"q"), ([f(0.25)], b"w"), ([f(1), f(1), f(1), f(1)], b"K")]
    for (ax, ay), (bx, by) in lines:
        ops += [([f(ax), f(ay)], b"m"), ([f(bx), f(by)], b"l"), ([], b"S")]
    return ops + [([], b"Q")]


def _output_intent(writer, cm: CMYK):
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
                               TextStringObject)

    icc = DecodedStreamObject()
    icc.set_data(cm.icc)
    icc[NameObject("/N")] = NumberObject(4)
    oi = DictionaryObject({
        NameObject("/Type"): NameObject("/OutputIntent"),
        NameObject("/S"): NameObject("/GTS_PDFX"),
        NameObject("/OutputConditionIdentifier"): TextStringObject(cm.name),
        NameObject("/Info"): TextStringObject(cm.name),
        NameObject("/DestOutputProfile"): writer._add_object(icc),
    })
    writer._root_object[NameObject("/OutputIntents")] = ArrayObject([writer._add_object(oi)])


def _background_cmyk(scene, cm):
    bg = scene.background
    if isinstance(bg, sc.Gradient):
        bg = bg.stops[0][1]
    return cm.color(bg[:3]) if bg[3] > 0 else (0.0, 0.0, 0.0, 0.0)


def print_pdf(scene: sc.Scene, path: str | Path, cm: CMYK, dpi: float = 300.0, mode: str = "vector",
              bleed: float = 0.125, bleed_mode: str = "canvas includes bleed", marks: bool = False,
              output_intent: bool = True, raster_dpi: float = 300.0, title: str = "",
              reg: FontRegistry | None = None) -> dict:
    """Write a CMYK print PDF. ``dpi`` is canvas pixels per inch; ``bleed`` is in inches.
    Returns facts for a report (sizes in inches, what was converted)."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ContentStream, FloatObject, NameObject

    reg = reg or registry()
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if bleed_mode not in BLEED_MODES:
        raise ValueError(f"bleed_mode must be one of {BLEED_MODES}")
    src = scene
    if mode == "flatten":
        s = raster_dpi / dpi
        rgba = sc.render(scene, s, reg)
        rgb = rgba[:, :, :3] * rgba[:, :, 3:4] + (1 - rgba[:, :, 3:4])  # transparency prints as paper
        img = np.concatenate([rgb, np.ones(rgb.shape[:2] + (1,), np.float32)], axis=2)
        src = sc.Scene(scene.width, scene.height, (1.0, 1.0, 1.0, 1.0)).add(
            sc.ImageItem(img, 0, 0, scene.width, scene.height, "stretch"))
    fd, tmp = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        sc.to_pdf(src, tmp, dpi, reg)
        writer = PdfWriter(clone_from=PdfReader(tmp))
    finally:
        os.unlink(tmp)
    conv = _Converter(cm)
    page = writer.pages[0]
    conv.page(page, writer)

    k = 72.0 / dpi
    W, H = scene.width * k, scene.height * k
    b = max(0.0, bleed) * 72.0 if bleed_mode != "none" else 0.0
    if bleed_mode == "canvas includes bleed":
        trim, bleed_box = (b, b, W - b, H - b), (0.0, 0.0, W, H)
        if trim[2] <= trim[0] or trim[3] <= trim[1]:
            raise ValueError("the bleed is larger than half the canvas")
    else:
        trim, bleed_box = (0.0, 0.0, W, H), (-b, -b, W + b, H + b)
    slug = (b + MARK_GAP + MARK_LEN + 2.0) if marks else 0.0
    media = (trim[0] - slug, trim[1] - slug, trim[2] + slug, trim[3] + slug) if marks else bleed_box

    # Wrap the page in q/Q (skia's first op flips the y axis), then add background bleed and marks.
    cs = ContentStream(page.get_contents(), writer)
    ops = [([], b"q")] + cs.operations + [([], b"Q")]
    if bleed_mode == "extend background" and b > 0:
        c = [FloatObject(round(v, 4)) for v in _background_cmyk(scene, cm)]
        x0, y0, x1, y1 = bleed_box
        ops = [([], b"q"), (c, b"k"), ([FloatObject(v) for v in (x0, y0, x1 - x0, y1 - y0)], b"re"), ([], b"f"),
               ([], b"Q")] + ops
    if marks:
        ops += _mark_ops(trim, b)
    cs.operations = ops
    page.replace_contents(cs)
    page[NameObject("/MediaBox")] = _box(*media)
    page[NameObject("/CropBox")] = _box(*media)
    page[NameObject("/BleedBox")] = _box(*bleed_box)
    page[NameObject("/TrimBox")] = _box(*trim)
    if output_intent and cm.calibrated:
        _output_intent(writer, cm)
    writer.add_metadata({"/Title": title or Path(path).stem, "/Creator": "CrateNode-Comfy"})
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        writer.write(f)
    return {"trim_in": ((trim[2] - trim[0]) / 72, (trim[3] - trim[1]) / 72), "bleed_in": b / 72,
            "media_in": ((media[2] - media[0]) / 72, (media[3] - media[1]) / 72), "profile": cm.name,
            "calibrated": cm.calibrated, "mode": mode, "converted": dict(conv.stats)}
