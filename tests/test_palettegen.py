"""Palette generator (no ComfyUI needed): harmonies, families, styles, repeatability.

    python -m unittest discover -s tests -v
"""

import colorsys
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import palettegen as pg, randcolor as rc  # noqa: E402


def hue(c) -> float:
    return colorsys.rgb_to_hls(*c[:3])[0] * 360


def hue_gap(a, b) -> float:
    d = abs(hue(a) - hue(b)) % 360
    return min(d, 360 - d)


class Generate(unittest.TestCase):
    def test_every_harmony_family_and_style(self):
        for h in pg.HARMONIES:
            for fam in ("any", "blue", "warm", "neutral"):
                for style in ("any", "pastel", "dark"):
                    colors = pg.generate(3, h, fam, style)
                    self.assertEqual(len(colors), pg.COUNT, (h, fam, style))
                    for c in colors:
                        self.assertTrue(all(0.0 <= v <= 1.0 for v in c), (h, fam, style, c))
                    self.assertTrue(all(x.startswith("#") and len(x) == 7 for x in pg.to_hex_list(colors)))

    def test_same_seed_same_palette(self):
        self.assertEqual(pg.generate(42, "triadic", "teal", "vivid"), pg.generate(42, "triadic", "teal", "vivid"))
        self.assertNotEqual(pg.generate(42, "triadic"), pg.generate(43, "triadic"))

    def test_harmonies_follow_the_wheel(self):
        mono = pg.generate(5, "monochromatic", style="vivid")
        self.assertTrue(all(hue_gap(mono[0], c) < 15 for c in mono))
        comp = pg.generate(5, "complementary", style="vivid")
        self.assertGreater(hue_gap(comp[0], comp[1]), 160)
        tri = pg.generate(5, "triadic", style="vivid")
        self.assertTrue(100 < hue_gap(tri[0], tri[1]) < 140)
        ana = pg.generate(5, "analogous", style="vivid")
        self.assertTrue(all(hue_gap(ana[0], c) < 45 for c in ana))

    def test_lightness_is_spread(self):
        # five tones from dark to light, not five alike
        light = sorted(rc.lightness(c) for c in pg.generate(9, "analogous", style="vivid"))
        self.assertGreater(light[-1] - light[0], 15)

    def test_family_sets_the_base_hue(self):
        for seed in range(10):
            base = pg.generate(seed, "analogous", "blue", "vivid")[0]
            self.assertTrue(185 <= hue(base) <= 250, hue(base))

    def test_bad_names(self):
        for kw, word in [({"harmony": "clashing"}, "harmony"), ({"family": "plaid"}, "family"),
                         ({"style": "loud"}, "style")]:
            with self.assertRaisesRegex(ValueError, word):
                pg.generate(1, **kw)


if __name__ == "__main__":
    unittest.main()
