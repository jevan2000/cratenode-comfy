"""Fluid gradients (no ComfyUI needed): every style renders, the same settings give the
same picture, and it works as a fill wherever a gradient does.

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, fluid, fonts, scene as sc, template  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))
RED, BLUE, GREEN = (1.0, 0.0, 0.0, 1.0), (0.0, 0.0, 1.0, 1.0), (0.0, 1.0, 0.0, 1.0)


def grad(**kw):
    return fluid.FluidGradient(stops=((0.0, RED), (0.5, GREEN), (1.0, BLUE)), grain=0.0, **kw)


class Styles(unittest.TestCase):
    def test_every_style_renders(self):
        for style in fluid.STYLES:
            img = fluid.render(grad(style=style), 96, 54)
            self.assertEqual(img.shape, (54, 96, 4), style)
            self.assertTrue(np.isfinite(img).all(), style)
            self.assertGreater(float(img[..., :3].std()), 0.02, f"{style} is not flat")

    def test_same_settings_same_picture(self):
        a = fluid.render(grad(style="liquid", seed=4), 80, 60)
        b = fluid.render(grad(style="liquid", seed=4), 80, 60)
        c = fluid.render(grad(style="liquid", seed=5), 80, 60)
        np.testing.assert_array_equal(a, b)
        self.assertGreater(float(np.abs(a - c).mean()), 0.02, "a new seed gives a new picture")

    def test_controls_change_the_picture(self):
        base = fluid.render(grad(style="mesh"), 80, 45)
        for change in [{"twirl": 360}, {"blur": 0.3}, {"glass": 1.0}, {"hue_shift": 90}, {"saturation": 0.0},
                       {"vignette": 1.0}, {"bands": 3}, {"rotation": 90}, {"evolve": 2.0}]:
            img = fluid.render(grad(style="mesh", **change), 80, 45)
            self.assertGreater(float(np.abs(img - base).mean()), 0.003, change)
        grey = fluid.render(grad(style="mesh", saturation=0.0), 40, 20)[..., :3]
        self.assertLess(float(np.abs(grey - grey.mean(axis=-1, keepdims=True)).max()), 0.01)

    def test_the_colours_are_the_ones_given(self):
        img = fluid.render(fluid.FluidGradient(stops=((0.0, RED), (1.0, BLUE)), grain=0.0, style="liquid"), 64, 64)
        self.assertLess(float(img[..., 1].max()), 0.05, "no green appears from red and blue")


class Presets(unittest.TestCase):
    def test_every_preset_is_complete_and_renders(self):
        fields = {f for f in fluid.FluidGradient.__dataclass_fields__} - {"kind", "stops", "angle"}
        colours = {f"color_{i}" for i in range(1, fluid.MAX_COLORS + 1)}
        for name in fluid.PRESETS:
            v = fluid.preset_values(name)
            self.assertEqual(set(v), fields | colours, name)  # every setting of the node, nothing else
            self.assertIn(v["style"], fluid.STYLES, name)
            self.assertGreaterEqual(sum(1 for c in colours if v[c]), 2, name)
            img = fluid.render(fluid.preset_gradient(name), 64, 36)
            self.assertGreater(float(img[..., :3].std()), 0.02, f"{name} is not flat")

    def test_presets_differ(self):
        seen = {}
        for name in fluid.PRESETS:
            img = fluid.render(fluid.preset_gradient(name), 48, 27)[..., :3]
            for other, o in seen.items():
                self.assertGreater(float(np.abs(img - o).mean()), 0.03, f"{name} looks like {other}")
            seen[name] = img


class RandomLooks(unittest.TestCase):
    def test_random_looks_are_complete_repeatable_and_lively(self):
        fields = {f for f in fluid.FluidGradient.__dataclass_fields__} - {"kind", "stops", "angle"}
        colours = {f"color_{i}" for i in range(1, fluid.MAX_COLORS + 1)}
        styles = set()
        for seed in range(40):
            v = fluid.random_look(seed)
            self.assertEqual(v, fluid.random_look(seed), "same seed, same look")
            self.assertEqual(set(v), fields | colours, seed)
            styles.add(v["style"])
            # kept within the ranges that still look good
            self.assertLessEqual(v["grain"], 0.05, seed)
            self.assertEqual(v["brightness"], 0.0, seed)
            self.assertEqual(v["hue_shift"], 0.0, seed)
            self.assertTrue(0.8 <= v["scale"] <= 1.6, (seed, v["scale"]))
            self.assertTrue(v["softness"] >= 0.5, (seed, v["softness"]))
            self.assertGreaterEqual(sum(1 for c in colours if v[c]), 3, seed)
            img = fluid.render(fluid.values_gradient(v), 48, 27)
            self.assertGreater(float(img[..., :3].std()), 0.03, f"seed {seed} looks flat")
        self.assertGreaterEqual(len(styles), 5, "random looks use most styles")
        self.assertNotEqual(fluid.random_look(1), fluid.random_look(2))

    def test_blended_styles_get_neighbouring_hues(self):
        import random

        rng = random.Random(3)
        for _ in range(20):
            cols = fluid.random_colors(rng, "mesh")
            self.assertGreaterEqual(len(cols), 4)


class AsAFill(unittest.TestCase):
    def test_fills_a_canvas_and_a_shape(self):
        g = grad(style="liquid")
        bg = sc.render(sc.Scene(160, 90, g), reg=REG)
        self.assertEqual(bg.shape, (90, 160, 4))
        self.assertGreater(float(bg[..., :3].std()), 0.02)
        s = sc.Scene(200, 100).add(sc.ShapeItem("ellipse", 50, 25, 100, 50, g))
        out = sc.render(s, reg=REG)
        self.assertEqual(float(out[2, 2, 3]), 0.0, "only inside the shape")
        self.assertGreater(float(out[50, 100, 3]), 0.99)

    def test_works_like_a_gradient(self):
        g = grad(style="glass", seed=3)
        self.assertIsInstance(g, sc.Gradient)
        faded = sc.fade_fill(g, 0.5)
        self.assertIsInstance(faded, fluid.FluidGradient)
        self.assertEqual([c[3] for _, c in faded.stops], [0.5, 0.5, 0.5])
        self.assertEqual(faded.style, "glass")
        back = template.from_data(template.to_data(sc.Scene(10, 10, g)))
        self.assertEqual(back.background, g)

    def test_recolour_swaps_its_colours(self):
        from cratenode_comfy import color

        s = sc.Scene(10, 10, grad(style="mesh"))
        out, n = color.recolor(s, [(RED, (1.0, 1.0, 0.0, 1.0))])
        self.assertIsInstance(out.background, fluid.FluidGradient)
        self.assertEqual(out.background.stops[0][1], (1.0, 1.0, 0.0, 1.0))
        self.assertEqual(out.background.style, "mesh")
        self.assertGreaterEqual(n, 1)


if __name__ == "__main__":
    unittest.main()
