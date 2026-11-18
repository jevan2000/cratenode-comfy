"""Scene → image tests (no ComfyUI needed): sizes, rounding, flattening, sharpness.

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, convert, fonts, motion, scene as sc  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))


def card():
    s = sc.Scene(1920, 1080)  # transparent canvas
    return s.add(sc.ShapeItem("rectangle", 480, 270, 960, 540, (1.0, 0.0, 0.0, 1.0)))


class Sizes(unittest.TestCase):
    def test_modes(self):
        t = convert.target_size
        self.assertEqual(t(1920, 1080, "scale", 0.5), (960, 540))
        self.assertEqual(t(1920, 1080, "fit width", width=1024), (1024, 576))
        self.assertEqual(t(1920, 1080, "fit height", height=512), (910, 512))
        self.assertEqual(t(1920, 1080, "fit inside", width=1024, height=1024), (1024, 576))
        self.assertEqual(t(1080, 1920, "fit inside", width=1024, height=1024), (576, 1024))
        self.assertEqual(t(1920, 1080, "exact size (stretch)", width=512, height=512), (512, 512))

    def test_rounding_for_latents(self):
        t = convert.target_size
        self.assertEqual(t(1920, 1080, "fit height", height=512, multiple=64), (896, 512))
        self.assertEqual(t(1000, 1000, "scale", 1.0, multiple=8), (1000, 1000))
        self.assertEqual(t(1003, 997, "scale", 1.0, multiple=8), (1000, 1000))
        self.assertEqual(t(10, 10, "scale", 1.0, multiple=64), (64, 64), "never below one multiple")


class Convert(unittest.TestCase):
    def test_keep_transparency(self):
        img = convert.scene_to_rgba(card(), "fit width", width=960, reg=REG)
        self.assertEqual(img.shape, (540, 960, 4))
        self.assertEqual(img[5, 5, 3], 0.0)
        np.testing.assert_allclose(img[270, 480], (1, 0, 0, 1))

    def test_flatten(self):
        img = convert.scene_to_rgba(card(), "scale", 0.25, matte="#00ff00", reg=REG)
        np.testing.assert_allclose(img[2, 2], (0, 1, 0, 1))
        self.assertEqual(float(img[:, :, 3].min()), 1.0)

    def test_exact_stretch_and_rounding_resample(self):
        img = convert.scene_to_rgba(card(), "exact size (stretch)", width=512, height=512, reg=REG)
        self.assertEqual(img.shape, (512, 512, 4))
        ys, xs = np.where(img[:, :, 3] > 0.5)
        self.assertAlmostEqual((xs.max() - xs.min() + 1) / 512, 0.5, delta=0.01, msg="half the width")
        self.assertAlmostEqual((ys.max() - ys.min() + 1) / 512, 0.5, delta=0.01, msg="half the height")
        r64 = convert.scene_to_rgba(card(), "fit height", height=512, multiple=64, reg=REG)
        self.assertEqual(r64.shape[:2], (512, 896))

    def test_sharp_at_the_output_size(self):
        # rendered at the target size, not upscaled: a 2x output has crisp edges
        img = convert.scene_to_rgba(card(), "scale", 2.0, reg=REG)
        col = img[:, 1920, 3]
        edge = np.where((col > 0.02) & (col < 0.98))[0]
        self.assertLessEqual(len(edge), 2)

    def test_time(self):
        s = sc.Scene(100, 100).add(sc.animate(sc.ShapeItem("rectangle", 0, 0, 100, 100, (1, 1, 1, 1)),
                                              motion.preset("fade", 0, 1, easing="linear")))
        self.assertAlmostEqual(float(convert.scene_to_rgba(s, t=0.5, reg=REG)[50, 50, 3]), 0.5, delta=0.01)
        self.assertEqual(float(convert.scene_to_rgba(s, reg=REG)[50, 50, 3]), 1.0)


class ImageIn(unittest.TestCase):
    def photo(self, w=200, h=100, c=(0.0, 0.0, 1.0)):
        a = np.zeros((h, w, 4), np.float32)
        a[...] = c + (1.0,)
        return a

    def design(self):
        s = sc.Scene(400, 400, (0.5, 0.5, 0.5, 1.0), margin=(20, 20, 20, 20), fps=24)
        return s.add(sc.ShapeItem("rectangle", 150, 150, 100, 100, (1.0, 0.0, 0.0, 1.0)))

    def test_new_canvas(self):
        s = convert.image_into_scene(self.photo(), safe_margin=10)
        self.assertEqual((s.width, s.height, s.margin), (200, 100, (10, 10, 10, 10)))
        np.testing.assert_allclose(sc.render(s, reg=REG)[50, 100], (0, 0, 1, 1))

    def test_under_the_design(self):
        s = convert.image_into_scene(self.photo(), self.design(), convert.PLACES[1], "fill", name="ai")
        self.assertEqual((s.width, s.height, s.fps, s.margin), (400, 400, 24, (20, 20, 20, 20)))
        img = sc.render(s, reg=REG)
        np.testing.assert_allclose(img[10, 10], (0, 0, 1, 1), err_msg="fill covers the canvas")
        np.testing.assert_allclose(img[200, 200], (1, 0, 0, 1), err_msg="the design stays on top")
        self.assertEqual(s.items[0].name, "ai")

    def test_on_top_and_fit(self):
        s = convert.image_into_scene(self.photo(), self.design(), convert.PLACES[2], "fit")
        img = sc.render(s, reg=REG)
        np.testing.assert_allclose(img[200, 200], (0, 0, 1, 1), err_msg="the image covers the shape")
        np.testing.assert_allclose(img[10, 200], (0.5, 0.5, 0.5, 1), atol=1 / 255,
                                   err_msg="fit letterboxes: the canvas shows above")

    def test_replace_keeps_canvas(self):
        s = convert.image_into_scene(self.photo(), self.design(), convert.PLACES[3], "stretch")
        self.assertEqual(len(s.items), 1)
        self.assertEqual((s.width, s.fps, s.margin), (400, 24, (20, 20, 20, 20)))
        np.testing.assert_allclose(sc.render(s, reg=REG)[200, 200], (0, 0, 1, 1))


if __name__ == "__main__":
    unittest.main()
