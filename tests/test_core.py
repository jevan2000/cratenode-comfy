"""Core tests (no ComfyUI needed): fonts, text layout, scenes, rendering.

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, fonts, render, scene, text  # noqa: E402

BUNDLED_ONLY = config.Config(system_fonts=False)


def reg():
    return fonts.FontRegistry(BUNDLED_ONLY)


class Fonts(unittest.TestCase):
    def test_bundled_fonts_resolve_by_weight(self):
        r = reg()
        self.assertEqual(r.families(), ["Inter", "Montserrat"])
        self.assertEqual(r.require("montserrat", 700).weight, 700)
        self.assertEqual(r.require("Montserrat", 900).weight, 900)
        self.assertEqual(r.require("Montserrat", 800).weight, 900, "CSS rule: heavier first above 500")
        self.assertEqual(r.require("Inter").licence.status, "bundled")
        with self.assertRaisesRegex(ValueError, "not installed"):
            r.require("No Such Family")

    def test_licence_warnings(self):
        r = reg()
        face = r.require("Inter")
        self.assertIsNone(r.licence_warning(face, None))
        scoped = replace(face, licence=fonts.Licence("scoped", ("LifePointe",)))
        self.assertIsNone(r.licence_warning(scoped, "lifepointe"))
        self.assertIn("LifePointe only", r.licence_warning(scoped, "Cratefolio"))
        self.assertIn("not set", r.licence_warning(scoped, None))


class Text(unittest.TestCase):
    def test_spans_markup(self):
        self.assertEqual(text.spans("a *b* c"), [("a ", False), ("b", True), (" c", False)])
        self.assertEqual(text.spans("5 \\* 3, lone * star"), [("5 * 3, lone * star", False)])
        self.assertEqual(text.apply_case("the good shepherd", "Title"), "The Good Shepherd")

    def test_wraps_in_the_box(self):
        spec = text.TextSpec(text="The 10 One Another Commands of the New Testament", family="Inter", size=40,
                             width=800, line_height=1.2)
        laid = text.layout(spec, reg())
        self.assertAlmostEqual(laid.height, 96.0, delta=1.0, msg="two lines at 800 px")
        self.assertLessEqual(laid.paragraph.LongestLine, 800)

    def test_bottom_anchor_grows_upward(self):
        base = text.TextSpec(text="Short", family="Inter", size=40, y=100, width=300, height=300, valign="bottom")
        one = text.layout(base, reg())
        two = text.layout(replace(base, text="A much longer title that wraps"), reg())
        self.assertAlmostEqual(one.bounds()[3], 400.0, delta=0.5)
        self.assertAlmostEqual(two.bounds()[3], 400.0, delta=0.5)
        self.assertLess(two.y, one.y)

    def test_auto_fit_shrinks_to_the_box(self):
        spec = text.TextSpec(text="A long headline that will not fit", family="Montserrat", weight=900, size=200,
                             width=600, height=120, auto_fit=True)
        laid = text.layout(spec, reg())
        self.assertLess(laid.size, 200)
        self.assertLessEqual(laid.height, 120.5)


class Scenes(unittest.TestCase):
    def test_below_previous_reflows(self):
        title = lambda t: scene.TextItem(text.TextSpec(text=t, family="Inter", size=60, x=0, y=50, width=500))
        sub = scene.TextItem(text.TextSpec(text="sub", family="Inter", size=20, x=0, y=0, width=500),
                             flow=scene.Flow(True, 10))
        short = scene.resolve(scene.Scene(500, 500).add(title("Hi")).add(sub), reg())
        long = scene.resolve(scene.Scene(500, 500).add(title("A title long enough to wrap twice over")).add(sub), reg())
        self.assertAlmostEqual(short[1].bounds[1], short[0].bounds[3] + 10, delta=0.01)
        self.assertGreater(long[1].bounds[1], short[1].bounds[1] + 50)

    def test_render_and_scale(self):
        sc = scene.Scene(200, 100, (0, 0, 0, 1)).add(scene.RectItem(10, 10, 50, 30, (1, 0, 0, 1)))
        img = scene.render(sc, reg=reg())
        self.assertEqual(img.shape, (100, 200, 4))
        np.testing.assert_allclose(img[20, 20], [1, 0, 0, 1], atol=0.01)
        np.testing.assert_allclose(img[90, 190], [0, 0, 0, 1], atol=0.01)
        big = scene.render(sc, scale=2.0, reg=reg())
        self.assertEqual(big.shape, (200, 400, 4))
        np.testing.assert_allclose(big[40, 40], [1, 0, 0, 1], atol=0.01)

    def test_fit_modes(self):
        _, dst = render.fit_rects(200, 100, 0, 0, 100, 100, "fit")
        self.assertEqual((dst.left(), dst.top(), dst.width(), dst.height()), (0, 25, 100, 50))
        src, dst = render.fit_rects(200, 100, 0, 0, 100, 100, "fill")
        self.assertEqual((src.left(), src.width(), dst.width()), (50, 100, 100))

    def test_colors(self):
        self.assertEqual(render.parse_color("#ff000080"), (1.0, 0.0, 0.0, 128 / 255))
        with self.assertRaises(ValueError):
            render.parse_color("red")

    def test_pdf_keeps_text(self):
        import tempfile, os
        sc = scene.Scene(600, 300, (1, 1, 1, 1)).add(
            scene.TextItem(text.TextSpec(text="Hello PDF", family="Inter", size=40, x=20, y=20, width=500, color=(0, 0, 0, 1))))
        path = os.path.join(tempfile.mkdtemp(), "t.pdf")
        scene.to_pdf(sc, path, reg=reg())
        data = Path(path).read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertIn(b"FontFile", data)


if __name__ == "__main__":
    unittest.main()
