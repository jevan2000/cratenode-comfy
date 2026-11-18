"""Colour tests (no ComfyUI needed): palettes, contrast, palette from image,
recolouring, brand kits, palette names in templates.

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import color as col  # noqa: E402
from cratenode_comfy import config, fonts, scene as sc, template as tpl, text  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))
ROOT = Path(__file__).resolve().parent.parent
WHITE, BLACK = (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)


class Palettes(unittest.TestCase):
    def test_named_and_bare(self):
        p = col.parse_palette("# brand\nprimary: #1f6feb\naccent = #F2B134 // warm\n#000000, #ffffff80")
        self.assertEqual(p.names(), ["primary", "accent", "color_3", "color_4"])
        self.assertEqual(p.hexes(), ["#1f6feb", "#f2b134", "#000000", "#ffffff80"])
        self.assertEqual(p.get("ACCENT"), p.get("2"))
        self.assertEqual(p.get("#ff0000"), (1.0, 0.0, 0.0, 1.0))
        with self.assertRaisesRegex(KeyError, "primary, accent"):
            p.get("nope")

    def test_bad_line(self):
        with self.assertRaises(ValueError):
            col.parse_palette("primary: blue")


class Contrast(unittest.TestCase):
    def test_wcag_values(self):
        self.assertAlmostEqual(col.contrast(WHITE, BLACK), 21.0, places=2)
        self.assertAlmostEqual(col.contrast(WHITE, WHITE), 1.0)
        self.assertAlmostEqual(col.contrast(col.parse_palette("#777777").get("1"), WHITE), 4.48, places=2)
        self.assertEqual(col.wcag_grade(4.48), "fail")
        self.assertEqual(col.wcag_grade(4.48, large=True), "AA")
        self.assertEqual(col.wcag_grade(7.1), "AAA")

    def test_best_contrast(self):
        p = col.parse_palette("light: #f5f7fa\ndark: #111418\nmid: #808080")
        self.assertEqual(col.best_contrast(col.parse_palette("#1f6feb").get("1"), p.colors)[0], "light")
        self.assertEqual(col.best_contrast((1.0, 0.9, 0.3, 1.0), p.colors)[0], "dark")


class FromImage(unittest.TestCase):
    def img(self):
        """60% red, 30% blue, 10% near-red noise; the right column is transparent."""
        rng = np.random.default_rng(3)
        a = np.zeros((100, 110, 4), np.float32)
        a[:60, :100] = (0.9, 0.1, 0.1, 1)
        a[60:90, :100] = (0.1, 0.2, 0.8, 1)
        a[90:, :100] = (0.88, 0.12, 0.1, 1)
        a[:, :100, :3] += rng.normal(0, 0.005, (100, 100, 3)).astype(np.float32)
        a[:, 100:] = (0, 1, 0, 0)  # transparent green must be ignored
        return a

    def test_main_colours_and_shares(self):
        pal, shares = col.palette_from_image(self.img(), count=5)
        self.assertEqual(len(pal.colors), 2, "near-duplicate reds merge; transparent green ignored")
        red, blue = pal.colors[0][1], pal.colors[1][1]
        self.assertGreater(red[0], 0.85)
        self.assertGreater(blue[2], 0.75)
        self.assertAlmostEqual(shares[0], 0.7, delta=0.02)
        self.assertAlmostEqual(sum(shares), 1.0, places=5)

    def test_count_caps_and_sorts(self):
        pal, _ = col.palette_from_image(self.img(), count=1)
        self.assertEqual(len(pal.colors), 1)
        pal, _ = col.palette_from_image(self.img(), count=4, sort="dark to light", min_distance=0)
        lums = [col.luminance(c) for _, c in pal.colors]
        self.assertEqual(lums, sorted(lums))

    def test_deterministic(self):
        a = col.palette_from_image(self.img(), 3, seed=1)[0]
        b = col.palette_from_image(self.img(), 3, seed=1)[0]
        self.assertEqual(a, b)


class Recolor(unittest.TestCase):
    def scene(self):
        grad = sc.Gradient("linear", ((0.0, WHITE), (1.0, (0.2, 0.2, 0.2, 1.0))))
        s = sc.Scene(200, 100, grad)
        s = s.add(sc.ShapeItem("rectangle", 0, 0, 50, 50, (1.0, 1.0, 1.0, 0.5), stroke=BLACK, stroke_width=2))
        t = sc.add_effect(sc.TextItem(text.TextSpec("Hi", color=WHITE)), sc.Shadow(color=BLACK))
        return s.add(sc.GroupItem((t,)))

    def test_swaps_everywhere_keeping_alpha(self):
        pal = col.parse_palette("accent: #f2b134")
        out, n = col.recolor(self.scene(), col.parse_mapping("#ffffff -> accent\n#000000 -> #ff0000", pal))
        acc = pal.get("accent")
        self.assertEqual(n, 5)
        self.assertEqual(out.background.stops[0][1], acc)
        self.assertEqual(out.items[0].fill, (acc[0], acc[1], acc[2], 0.5))
        self.assertEqual(out.items[0].stroke, (1.0, 0.0, 0.0, 1.0))
        t = out.items[1].items[0]
        self.assertEqual(t.spec.color, acc)
        self.assertEqual(t.style.effects[0].color, (1.0, 0.0, 0.0, 1.0))
        sc.render(out, reg=REG)  # still renders

    def test_tolerance(self):
        s = sc.Scene(10, 10).add(sc.ShapeItem(fill=(0.98, 0.98, 0.98, 1.0)))
        self.assertEqual(col.recolor(s, [(WHITE, BLACK)], 0.01)[1], 0)
        self.assertEqual(col.recolor(s, [(WHITE, BLACK)], 0.03)[1], 1)

    def test_bad_mapping(self):
        with self.assertRaises(ValueError):
            col.parse_mapping("#ffffff #000000")


class Brands(unittest.TestCase):
    def test_bundled_example(self):
        found = col.find_brands([ROOT / "brand"])
        self.assertIn("example", found)
        bk = col.load_brand(found["example"])
        self.assertEqual(bk.palette.names(), ["primary", "secondary", "accent", "light", "dark"])
        self.assertEqual(bk.font("heading"), ("Montserrat", 800))
        self.assertTrue(bk.logos["primary"].is_file())
        REG.require(*bk.font("heading"))  # the kit's fonts are bundled

    def test_palette_names_in_templates(self):
        s = sc.Scene(100, 100).add(sc.TextItem(text.TextSpec("x"), name="title"))
        pal = col.parse_palette("accent: #f2b134")
        out, unused = tpl.fill(s, {"title.color": "accent"}, palette=pal)
        self.assertEqual(out.items[0].spec.color, pal.get("accent"))
        self.assertEqual(unused, [])

    def test_swatches_render(self):
        pal = col.parse_palette("a: #000000\nb: #ffffff\nc: #1f6feb")
        img = sc.render(col.swatch_scene(pal, cell=100), reg=REG)
        self.assertEqual(img.shape, (100, 300, 4))
        self.assertLess(img[90, 10, :3].max(), 0.05)  # black swatch corner
        self.assertGreater(img[90, 110, :3].min(), 0.95)  # white swatch corner


if __name__ == "__main__":
    unittest.main()
