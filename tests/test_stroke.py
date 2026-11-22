"""Stroke styles (no ComfyUI needed): text form, alignment, dashes, double lines.

    python -m unittest discover -s tests -v
"""

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, fonts, scene as sc, stroke, template  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))
RED = (1.0, 0.0, 0.0, 1.0)


def alpha(style: str, width=10.0, kind="rectangle", fill=None):
    """Alpha of a 100x60 shape at (50, 50) on a 200x160 canvas."""
    s = sc.Scene(200, 160).add(sc.ShapeItem(kind, 50, 50, 100, 60, fill, RED, width,
                                            stroke_style=stroke.parse(style)))
    return sc.render(s, reg=REG)[:, :, 3]


class Text(unittest.TestCase):
    def test_round_trip_and_presets(self):
        for name, text in stroke.PRESETS.items():
            st = stroke.parse(text)
            self.assertEqual(stroke.parse(stroke.to_text(st)), st, name)
        st = stroke.parse("align=Inside; dash=3, 2; offset=1; cap=butt; join=miter; double=0.5,2,outside; behind=1")
        self.assertEqual((st.align, st.dash, st.offset, st.cap, st.join), ("inside", (3.0, 2.0), 1.0, "butt", "miter"))
        self.assertEqual((st.double_gap, st.double_width, st.double_side, st.behind), (0.5, 2.0, "outside", True))
        self.assertIsNone(stroke.parse("  "))

    def test_bad_values_say_what_is_wrong(self):
        for bad, words in [("align=middle", "align"), ("dash=3", "pairs"), ("double=1", "double"),
                           ("colour=red", "unknown key"), ("dash", "key=value")]:
            with self.assertRaisesRegex(ValueError, words):
                stroke.parse(bad)


class Geometry(unittest.TestCase):
    def test_plain_style_matches_the_old_stroke(self):
        plain = alpha("")
        explicit = alpha("align=center")  # drawn as an outline instead of a stroke
        self.assertLess(float(np.abs(plain - explicit).max()), 0.35, "same shape, within anti-aliasing")
        self.assertGreater(plain[50, 100], 0.9)  # on the edge
        self.assertGreater(plain[46, 100], 0.9)  # half the width outside

    def test_alignment(self):
        inside, outside = alpha("align=inside"), alpha("align=outside")
        self.assertLess(inside[47, 100], 0.05, "nothing outside the edge")
        self.assertGreater(inside[57, 100], 0.9, "the full width inside")
        self.assertGreater(outside[43, 100], 0.9, "the full width outside")
        self.assertLess(outside[53, 100], 0.05, "nothing inside the edge")

    def test_dashes_leave_gaps(self):
        solid, dashed = alpha(""), alpha("dash=1,1; cap=butt")
        row_solid, row_dashed = solid[50, 60:140], dashed[50, 60:140]
        self.assertGreater(float(row_solid.min()), 0.9)
        self.assertLess(float(row_dashed.min()), 0.05)
        self.assertGreater(float(row_dashed.max()), 0.9)

    def test_double_line_has_a_gap(self):
        a = alpha("double=1,0.5,inside")  # main 45..55, gap 55..65, second 65..70
        self.assertGreater(a[50, 100], 0.9)
        self.assertLess(a[60, 100], 0.05)
        self.assertGreater(a[67, 100], 0.9)
        out = alpha("double=1,0.5,outside")  # second line at 30..35, outside the box
        self.assertGreater(out[33, 100], 0.9)
        self.assertLess(out[40, 100], 0.05)

    def test_behind_the_fill(self):
        front = sc.render(sc.Scene(200, 160).add(sc.ShapeItem("rectangle", 50, 50, 100, 60, (0, 0, 1, 1), RED, 10)),
                          reg=REG)
        back = sc.render(sc.Scene(200, 160).add(sc.ShapeItem("rectangle", 50, 50, 100, 60, (0, 0, 1, 1), RED, 10,
                                                             stroke_style=stroke.parse("behind=1"))), reg=REG)
        np.testing.assert_allclose(front[52, 100, :3], (1, 0, 0), atol=0.05)  # stroke over the fill
        np.testing.assert_allclose(back[52, 100, :3], (0, 0, 1), atol=0.05)  # fill over the stroke
        np.testing.assert_allclose(back[47, 100, :3], (1, 0, 0), atol=0.05)  # outer half still shows

    def test_line_double_runs_both_sides(self):
        a = alpha("double=1,0.5", kind="line")
        self.assertTrue(a.max() > 0.9)

    def test_reach_covers_outside_strokes(self):
        self.assertEqual(stroke.reach(None, 10), 5)
        self.assertEqual(stroke.reach(stroke.parse("align=inside"), 10), 0)
        self.assertEqual(stroke.reach(stroke.parse("align=outside; double=1,0.5,outside"), 10), 25)
        item = sc.ShapeItem("rectangle", 0, 0, 10, 10, None, RED, 10, stroke_style=stroke.parse("align=outside"))
        self.assertEqual(sc.stroke_reach(sc.GroupItem(items=(item,))), 10)


class Templates(unittest.TestCase):
    def test_style_survives_a_template(self):
        st = stroke.parse("align=inside; dash=3,2; double=0.5,1,outside")
        s = sc.Scene(100, 100).add(sc.ShapeItem("ellipse", 0, 0, 50, 50, None, RED, 4, stroke_style=st))
        back = template.from_data(template.to_data(s))
        self.assertEqual(back.items[0].stroke_style, st)


if __name__ == "__main__":
    unittest.main()
