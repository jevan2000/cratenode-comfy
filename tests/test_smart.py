"""Smart helper tests (no ComfyUI, no GPU, no real model): device gate, busyness and
quiet areas, readability, scrims, the Ollama client against a fake server, and the
torch k-means path.

    python -m unittest discover -s tests -v
"""

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import color as col  # noqa: E402
from cratenode_comfy import config, copywriter, devices, fonts, layout, scene as sc, smart, text  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))
WHITE, BLACK = (1.0, 1.0, 1.0, 1.0), (0.0, 0.0, 0.0, 1.0)


def noisy_left(w=400, h=200):
    rng = np.random.default_rng(0)
    img = np.full((h, w, 3), 0.2, np.float32)
    img[:, : w // 2] = rng.random((h, w // 2, 3))
    return img


def label(t, color=WHITE, size=48, x=40, y=40, width=600, **kw):
    return sc.TextItem(text.TextSpec(t, "Montserrat", 800, size=size, color=color, x=x, y=y, width=width), **kw)


class Devices(unittest.TestCase):
    def test_cpu_and_fallbacks(self):
        self.assertEqual(devices.pick("cpu")[1], "cpu")
        self.assertIn("no CUDA", devices.pick("gpu when free", cuda_available=False)[1])
        cfg = config.Config(gpu_gate="http://gate.invalid/")
        dev, note = devices.pick("gpu when free", cfg, cuda_available=True,
                                 gate=lambda url: (False, "GPU gate said no: busy"))
        self.assertEqual((str(dev), note), ("cpu", "cpu (GPU gate said no: busy)"))
        dev, note = devices.pick("gpu when free", cfg, cuda_available=True, gate=lambda url: (True, "ok"))
        self.assertEqual(dev.type, "cuda", "cleared: the GPU (nothing is allocated here)")

    def test_gate_answers(self):
        with FakeServer({"ok": False, "reasons": ["GPU load 30 % >= 30 %"]}) as url:
            self.assertEqual(devices.ask_gate(url), (False, "GPU gate said no: GPU load 30 % >= 30 %"))
        with FakeServer({"ok": True}) as url:
            self.assertTrue(devices.ask_gate(url)[0])
        ok, why = devices.ask_gate("http://127.0.0.1:9/none", timeout=0.5)
        self.assertFalse(ok)
        self.assertIn("unreachable", why)


class Quiet(unittest.TestCase):
    def test_busyness(self):
        m, f = smart.busyness(noisy_left())
        self.assertEqual(f, 1.0)
        self.assertGreater(m[:, :150].mean(), 0.5)
        self.assertLess(m[:, 260:].mean(), 0.01)
        m2, f2 = smart.busyness(np.zeros((2000, 1000, 3), np.float32))
        self.assertEqual(m2.shape, (512, 256))
        self.assertAlmostEqual(f2, 0.256)

    def test_quiet_box_finds_the_calm_side(self):
        spot, _, _ = smart.quiet_box(noisy_left(), 120, 80)
        self.assertGreaterEqual(spot.x, 200)
        self.assertLess(spot.score, 0.02)
        np.testing.assert_allclose(spot.mean_color[:3], (0.2, 0.2, 0.2), atol=1e-4)
        spot9, _, _ = smart.quiet_box(noisy_left(), 120, 80, candidates="9 positions")
        self.assertIn(spot9.x, (140.0, 280.0))
        self.assertIn(spot9.y, (0.0, 60.0, 120.0))
        area, _, _ = smart.quiet_box(noisy_left(), 100, 50, area=(0, 0, 180, 200))
        self.assertLessEqual(area.x + area.w, 180, "stays inside the area")

    def test_heatmap(self):
        spot, m, f = smart.quiet_box(noisy_left(), 120, 80)
        hm = smart.heatmap(m, spot, f)
        self.assertEqual(hm.shape, (200, 400, 3))
        np.testing.assert_allclose(hm[int(spot.y), int(spot.x) + 5], (0.2, 1.0, 0.4))


    def test_ink_bounds_are_the_letters(self):
        t = label("I", width=600)  # a 600 px wide box holding one narrow letter
        lb = sc.content_bounds((t,), REG)
        ib = smart.ink_bounds((t,), REG)
        self.assertGreater(lb[2] - lb[0], 500)
        self.assertLess(ib[2] - ib[0], 40)
        self.assertGreaterEqual(ib[0], lb[0])
        self.assertIsNone(smart.ink_bounds((), REG))


class Readability(unittest.TestCase):
    def test_pass_fail_and_large_text(self):
        s = sc.Scene(800, 300, (0.95, 0.95, 0.95, 1))
        s = s.add(label("WHITE ON LIGHT", name="bad"))
        s = s.add(label("dark small", color=(0.1, 0.1, 0.1, 1), size=16, y=150, name="good"))
        bad, good = smart.readability(s, reg=REG)
        self.assertFalse(bad.ok)
        self.assertLess(bad.worst, 1.2)
        self.assertTrue(bad.large)
        self.assertEqual(bad.need, 3.0)
        self.assertTrue(good.ok)
        self.assertFalse(good.large)
        self.assertEqual(good.need, 4.5)
        self.assertGreater(good.worst, 15)
        self.assertIn("FAIL 'bad'", bad.line())

    def test_measures_what_is_behind_the_letters(self):
        s = sc.Scene(800, 300, BLACK)
        s = s.add(sc.ShapeItem("rectangle", 0, 0, 800, 70, WHITE))  # white band behind the top of the text
        s = s.add(label("HALF", y=40, size=80))
        c = smart.readability(s, reg=REG)[0]
        self.assertLess(c.worst, 1.5, "the worst pixels are the white band")
        self.assertGreater(c.median, 10, "most of the glyphs are on black")

    def test_texts_inside_layouts_and_gradients(self):
        grad = sc.Gradient("linear", ((0, (1, 1, 1, 1)), (1, (0.8, 0.8, 0.8, 1))))
        part = sc.Scene(1, 1, items=(sc.TextItem(text.TextSpec("A", size=60, width=200, align="center"), fill=grad),))
        s = sc.Scene(400, 300, BLACK).add(layout.stack_item([part, part], (0, 0, 400, 300)))
        checks = smart.readability(s, reg=REG)
        self.assertEqual(len(checks), 2)
        self.assertTrue(all(c.ok for c in checks))
        self.assertEqual(smart.text_color(part.items[0])[:3], (0.9, 0.9, 0.9))
        ov = smart.overlay(s, checks, 1.0, REG)
        self.assertEqual(ov.shape, (300, 400, 4))


class Scrim(unittest.TestCase):
    def test_needed_alpha_matches_the_maths(self):
        bg = np.full((100, 3), 0.8)
        a, achieved = smart.needed_alpha(WHITE, bg, BLACK, 4.5)
        self.assertGreaterEqual(achieved, 4.5)
        self.assertLess(smart.needed_alpha(WHITE, bg, BLACK, 4.5, )[0] - a, 1e-9)
        just_less = bg * (1 - (a - 0.01))
        self.assertLess(float(np.percentile(smart.ratios(1.0, just_less), 10)), 4.5, "the smallest that works")
        self.assertEqual(smart.needed_alpha(WHITE, np.zeros((5, 3)), BLACK, 4.5)[0], 0.0)

    def _light_scene(self):
        rng = np.random.default_rng(1)
        photo = (0.6 + 0.4 * rng.random((300, 800, 3))).astype(np.float32)
        s = sc.Scene(800, 300).add(sc.ImageItem(np.concatenate([photo, np.ones((300, 800, 1), np.float32)], 2),
                                                0, 0, 800, 300, "stretch"))
        return s.add(label("READ ME", y=200, size=60))

    def test_styles_reach_the_target(self):
        for style in smart.SCRIM_STYLES:
            out, report = smart.scrim_for(self._light_scene(), style=style, target=4.5, reg=REG)
            self.assertEqual(len(out.items), 3, style)
            self.assertEqual(out.items[1].name, "scrim")
            after = smart.readability(out, reg=REG)[0]
            self.assertGreaterEqual(after.worst, 4.4, (style, report))
            self.assertIn("->", report)

    def test_band_comes_from_the_nearer_edge_and_auto_colour(self):
        out, _ = smart.scrim_for(self._light_scene(), style="gradient band", reg=REG)
        band = out.items[1]
        self.assertEqual(band.y + band.h, 300, "text is low: the band reaches the bottom")
        self.assertEqual(band.fill.stops[0][1][3], 0.0, "fades in from the top")
        dark = sc.Scene(800, 300, (0.1, 0.1, 0.1, 1)).add(label("DARK", color=(0.15, 0.15, 0.15, 1), y=20))
        out, _ = smart.scrim_for(dark, style="box", reg=REG)
        self.assertEqual(out.items[0].fill[:3], (1.0, 1.0, 1.0), "white under dark text")

    def test_nothing_when_readable(self):
        s = sc.Scene(400, 200, BLACK).add(label("FINE"))
        out, report = smart.scrim_for(s, reg=REG)
        self.assertIs(out, s)
        self.assertIn("no scrim needed", report)


class FakeServer:
    """A one-endpoint JSON server on a free port."""

    def __init__(self, reply, record=None):
        self.reply, self.record = reply, record if record is not None else []

    def __enter__(self):
        reply, record = self.reply, self.record

        class H(BaseHTTPRequestHandler):
            def _send(self):
                body = json.dumps(reply(record) if callable(reply) else reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                record.append(("GET", self.path, None))
                self._send()

            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                record.append(("POST", self.path, json.loads(self.rfile.read(n))))
                self._send()

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.srv.server_port}"

    def __exit__(self, *a):
        self.srv.shutdown()
        self.srv.server_close()


class Copy(unittest.TestCase):
    def test_parse(self):
        reply = ("<think>hmm</think>Here are 3 headlines:\n1. Find Your Peace\n2) \"Still Waters\"\n- Rest Now\n"
                 "* A headline that is far too long to fit in the box at all\n1. Find Your Peace\n")
        fit, long_ = copywriter.parse_variants(reply, 20)
        self.assertEqual(fit, ["Find Your Peace", "Still Waters", "Rest Now"])
        self.assertEqual(len(long_), 1)

    def test_prompt(self):
        p = copywriter.build_prompt("taglines", "A coffee shop", "warm, no puns", 4, 30)
        self.assertIn("4 memorable taglines", p)
        self.assertIn("at most 30 characters", p)
        self.assertTrue(p.endswith("Text:\nA coffee shop"))
        with self.assertRaises(ValueError):
            copywriter.build_prompt("poems", "x")

    def test_against_a_fake_ollama(self):
        rec = []
        with FakeServer({"response": "Brew Joy\nWarm Cups, Warm Hearts\nThis one is definitely too long ok"},
                        rec) as url:
            variants, report = copywriter.write("taglines", "coffee", "tiny-model", url, count=3, max_chars=24,
                                                seed=7)
        self.assertEqual(variants, ["Brew Joy", "Warm Cups, Warm Hearts"])
        self.assertIn("2 fit 24 characters, 1 too long", report)
        method, path, body = rec[0]
        self.assertEqual((method, path, body["model"], body["stream"], body["options"]["seed"]),
                         ("POST", "/api/generate", "tiny-model", False, 7))
        with FakeServer({"error": "model 'x' not found"}) as url:
            with self.assertRaisesRegex(RuntimeError, "not found"):
                copywriter.write("headlines", "x", "x", url)

    def test_needs_a_model_and_a_server(self):
        with self.assertRaisesRegex(ValueError, "choose an Ollama model"):
            copywriter.write("headlines", "x", "", "http://127.0.0.1:9")
        with self.assertRaisesRegex(RuntimeError, "not reachable"):
            copywriter.generate("http://127.0.0.1:9", "m", "p", timeout=1)


class TorchKMeans(unittest.TestCase):
    def test_same_as_numpy(self):
        import torch

        rng = np.random.default_rng(0)
        x = np.concatenate([rng.normal(c, 1.0, (300, 3)) for c in (0, 20, 50)])
        a = col._kmeans(x, 3, np.random.default_rng(5))
        c0 = col._kmeans(x, 3, np.random.default_rng(5), iters=0)[0]
        b = col._kmeans_torch(x, c0, 25, torch.device("cpu"))
        np.testing.assert_allclose(np.sort(a[0], 0), np.sort(b[0], 0), atol=1e-6)


if __name__ == "__main__":
    unittest.main()
