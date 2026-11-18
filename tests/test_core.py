"""Core tests (no ComfyUI needed): fonts, text, scenes, effects, layout.

    python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, fonts, layout, render, scene as sc, text  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))


def R(scene, scale=1.0):
    return sc.render(scene, scale, reg=REG)


def rect(x, y, w, h, c=(1, 0, 0, 1), **kw):
    return sc.ShapeItem("rectangle", x, y, w, h, c, **kw)


def tspec(t, **kw):
    base = dict(text=t, family="Inter", size=40, x=0, y=0, width=500, color=(1, 1, 1, 1))
    base.update(kw)
    return text.TextSpec(**base)


class Fonts(unittest.TestCase):
    def test_bundled_fonts_resolve_by_weight(self):
        self.assertEqual(REG.families(), ["Inter", "Montserrat"])
        self.assertEqual(REG.require("montserrat", 700).weight, 700)
        self.assertEqual(REG.require("Montserrat", 800).weight, 900, "CSS rule: heavier first above 500")
        self.assertEqual(REG.require("Inter").licence.status, "bundled")
        with self.assertRaisesRegex(ValueError, "not installed"):
            REG.require("No Such Family")

    def test_licence_warnings(self):
        face = REG.require("Inter")
        scoped = replace(face, licence=fonts.Licence("scoped", ("Client A",)))
        self.assertIsNone(REG.licence_warning(face, None))
        self.assertIsNone(REG.licence_warning(scoped, "client a"))
        self.assertIn("Client A only", REG.licence_warning(scoped, "Client B"))


class Text(unittest.TestCase):
    def test_markup_and_case(self):
        self.assertEqual(text.spans("a *b* c"), [("a ", False), ("b", True), (" c", False)])
        self.assertEqual(text.spans("5 \\* 3, lone * star"), [("5 * 3, lone * star", False)])
        self.assertEqual(text.apply_case("the good shepherd", "Title"), "The Good Shepherd")

    def test_wrap_anchor_and_fit(self):
        two = text.layout(tspec("The 10 One Another Commands of the New Testament", width=800, line_height=1.2), REG)
        self.assertAlmostEqual(two.height, 96.0, delta=1.0)
        base = tspec("Short", y=100, width=300, height=300, valign="bottom")
        one = text.layout(base, REG)
        grown = text.layout(replace(base, text="A much longer title that wraps"), REG)
        self.assertAlmostEqual(one.bounds()[3], 400.0, delta=0.5)
        self.assertAlmostEqual(grown.bounds()[3], 400.0, delta=0.5)
        fit = text.layout(tspec("A long headline that will not fit", family="Montserrat", weight=900, size=200,
                                width=600, height=120, auto_fit=True), REG)
        self.assertLess(fit.size, 200)
        self.assertLessEqual(fit.height, 120.5)


class Shapes(unittest.TestCase):
    def test_rectangle_ellipse_star_line(self):
        s = sc.Scene(300, 100, (0, 0, 0, 1))
        img = R(s.add(rect(10, 10, 50, 30))
                 .add(sc.ShapeItem("ellipse", 100, 10, 80, 80, (0, 1, 0, 1)))
                 .add(sc.ShapeItem("star", 200, 10, 80, 80, (0, 0, 1, 1), sides=5, inner=0.4)))
        np.testing.assert_allclose(img[20, 20], [1, 0, 0, 1], atol=0.01)
        np.testing.assert_allclose(img[50, 140], [0, 1, 0, 1], atol=0.01)
        np.testing.assert_allclose(img[12, 102, :3], [0, 0, 0], atol=0.05, err_msg="ellipse corner is empty")
        np.testing.assert_allclose(img[50, 240], [0, 0, 1, 1], atol=0.01)
        line = R(sc.Scene(100, 20).add(sc.ShapeItem("line", 0, 10, 100, 0, None, (1, 1, 1, 1), 4)))
        self.assertGreater(line[10, 50, 3], 0.9)
        self.assertEqual(line[2, 50, 3], 0.0)

    def test_gradients(self):
        g = sc.Gradient("linear", ((0.0, (0, 0, 0, 1)), (1.0, (1, 1, 1, 1))), angle=0)
        img = R(sc.Scene(200, 10, g))
        self.assertLess(img[5, 2, 0], 0.05)
        self.assertGreater(img[5, 197, 0], 0.95)
        self.assertAlmostEqual(img[5, 100, 0], 0.5, delta=0.05)
        radial = R(sc.Scene(100, 100).add(rect(0, 0, 100, 100, sc.Gradient("radial", ((0, (1, 1, 1, 1)), (1, (0, 0, 0, 1)))))))
        self.assertGreater(radial[50, 50, 0], radial[5, 50, 0])


class Effects(unittest.TestCase):
    def test_drop_shadow_sits_under_and_offset(self):
        item = sc.add_effect(rect(20, 20, 20, 20, (1, 1, 1, 1)), sc.Shadow(dx=20, dy=0, blur=0, opacity=1.0))
        img = R(sc.Scene(100, 60, (1, 0, 0, 1)).add(item))
        np.testing.assert_allclose(img[30, 30], [1, 1, 1, 1], atol=0.01)
        np.testing.assert_allclose(img[30, 50, :3], [0, 0, 0], atol=0.02)
        np.testing.assert_allclose(img[30, 70, :3], [1, 0, 0], atol=0.02)

    def test_outline_glow_blur(self):
        base = rect(40, 40, 20, 20, (1, 1, 1, 1))
        outlined = R(sc.Scene(100, 100).add(sc.add_effect(base, sc.Outline(5, (1, 0, 0, 1)))))
        np.testing.assert_allclose(outlined[50, 37], [1, 0, 0, 1], atol=0.02)
        np.testing.assert_allclose(outlined[50, 50], [1, 1, 1, 1], atol=0.02)
        glow = R(sc.Scene(100, 100).add(sc.add_effect(base, sc.Glow(16, 0, (0, 1, 0, 1), 1.0))))
        self.assertGreater(glow[50, 34, 3], 0.05)
        blurred = R(sc.Scene(100, 100).add(sc.add_effect(base, sc.Blur(10))))
        self.assertTrue(0.05 < blurred[50, 40, 3] < 0.95)

    def test_opacity_blend_and_clip(self):
        half = R(sc.Scene(20, 20).add(sc.with_style(rect(0, 0, 20, 20, (1, 1, 1, 1)), opacity=0.5)))
        self.assertAlmostEqual(half[10, 10, 3], 0.5, delta=0.02)
        mult = R(sc.Scene(20, 20, (0.5, 0.5, 0.5, 1)).add(sc.with_style(rect(0, 0, 20, 20, (1, 0, 0, 1)), blend="multiply")))
        np.testing.assert_allclose(mult[10, 10, :3], [0.5, 0, 0], atol=0.02)
        shape = rect(0, 0, 10, 20, (1, 1, 1, 1))
        fill = sc.with_style(rect(0, 0, 20, 20, (0, 0, 1, 1)), clip_to_previous=True)
        clip = R(sc.Scene(20, 20).add(shape).add(fill))
        np.testing.assert_allclose(clip[10, 5], [0, 0, 1, 1], atol=0.02)
        self.assertEqual(clip[10, 15, 3], 0.0, "clipped away outside the shape")


class Layout(unittest.TestCase):
    def part(self, w, h):
        return sc.Scene(400, 300).add(rect(999, 999, w, h))

    def test_stack_vertical_and_horizontal(self):
        groups = layout.stack([self.part(200, 40), self.part(100, 20)], (0, 20, 400, 280), "vertical", 10,
                              "center", "top", REG)
        bounds = [sc.content_bounds((g,), REG) for g in groups]
        self.assertEqual(bounds, [(100, 20, 300, 60), (150, 70, 250, 90)])
        row = layout.stack([self.part(50, 50), self.part(30, 10)], (0, 0, 400, 200), "horizontal", 5,
                           "right", "middle", REG)
        self.assertEqual([sc.content_bounds((g,), REG) for g in row], [(315, 75, 365, 125), (370, 95, 400, 105)])

    def test_place_and_safe_area(self):
        s = sc.Scene(1000, 500, margin=(50, 50, 50, 50))
        self.assertEqual(layout.area_box(s, "safe area", 0, 0, 0, 0), (50, 50, 900, 400))
        self.assertEqual(layout.area_box(s, "custom", 100, 100, 0, 0), (100, 100, 900, 400))
        g = layout.place(self.part(80, 40), s.safe_box(), "right", "bottom", REG)
        self.assertEqual(sc.content_bounds(tuple(g), REG), (870, 410, 950, 450))

    def test_grid(self):
        parts = [self.part(20, 20) for _ in range(4)]
        g = layout.grid(parts, (0, 0, 220, 100), columns=2, gap_x=20, gap_y=0, reg=REG)
        b = [sc.content_bounds((x,), REG) for x in g]
        self.assertEqual(b[0], (40, 15, 60, 35))
        self.assertEqual(b[3], (160, 65, 180, 85))

    def test_text_stack_reflows(self):
        title = lambda t: sc.Scene(800, 600).add(sc.TextItem(tspec(t, size=60, width=500)))
        sub = sc.Scene(800, 600).add(sc.TextItem(tspec("sub", size=20)))
        short = layout.stack([title("Hi"), sub], (0, 0, 800, 600), "vertical", 10, "left", "top", REG)
        long = layout.stack([title("A title long enough to wrap twice over"), sub], (0, 0, 800, 600),
                            "vertical", 10, "left", "top", REG)
        y_short = sc.content_bounds((short[1],), REG)[1]
        y_long = sc.content_bounds((long[1],), REG)[1]
        self.assertGreater(y_long, y_short + 50)


class Rendering(unittest.TestCase):
    def test_scale_flow_and_groups(self):
        s = sc.Scene(200, 100, (0, 0, 0, 1)).add(rect(10, 10, 50, 30))
        big = R(s, 2.0)
        self.assertEqual(big.shape, (200, 400, 4))
        np.testing.assert_allclose(big[40, 40], [1, 0, 0, 1], atol=0.01)
        flowed = sc.resolve(sc.Scene(200, 200).add(rect(0, 10, 10, 30)).add(
            replace(rect(0, 0, 10, 10), flow=sc.Flow(True, 5))), REG)
        self.assertEqual(flowed[1].bounds[1], 45)
        grp = R(sc.Scene(100, 100).add(sc.GroupItem(items=(rect(0, 0, 10, 10),), dx=50, dy=50)))
        np.testing.assert_allclose(grp[55, 55], [1, 0, 0, 1], atol=0.01)

    def test_gradient_text_and_colors(self):
        g = sc.Gradient("linear", ((0, (1, 0, 0, 1)), (1, (0, 0, 1, 1))), angle=0)
        img = R(sc.Scene(600, 100).add(sc.TextItem(tspec("MMMMMMMMMMMM", size=60, family="Montserrat", weight=900), fill=g)))
        ink = img[..., 3] > 0.9
        cols = np.where(ink.any(axis=0))[0]
        left, right = img[ink[:, cols[0] + 2], cols[0] + 2], img[ink[:, cols[-1] - 2], cols[-1] - 2]
        self.assertGreater(left[:, 0].mean(), left[:, 2].mean())
        self.assertGreater(right[:, 2].mean(), right[:, 0].mean())
        self.assertEqual(render.parse_color("#ff000080"), (1.0, 0.0, 0.0, 128 / 255))
        with self.assertRaises(ValueError):
            render.parse_color("red")

    def test_pdf_keeps_text(self):
        s = sc.Scene(600, 300, (1, 1, 1, 1)).add(sc.TextItem(tspec("Hello PDF", color=(0, 0, 0, 1))))
        path = os.path.join(tempfile.mkdtemp(), "t.pdf")
        sc.to_pdf(s, path, reg=REG)
        data = Path(path).read_bytes()
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertIn(b"FontFile", data)


if __name__ == "__main__":
    unittest.main()
