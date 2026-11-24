"""New palettes / looks on server-queued prompts (no ComfyUI needed).

    python -m unittest discover -s tests -v
"""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import fluid, rerun  # noqa: E402

OLD = ["#111111", "#222222", "#333333", "#444444", "#555555"]


def palette(**over):
    ins = {"harmony": "random", "family": "any", "style": "any", "new_each_run": True, "locked": False,
           **{f"color_{i + 1}": c for i, c in enumerate(OLD)}}
    ins.update(over)
    return {"class_type": "CNPaletteGenerator", "inputs": ins}


def gradient(**over):
    ins = {**fluid.preset_values(next(iter(fluid.PRESETS))), "preset": next(iter(fluid.PRESETS)),
           "randomize": True, "seed": 7}
    ins.update(over)
    return {"class_type": "CNFluidGradient", "inputs": ins}


def colours(node):
    return [node["inputs"][f"color_{i}"] for i in range(1, 6)]


class RefreshPrompt(unittest.TestCase):
    def test_palette_new_each_run(self):
        p = {"1": palette()}
        self.assertEqual(rerun.refresh_prompt(p, random.Random(1)), 1)
        self.assertNotEqual(colours(p["1"]), OLD)
        self.assertTrue(all(c.startswith("#") and len(c) == 7 for c in colours(p["1"])))

    def test_palette_settings_respected(self):
        p = {"1": palette(locked=True), "2": palette(new_each_run=False)}
        self.assertEqual(rerun.refresh_prompt(p, random.Random(1)), 0)
        self.assertEqual(colours(p["1"]), OLD)
        self.assertEqual(colours(p["2"]), OLD)

    def test_palette_linked_inputs_kept(self):
        p = {"1": palette(color_2=["9", 0]), "2": palette(family=["9", 1])}
        rerun.refresh_prompt(p, random.Random(1))
        self.assertEqual(p["1"]["inputs"]["color_2"], ["9", 0])
        self.assertNotEqual(p["1"]["inputs"]["color_1"], OLD[0])
        self.assertEqual(colours(p["2"]), OLD)  # its options come from another node

    def test_runs_differ(self):
        rng = random.Random(3)
        seen = set()
        for _ in range(4):
            p = {"1": palette(), "2": gradient()}
            rerun.refresh_prompt(p, rng)
            seen.add((tuple(colours(p["1"])), p["2"]["inputs"]["seed"]))
        self.assertEqual(len(seen), 4)

    def test_fluid_randomize(self):
        p = {"2": gradient()}
        self.assertEqual(rerun.refresh_prompt(p, random.Random(5)), 1)
        self.assertEqual(p["2"]["inputs"]["preset"], fluid.CUSTOM)
        self.assertNotEqual(p["2"]["inputs"]["seed"], 7)

    def test_fluid_off_and_linked(self):
        off = {"2": gradient(randomize=False)}
        before = dict(off["2"]["inputs"])
        self.assertEqual(rerun.refresh_prompt(off, random.Random(5)), 0)
        self.assertEqual(off["2"]["inputs"], before)

        linked = {"2": gradient(palette=["4", 0], seed=["8", 0])}
        cols = colours(linked["2"])
        rerun.refresh_prompt(linked, random.Random(5))
        self.assertEqual(colours(linked["2"]), cols)  # colours come from the palette
        self.assertEqual(linked["2"]["inputs"]["seed"], ["8", 0])

    def test_other_nodes_untouched(self):
        p = {"3": {"class_type": "KSampler", "inputs": {"seed": 1}}, "x": "junk"}
        self.assertEqual(rerun.refresh_prompt(p), 0)
        self.assertEqual(p["3"]["inputs"]["seed"], 1)

    def test_register_once(self):
        rerun.register()
        rerun.register()
        hooks = sys.modules[rerun.REGISTRY].hooks
        self.assertEqual(sum(h is rerun.refresh_prompt for h in hooks), 1)


if __name__ == "__main__":
    unittest.main()
