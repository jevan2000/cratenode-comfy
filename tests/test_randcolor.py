"""Random colours (no ComfyUI needed): families, styles, brightness, contrast, palettes.

    python -m unittest discover -s tests -v
"""

import colorsys
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import color as col, randcolor as rc  # noqa: E402

SEEDS = range(40)
WHITE = (1.0, 1.0, 1.0, 1.0)


def hue(c) -> float:
    return colorsys.rgb_to_hls(*c[:3])[0] * 360


def in_span(h, span, slack=2.0) -> bool:
    a, b = span
    return (h - a + slack) % 360 <= (b - a) % 360 + 2 * slack


class RandomColor(unittest.TestCase):
    def test_same_seed_same_colour_and_seeds_differ(self):
        self.assertEqual(rc.generate(7)[0], rc.generate(7)[0])
        self.assertGreater(len({col.to_hex(rc.generate(s)[0][0]) for s in SEEDS}), 35)

    def test_families_keep_their_hues(self):
        for fam in ("red", "orange", "green", "blue", "purple", "warm", "cool"):
            for s in SEEDS:
                c = rc.generate(s, family=fam, style="vivid")[0][0]
                self.assertTrue(in_span(hue(c), rc.FAMILIES[fam]), f"{fam} seed {s}: hue {hue(c):.0f}")

    def test_neutral_is_grey(self):
        for s in SEEDS:
            r, g, b, _ = rc.generate(s, family="neutral")[0][0]
            self.assertLess(max(r, g, b) - min(r, g, b), 0.18)

    def test_styles(self):
        for s in SEEDS:
            pastel = rc.generate(s, style="pastel")[0][0]
            dark = rc.generate(s, style="dark")[0][0]
            self.assertGreater(rc.lightness(pastel), 70)
            self.assertLess(rc.lightness(dark), 40)

    def test_brightness_range(self):
        for s in SEEDS:
            cs, notes = rc.generate(s, 3, min_brightness=40, max_brightness=55)
            self.assertEqual(notes, [])
            for c in cs:
                self.assertTrue(39.5 <= rc.lightness(c) <= 55.5, rc.describe(c))

    def test_contrast_against_a_background(self):
        for s in SEEDS:
            c, notes = rc.generate(s, family="any", against=WHITE, min_contrast=4.5)
            self.assertEqual(notes, [])
            self.assertGreaterEqual(col.contrast(c[0], WHITE), 4.5)

    def test_palette_colours_differ(self):
        cs, notes = rc.generate(3, 8, family="blue")
        self.assertEqual(len(cs), 8)
        self.assertEqual(len({col.to_hex(c) for c in cs}), 8)

    def test_impossible_limits_are_reported_not_raised(self):
        cs, notes = rc.generate(1, family="yellow", style="pastel", against=WHITE, min_contrast=7)
        self.assertEqual(len(cs), 1)
        self.assertTrue(notes and "contrast" in notes[0])

    def test_bad_names(self):
        with self.assertRaisesRegex(ValueError, "family"):
            rc.generate(1, family="plaid")
        with self.assertRaisesRegex(ValueError, "style"):
            rc.generate(1, style="loud")


if __name__ == "__main__":
    unittest.main()
