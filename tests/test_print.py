"""Print tests (no ComfyUI needed): CMYK conversion and exact values, and CMYK print
PDFs (operators, images, gradients, boxes, marks, output intent). Calibrated tests
use Windows' RSWOP.icm when it exists; no profile ships with the package.

    python -m unittest discover -s tests -v
"""

import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import cmyk, color as col, config, fonts, printpdf, scene as sc, text  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))
SYS = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "spool" / "drivers" / "color"
SWOP = SYS / "RSWOP.icm"
SRGB = SYS / "sRGB Color Space Profile.icm"
BRAND = (31 / 255, 111 / 255, 235 / 255)

try:
    import pypdf
except ImportError:  # pragma: no cover
    pypdf = None
try:
    import pypdfium2
except ImportError:
    pypdfium2 = None


class Uncalibrated(unittest.TestCase):
    def test_formula_and_overrides(self):
        cm = cmyk.CMYK()
        self.assertFalse(cm.calibrated)
        self.assertEqual(cm.color((1, 1, 1)), (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(cm.color((1, 0, 0)), (0.0, 1.0, 1.0, 0.0))
        self.assertEqual(cm.color((0, 0, 0)), (0.0, 0.0, 0.0, 1.0))
        cm = cmyk.CMYK(overrides=cmyk.parse_overrides("#1f6feb = 90 55 0 0 // brand blue"))
        self.assertEqual(cm.color(BRAND), (0.9, 0.55, 0.0, 0.0))
        img = np.zeros((2, 2, 3), np.uint8)
        img[0, 0] = (31, 111, 235)
        img[1, 1] = (32, 111, 235)  # one off: not exact, goes through the formula
        out = cm.image(img)
        np.testing.assert_array_equal(out[0, 0], np.round(np.array([0.9, 0.55, 0, 0]) * 255))
        self.assertNotEqual(tuple(out[1, 1]), tuple(out[0, 0]))
        plain = cm.image(img, exact=False)  # print images: the profile only, no seams
        np.testing.assert_array_equal(plain[0, 0], cmyk.CMYK(pure_black=False).image(img)[0, 0])

    def test_parse(self):
        pal = col.parse_palette("primary: #1f6feb")
        self.assertEqual(cmyk.parse_overrides("primary = 90/55/0/0\n\n#000000: 0, 0, 0, 100%", pal),
                         [(pal.get("primary"), (0.9, 0.55, 0.0, 0.0)), ((0.0, 0.0, 0.0, 1.0), (0, 0, 0, 1.0))])
        for bad in ("#fff = 1 2 3", "#ffffff = 120 0 0 0", "blue = 1 2 3 4"):
            with self.assertRaises((ValueError, KeyError)):
                cmyk.parse_overrides(bad)


@unittest.skipUnless(SWOP.is_file(), "no CMYK profile on this machine")
class Calibrated(unittest.TestCase):
    def test_profile(self):
        cm = cmyk.CMYK(SWOP)
        self.assertTrue(cm.calibrated)
        self.assertIn("Swop", cm.name)
        self.assertEqual(cm.color((1, 1, 1)), (0.0, 0.0, 0.0, 0.0), "paper white: no ink")
        self.assertEqual(cm.color((0, 0, 0)), (0.0, 0.0, 0.0, 1.0), "pure black: K only")
        mixed = cmyk.CMYK(SWOP, pure_black=False).color((0, 0, 0))
        self.assertNotEqual(mixed, (0.0, 0.0, 0.0, 1.0), "without the override black goes through the profile")
        self.assertGreater(mixed[3], 0.9)

    def test_proof(self):
        cm = cmyk.CMYK(SWOP)
        grey = np.full((1, 1, 3), 128, np.uint8)
        self.assertLess(np.abs(cm.proof(grey).astype(int) - 128).max(), 16, "mid grey survives (roughly)")
        green = np.array([[[0, 255, 0]]], np.uint8)
        d = np.linalg.norm(col.srgb_to_lab(green.reshape(-1, 3) / 255) - col.srgb_to_lab(cm.proof(green).reshape(-1, 3) / 255))
        self.assertGreater(d, 20, "screen green is far out of SWOP gamut")

    @unittest.skipUnless(SRGB.is_file(), "no sRGB profile file")
    def test_rejects_rgb_profiles(self):
        with self.assertRaisesRegex(ValueError, "not a CMYK profile"):
            cmyk.CMYK(SRGB)
        with self.assertRaises(FileNotFoundError):
            cmyk.CMYK(SYS / "missing.icc")


def design():
    photo = np.random.default_rng(0).random((60, 80, 4)).astype(np.float32)
    photo[..., 3] = 1
    grad = sc.Gradient("linear", ((0, (0.1, 0.2, 0.6, 1)), (0.5, (0.5, 0.5, 0.5, 1)), (1, (0.9, 0.3, 0.1, 1))), 45)
    s = sc.Scene(600, 400, grad)
    s = s.add(sc.ImageItem(photo, 20, 20, 160, 120, "fill"))
    s = s.add(sc.ShapeItem("rectangle", 200, 250, 200, 60, BRAND + (1.0,), stroke=(0, 0, 0, 1), stroke_width=4))
    s = s.add(sc.add_effect(sc.TextItem(text.TextSpec("Hello *print*", "Montserrat", 700, size=48,
                                                       color=(1, 1, 1, 1), x=200, y=60, width=380)), sc.Shadow()))
    return s.add(sc.with_style(sc.ShapeItem("ellipse", 20, 250, 120, 120, (0.2, 0.9, 0.5, 1)), opacity=0.5))


def streams(reader):
    """Every content stream (page and forms, recursively) as text."""
    out, seen = [], set()

    def res(r):
        if r is None:
            return
        r = r.get_object()
        for x in (r.get("/XObject") or {}).values():
            o = x.get_object()
            if id(o) in seen:
                continue
            seen.add(id(o))
            if o.get("/Subtype") == "/Form":
                out.append(o.get_data().decode("latin-1"))
                res(o.get("/Resources"))

    pg = reader.pages[0]
    out.append(pg.get_contents().get_data().decode("latin-1"))
    res(pg.get("/Resources"))
    return out


def images(reader):
    found = []

    def res(r):
        r = r.get_object() if r is not None else None
        if r is None:
            return
        for x in (r.get("/XObject") or {}).values():
            o = x.get_object()
            if o.get("/Subtype") == "/Image":
                found.append(o)
            elif o.get("/Subtype") == "/Form":
                res(o.get("/Resources"))

    res(reader.pages[0].get("/Resources"))
    return found


@unittest.skipUnless(pypdf, "pypdf not installed")
class PrintPDF(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.cm = cmyk.CMYK(SWOP if SWOP.is_file() else None, overrides=cmyk.parse_overrides("#1f6feb = 90 55 0 0"))

    def make(self, name="p", **kw):
        p = str(Path(self.dir) / f"{name}.pdf")
        info = printpdf.print_pdf(kw.pop("scene", design()), p, kw.pop("cm", self.cm), dpi=72, reg=REG, **kw)
        return pypdf.PdfReader(p), info, p

    def test_vector_is_all_cmyk(self):
        r, info, _ = self.make()
        body = "\n".join(streams(r))
        self.assertNotRegex(body, r"\b(rg|RG)\b", "no RGB colour operators left")
        self.assertIn("0.9 0.55 0 0 k", re.sub(r"\.0\b", "", body), "the exact brand CMYK")
        self.assertRegex(body, r"\b0 0 0 1 K\b|\b0\.0 0\.0 0\.0 1 K\b", "pure black stroke")
        imgs = images(r)
        self.assertTrue(imgs)
        self.assertTrue(all(i.get("/ColorSpace") in ("/DeviceCMYK", "/DeviceGray") for i in imgs))
        self.assertEqual(info["converted"]["gradient stops"], 4)
        raw = Path(self.make("again")[2]).read_bytes()
        self.assertRegex(raw, rb"/FontFile[23]?", "fonts embedded: the shadowed title stays text")

    def test_flatten_is_one_image(self):
        r, info, _ = self.make(mode="flatten", raster_dpi=144)
        imgs = [i for i in images(r) if i.get("/ColorSpace") == "/DeviceCMYK"]
        self.assertEqual(len(imgs), 1)
        self.assertEqual((imgs[0]["/Width"], imgs[0]["/Height"]), (1200, 800), "2x the canvas at 144 dpi")
        self.assertNotIn(b"/FontFile", Path(self.make("f2", mode="flatten")[2]).read_bytes())

    def test_boxes_and_marks(self):
        r, info, _ = self.make(bleed=0.25, bleed_mode="canvas includes bleed", marks=False)
        pg = r.pages[0]
        self.assertEqual([float(v) for v in pg.trimbox], [18, 18, 582, 382])
        self.assertEqual([float(v) for v in pg.mediabox], [0, 0, 600, 400])
        self.assertAlmostEqual(info["trim_in"][0], 564 / 72)
        r, info, _ = self.make(bleed=0.25, bleed_mode="extend background", marks=True)
        pg = r.pages[0]
        self.assertEqual([float(v) for v in pg.trimbox], [0, 0, 600, 400])
        self.assertEqual([float(v) for v in pg.bleedbox], [-18, -18, 618, 418])
        self.assertLess(float(pg.mediabox[0]), -18 - printpdf.MARK_GAP - printpdf.MARK_LEN + 0.1)
        body = streams(r)[0]
        self.assertIn("1 1 1 1 K", body, "registration-colour marks")
        self.assertEqual(body.count(" l\n") + body.count(" l "), 8, "two marks at each corner")
        r, info, _ = self.make(bleed_mode="none")
        self.assertEqual([float(v) for v in r.pages[0].trimbox], [float(v) for v in r.pages[0].mediabox])
        with self.assertRaises(ValueError):
            self.make(bleed=5, bleed_mode="canvas includes bleed")

    def test_output_intent_only_when_calibrated(self):
        r, _, _ = self.make()
        self.assertEqual("/OutputIntents" in r.trailer["/Root"], self.cm.calibrated)
        r, _, _ = self.make("u", cm=cmyk.CMYK())
        self.assertNotIn("/OutputIntents", r.trailer["/Root"])

    @unittest.skipUnless(pypdfium2, "pypdfium2 not installed")
    def test_looks_like_the_design(self):
        _, _, p = self.make(bleed_mode="none")
        page = pypdfium2.PdfDocument(p)[0].render(scale=1).to_numpy()[:, :, :3].astype(np.float32) / 255
        ref = sc.render(design(), 1.0, REG)[:, :, :3]
        self.assertEqual(page.shape, ref.shape)
        # Same picture: compare edges, not brightness. The previewer turns CMYK back into RGB
        # its own way (without a profile), so tones differ; shapes and positions must not.
        edges = lambda a: np.abs(np.diff(a.mean(2), axis=0)).ravel()  # noqa: E731
        corr = np.corrcoef(edges(page), edges(ref))[0, 1]
        self.assertGreater(corr, 0.9, "same shapes in the same places")


if __name__ == "__main__":
    unittest.main()
