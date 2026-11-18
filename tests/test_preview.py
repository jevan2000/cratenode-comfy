"""Preview tests (no ComfyUI needed): backdrop, guides, animation time, description.

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, fonts, motion, preview, scene as sc  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))
RED = (1.0, 0.0, 0.0, 1.0)


def part_scene(**kw):
    s = sc.Scene(400, 200, margin=(40, 20, 40, 20), **kw)
    return s.add(sc.ShapeItem("rectangle", 100, 60, 100, 50, RED))


class Preview(unittest.TestCase):
    def test_transparency_over_backdrops(self):
        img = preview.preview(part_scene(), 1.0, reg=REG)
        self.assertEqual(img.shape, (200, 400, 3))
        np.testing.assert_allclose(img[80, 150], (1, 0, 0))  # the shape
        self.assertNotEqual(tuple(img[2, 2]), tuple(img[2, 14]), "checkerboard shows transparency")
        white = preview.preview(part_scene(), 1.0, background="white", reg=REG)
        np.testing.assert_allclose(white[2, 2], (1, 1, 1))
        opaque = preview.preview(part_scene(background=(0, 0, 1, 1)), 1.0, reg=REG)
        np.testing.assert_allclose(opaque[2, 2], (0, 0, 1))

    def test_scale(self):
        self.assertEqual(preview.preview(part_scene(), 0.5, reg=REG).shape, (100, 200, 3))

    def test_guides_only_in_the_preview(self):
        plain = preview.preview(part_scene(), 1.0, background="black", reg=REG)
        safe = preview.preview(part_scene(), 1.0, guides="safe area", background="black", reg=REG)
        np.testing.assert_allclose(safe[20, 41], preview.SAFE, err_msg="safe area line at the margin")
        np.testing.assert_allclose(plain[20, 41], (0, 0, 0))
        both = preview.preview(part_scene(), 1.0, guides="safe area + item outlines", background="black", reg=REG)
        np.testing.assert_allclose(both[60, 101], preview.BOUNDS, err_msg="item outline")
        # the render itself is untouched
        np.testing.assert_allclose(sc.render(part_scene(), reg=REG)[20, 41], (0, 0, 0, 0))

    def test_time(self):
        s = sc.Scene(200, 100).add(sc.animate(sc.ShapeItem("rectangle", 50, 25, 100, 50, RED),
                                              motion.preset("fade", 0, 1, easing="linear")))
        rest = preview.preview(s, 1.0, None, background="black", reg=REG)
        start = preview.preview(s, 1.0, 0.0, background="black", reg=REG)
        self.assertAlmostEqual(float(rest[50, 100, 0]), 1.0, places=2)
        self.assertAlmostEqual(float(start[50, 100, 0]), 0.0, places=2)

    def test_part_preview_crops_and_fits(self):
        # a small shape far from the origin: cropped to it (plus padding), then fitted
        s = sc.Scene(1920, 1080).add(sc.ShapeItem("rectangle", 1500, 900, 100, 50, RED))
        img = preview.part_preview(s, 320, 200, pad=10, background="black", reg=REG)
        self.assertEqual(img.shape, (70, 120, 3), "100x50 + 2x10 padding, not shrunk")
        # text: cropped to the letters, not to its (much wider) text box
        from cratenode_comfy import text

        t = sc.Scene(1920, 1080).add(sc.TextItem(text.TextSpec("Hi", "Montserrat", 700, size=80, x=0, y=0,
                                                                width=1728, color=(1, 1, 1, 1))))
        self.assertLess(preview.part_preview(t, 320, 200, reg=REG).shape[1], 200)
        # white content gets the dark checkerboard
        auto = preview.part_preview(t, 320, 200, pad=10, reg=REG)
        self.assertLess(float(auto[2, 2].mean()), 0.3)
        np.testing.assert_allclose(img[35, 60], (1, 0, 0))
        big = sc.Scene(10, 10).add(sc.ShapeItem("rectangle", 0, 0, 2000, 500, RED))
        self.assertLessEqual(preview.part_preview(big, 320, 200, reg=REG).shape[1], 320)

    def test_part_preview_includes_effects(self):
        s = sc.Scene(10, 10).add(sc.add_effect(sc.ShapeItem("rectangle", 0, 0, 100, 100, RED),
                                               sc.Shadow(dx=0, dy=30, blur=20)))
        with_fx = preview.part_preview(s, 400, 400, pad=0, background="white", reg=REG)
        self.assertGreater(with_fx.shape[0], 100 + 30, "room for the shadow below")
        self.assertLess(float(with_fx[-8, 50].mean()), 0.95, "the shadow is in the crop")

    def test_png(self):
        png = preview.to_png(np.zeros((4, 6, 3), np.float32))
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(preview.fit_scale(640, 400, 320, 200), 0.5)

    def test_describe(self):
        self.assertEqual(preview.describe(part_scene()), "400x200: 1 shape")
        s = sc.Scene(200, 100, fps=24).add(sc.animate(sc.ShapeItem(), motion.preset("pop", 0, 1)))
        s = s.add(sc.GroupItem((sc.ShapeItem(), sc.ShapeItem("ellipse"))))
        self.assertEqual(preview.describe(s), "200x100: 3 shapes; 2.00 s at 24 fps")
        self.assertEqual(preview.describe(sc.Scene(10, 10)), "10x10: empty")


if __name__ == "__main__":
    unittest.main()
