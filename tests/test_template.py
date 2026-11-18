"""Template and data tests (no ComfyUI needed): JSON round trip, slots, filling and
reflow, data rows, filename templates.

    python -m unittest discover -s tests -v
"""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, fonts, layout, scene as sc, template as tpl, text  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))


def R(scene):
    return sc.render(scene, 1.0, reg=REG)


def tbox(t, name="", size=60, **kw):
    spec = text.TextSpec(text=t, family="Montserrat", weight=700, size=size, width=800, align="center", **kw)
    return sc.TextItem(spec, name=name)


def card(title="SHORT", sub="Subtitle line"):
    """A canvas with a gradient, a logo-ish image, and a stacked title + subtitle."""
    logo = np.zeros((40, 60, 4), np.float32)
    logo[10:30, 10:50] = (0.2, 0.8, 0.3, 1.0)
    bg = sc.Gradient("linear", ((0.0, (0.1, 0.1, 0.3, 1.0)), (1.0, (0.4, 0.1, 0.2, 1.0))), 45.0)
    s = sc.Scene(1000, 600, bg, margin=(50, 50, 50, 50))
    s = s.add(sc.ShapeItem("rectangle", 0, 520, 1000, 80, (0.0, 0.0, 0.0, 0.5), name="band"))
    s = s.add(sc.ImageItem(logo, 900, 530, 60, 40, "fit", name="logo"))
    title = sc.Scene(1, 1, items=(sc.add_effect(tbox(title, "title"), sc.Shadow()),))
    subtitle = sc.Scene(1, 1, items=(tbox(sub, "subtitle", size=30),))
    return s.add(layout.stack_item([title, subtitle], s.safe_box(), gap=20, valign="middle"))


def find(scene, name):
    return next(it for it in tpl.walk(scene.items) if it.name == name)


def placed_bounds(scene, name):
    """Bounds of the named text item after layout."""
    def walk(ps):
        for p in ps:
            if p.item.name == name:
                return p.bounds
            if p.children:
                b = walk(p.children)
                if b:
                    return b
    return walk(sc.place_items(scene.items, REG))


class RoundTrip(unittest.TestCase):
    def test_save_load_renders_the_same(self):
        s = card()
        with tempfile.TemporaryDirectory() as d:
            p = tpl.save(s, Path(d) / "card.json", description="test")
            back, data = tpl.load(p)
        self.assertEqual(data["name"], "card")
        self.assertEqual([x["name"] for x in data["slots"]], ["band", "logo", "title", "subtitle"])
        a, b = R(s), R(back)
        self.assertEqual(a.shape, b.shape)
        self.assertLess(np.abs(a - b).max(), 3 / 255, "the same design after a JSON round trip")

    def test_defaults_left_out(self):
        d = tpl.to_data(sc.ShapeItem("ellipse"))
        self.assertEqual(d, {"type": "ShapeItem", "kind": "ellipse"})

    def test_rejects_other_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text('{"hello": 1}', encoding="utf-8")
            with self.assertRaises(ValueError):
                tpl.load(p)

    def test_find_templates_private_first(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for folder in (a, b):
                tpl.save(card(), Path(folder) / "promo" / "card.json")
            tpl.save(card(), Path(b) / "other.json")
            found = tpl.find_templates([Path(a), Path(b)])
        self.assertEqual(sorted(found), ["other", "promo/card"])
        self.assertTrue(str(found["promo/card"]).startswith(a))


class Fill(unittest.TestCase):
    def test_longer_title_reflows_the_stack(self):
        s = card()
        short_sub = placed_bounds(s, "subtitle")
        long, unused = tpl.fill(s, {"title": "A MUCH LONGER TITLE THAT WRAPS ONTO SEVERAL LINES"})
        self.assertEqual(unused, [])
        long_sub = placed_bounds(long, "subtitle")
        title = placed_bounds(long, "title")
        self.assertGreater(long_sub[1], short_sub[1], "subtitle pushed down")
        self.assertGreater(title[3] - title[1], 150, "title wrapped")
        self.assertGreaterEqual(long_sub[1], title[3] + 19, "still a gap below the title")

    def test_colour_placeholder_and_image(self):
        s = card(sub="Week {week} | {series}")
        red = np.zeros((10, 10, 4), np.float32)
        red[...] = (1, 0, 0, 1)
        out, unused = tpl.fill(s, {"week": 3, "series": "Hope", "title.color": "#ff0000", "band.color": "#00ff00",
                                   "nope": "x"}, {"logo": red, "ghost": red})
        self.assertEqual(find(out, "subtitle").spec.text, "Week 3 | Hope")
        self.assertEqual(find(out, "title").spec.color, (1.0, 0.0, 0.0, 1.0))
        self.assertEqual(find(out, "band").fill, (0.0, 1.0, 0.0, 1.0))
        self.assertIs(find(out, "logo").rgba, red)
        self.assertEqual(sorted(unused), ["ghost", "nope"])
        self.assertEqual(tpl.placeholders(s), ["week", "series"])
        # unknown placeholders stay as typed; the original is unchanged
        self.assertEqual(find(tpl.fill(s, {"week": 1})[0], "subtitle").spec.text, "Week 1 | {series}")
        self.assertEqual(find(s, "subtitle").spec.text, "Week {week} | {series}")

    def test_effects_survive_filling(self):
        out, _ = tpl.fill(card(), {"title": "NEW"})
        self.assertEqual(find(out, "title").style.effects, (sc.Shadow(),))


class Rows(unittest.TestCase):
    def test_csv(self):
        rows = tpl.parse_rows("﻿title,week\nHope,1\n\n\"Peace, now\",2\n")
        self.assertEqual(rows, [{"title": "Hope", "week": "1"}, {"title": "Peace, now", "week": "2"}])

    def test_json(self):
        self.assertEqual(tpl.parse_rows('[{"title": "A", "n": 2, "tags": ["x"]}]'),
                         [{"title": "A", "n": "2", "tags": '["x"]'}])
        self.assertEqual(tpl.parse_rows('{"rows": [{"a": "1"}]}'), [{"a": "1"}])
        with self.assertRaises(ValueError):
            tpl.parse_rows("[1, 2]")


class Filenames(unittest.TestCase):
    def test_values_and_extras(self):
        row = {"title": 'Peace: "Now"/Here?', "_index": "4"}
        name = tpl.format_name("thumbs/{date}_{title}_{index}", row)
        self.assertRegex(name, r"^thumbs/\d{4}-\d\d-\d\d_Peace-Now-Here_005$")

    def test_unknown_column_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "row has only: title"):
            tpl.format_name("{titel}", {"title": "x"})

    def test_values_cannot_climb_folders(self):
        self.assertNotIn("/", tpl.format_name("{t}", {"t": "../../etc"}))
        self.assertEqual(tpl.safe_part(".."), "_")


if __name__ == "__main__":
    unittest.main()
