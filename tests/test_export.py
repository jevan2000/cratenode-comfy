"""Export tests (no ComfyUI needed): PNG / JPEG / WebP encoding, flattening, size budget, resize.

    python -m unittest discover -s tests -v
"""

import io
import sys
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import export  # noqa: E402
from cratenode_comfy.export import ExportOptions  # noqa: E402


def half_transparent(w=64, h=48):
    """Left half opaque red, right half fully transparent."""
    rgba = np.zeros((h, w, 4), np.float32)
    rgba[:, : w // 2] = (1, 0, 0, 1)
    return rgba


def noisy(w=400, h=300, seed=1):
    rng = np.random.default_rng(seed)
    rgba = rng.random((h, w, 4), dtype=np.float32)
    rgba[:, :, 3] = 1
    return rgba


def decode(enc):
    return Image.open(io.BytesIO(enc.data))


class Encode(unittest.TestCase):
    def test_png_keeps_alpha_and_pixels(self):
        enc = export.encode(half_transparent(), ExportOptions("png"))
        im = decode(enc)
        self.assertEqual((im.format, im.mode, im.size), ("PNG", "RGBA", (64, 48)))
        self.assertEqual(im.getpixel((5, 5)), (255, 0, 0, 255))
        self.assertEqual(im.getpixel((60, 5))[3], 0)
        self.assertIsNone(enc.quality)

    def test_jpeg_flattens_onto_matte(self):
        enc = export.encode(half_transparent(), ExportOptions("jpeg", quality=95, matte="#0000ff"))
        im = decode(enc)
        self.assertEqual((im.format, im.mode), ("JPEG", "RGB"))
        r, g, b = im.getpixel((60, 20))
        self.assertTrue(b > 240 and r < 15, (r, g, b))
        r, g, b = im.getpixel((5, 20))
        self.assertTrue(r > 240 and b < 15, (r, g, b))

    def test_png_opaque_when_transparency_off(self):
        im = decode(export.encode(half_transparent(), ExportOptions("png", transparent=False, matte="#000000")))
        self.assertEqual(im.mode, "RGB")
        self.assertEqual(im.getpixel((60, 5)), (0, 0, 0))

    def test_webp_lossy_and_lossless(self):
        lossy = decode(export.encode(half_transparent(), ExportOptions("webp", quality=80)))
        self.assertEqual((lossy.format, lossy.mode), ("WEBP", "RGBA"))
        exact = export.encode(half_transparent(), ExportOptions("webp", lossless=True))
        im = decode(exact)
        self.assertEqual(im.getpixel((5, 5)), (255, 0, 0, 255))
        self.assertEqual(im.getpixel((60, 5))[3], 0)
        self.assertIsNone(exact.quality)

    def test_dpi_and_srgb_profile(self):
        im = decode(export.encode(half_transparent(), ExportOptions("png", dpi=300)))
        self.assertAlmostEqual(im.info["dpi"][0], 300, delta=0.5)
        self.assertIn("icc_profile", im.info)
        im = decode(export.encode(half_transparent(), ExportOptions("jpeg", dpi=150, srgb=False)))
        self.assertEqual(im.info["dpi"], (150, 150))
        self.assertNotIn("icc_profile", im.info)

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            export.encode(half_transparent(), ExportOptions("tiff"))


class SizeBudget(unittest.TestCase):
    def test_lowers_quality_to_fit(self):
        img = noisy()
        full = export.encode(img, ExportOptions("jpeg", quality=95))
        limit = int(full.kb * 0.5)
        enc = export.encode(img, ExportOptions("jpeg", quality=95, max_kb=limit))
        self.assertTrue(enc.fits)
        self.assertLessEqual(len(enc.data), limit * 1024)
        self.assertLess(enc.quality, 95)
        # the next quality up would not have fitted (highest that fits)
        over = export.encode(img, ExportOptions("jpeg", quality=enc.quality + 1))
        self.assertGreater(len(over.data), limit * 1024)

    def test_reports_when_it_cannot_fit(self):
        enc = export.encode(noisy(), ExportOptions("webp", quality=90, max_kb=1))
        self.assertFalse(enc.fits)
        self.assertEqual(enc.quality, export.MIN_QUALITY)
        png = export.encode(noisy(), ExportOptions("png", max_kb=1))
        self.assertFalse(png.fits)

    def test_no_search_when_already_small(self):
        enc = export.encode(half_transparent(), ExportOptions("jpeg", quality=90, max_kb=500))
        self.assertTrue(enc.fits)
        self.assertEqual(enc.quality, 90)


class Resize(unittest.TestCase):
    def test_scale_and_clean_edges(self):
        out = export.resize(half_transparent(64, 48), 0.5)
        self.assertEqual(out.shape, (24, 32, 4))
        # visible pixels near the alpha edge stay red (no dark fringe from transparent black)
        vis = out[:, :, 3] > 0.05
        self.assertTrue(np.all(out[vis][:, 0] > 0.95))
        self.assertTrue(np.all(out[vis][:, 1] < 0.05))
        self.assertIs(export.resize(out, 1.0), out)


if __name__ == "__main__":
    unittest.main()
