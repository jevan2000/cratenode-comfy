"""Motion and video tests (no ComfyUI needed): easing, tracks, timed rendering,
stagger, video items, templates with animation, and ffmpeg output.

    python -m unittest discover -s tests -v
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cratenode_comfy import config, fonts, layout, motion, scene as sc, template as tpl, video  # noqa: E402

REG = fonts.FontRegistry(config.Config(system_fonts=False))
RED = (1.0, 0.0, 0.0, 1.0)


def box(x=40, y=40, w=40, h=40, c=RED, **kw):
    return sc.ShapeItem("rectangle", x, y, w, h, c, **kw)


def R(scene, t=None):
    return sc.render(scene, 1.0, reg=REG, t=t)


def have_ffmpeg():
    try:
        video.ffmpeg_path()
        return True
    except RuntimeError:
        return False


class Easing(unittest.TestCase):
    def test_endpoints(self):
        for name, f in motion.EASINGS.items():
            self.assertAlmostEqual(f(0.0), 0.0, places=6, msg=name)
            self.assertAlmostEqual(f(1.0), 1.0, places=6, msg=name)
        self.assertGreater(motion.EASINGS["back out"](0.7), 1.0, "back out overshoots")

    def test_track_and_keys(self):
        tr = motion.track("x", motion.parse_keys("0: 0, 1s: 100\n2 = 50"), "linear")
        self.assertEqual([tr.value(t) for t in (-1, 0, 0.5, 1, 1.5, 2, 9)], [0, 0, 50, 100, 75, 50, 50])
        with self.assertRaises(ValueError):
            motion.track("size", ((0, 1),))
        with self.assertRaises(ValueError):
            motion.parse_keys("zero: 1")

    def test_in_then_out(self):
        anim = motion.preset("fade", 0.0, 1.0, easing="linear") + motion.preset("fade", 3.0, 1.0, easing="linear",
                                                                                  out=True)
        op = [motion.state(anim, t)["opacity"] for t in (0, 0.5, 2, 3.5, 5)]
        self.assertEqual(op, [0.0, 0.5, 1.0, 0.5, 0.0])
        self.assertEqual(motion.state(anim, None)["opacity"], 1.0, "no time: at rest")


class Timed(unittest.TestCase):
    def test_fade_up_moves_and_fades(self):
        s = sc.Scene(200, 200).add(sc.animate(box(), motion.preset("fade up", 0, 1, distance=50, easing="linear")))
        self.assertEqual(R(s, 0.0)[:, :, 3].max(), 0.0, "invisible at the start")
        mid = R(s, 0.5)
        ys = np.where(mid[:, :, 3] > 0.01)[0]
        self.assertEqual((ys.min(), ys.max()), (65, 104), "25 px lower halfway")
        self.assertAlmostEqual(float(mid[80, 60, 3]), 0.5, delta=0.01)
        np.testing.assert_allclose(R(s, 1.0), R(s), atol=1 / 255, err_msg="at rest after the end")

    def test_wipe_and_rotation(self):
        s = sc.Scene(200, 200).add(sc.animate(box(0, 0, 100, 100),
                                              (motion.track("wipe", ((0, 0), (1, 1)), "linear"),)))
        half = R(s, 0.5)
        self.assertEqual(half[50, 40, 3], 1.0)
        self.assertEqual(half[50, 60, 3], 0.0)
        s = sc.Scene(200, 200).add(sc.animate(box(50, 90, 100, 20), (motion.track("rotation", ((0, 90),)),)))
        rot = R(s, 0.0)
        self.assertEqual(rot[60, 100, 3], 1.0, "a wide bar turned upright")
        self.assertEqual(rot[100, 60, 3], 0.0)

    def test_stagger_on_a_stack(self):
        parts = [sc.Scene(1, 1, items=(box(0, 0, 40, 20),)) for _ in range(3)]
        st = layout.stack_item(parts, (0, 0, 200, 200), gap=10, valign="top")
        s = sc.Scene(200, 200).add(sc.animate(st, motion.preset("fade", 0, 0.5, easing="linear"), stagger=0.5))
        a = R(s, 0.75)[:, :, 3]
        self.assertEqual([round(float(a[y, 100]), 2) for y in (10, 40, 70)], [1.0, 0.5, 0.0])

    def test_duration_and_frames(self):
        s = sc.Scene(100, 100).add(sc.animate(box(), motion.preset("pop", 0.5, 0.5)))
        self.assertEqual(sc.scene_duration(s), 2.0, "last key + 1 s")
        self.assertEqual(len(sc.frame_times(s, 10)), 20)
        self.assertEqual(sc.frame_times(s, 10, start=5, count=3, step=2), [0.5, 0.7, 0.9])
        s2 = sc.Scene(100, 100, duration=1.5, fps=24)
        self.assertEqual(len(sc.frame_times(s2)), 36)

    def test_render_frames_matches_render(self):
        s = sc.Scene(120, 80, (0, 0, 1, 1)).add(sc.animate(box(), motion.preset("slide from left", 0, 1)))
        ts = [0.0, 0.3, 1.0]
        fr = list(sc.render_frames(s, ts, reg=REG, as_uint8=True))
        self.assertEqual(fr[0].dtype, np.uint8)
        for t, f in zip(ts, fr):
            np.testing.assert_allclose(f / 255.0, R(s, t), atol=1 / 255)


    def test_cached_effects_match_direct_render(self):
        from cratenode_comfy import text

        t = sc.add_effect(sc.TextItem(text.TextSpec("Hi", "Montserrat", 800, size=60, x=20, y=20, width=300)),
                          sc.Shadow(0, 6, 12))
        part = sc.Scene(1, 1, items=(t,))
        st = layout.stack_item([part, sc.Scene(1, 1, items=(box(0, 0, 80, 10),))], (0, 0, 400, 200), gap=8)
        s = sc.Scene(400, 200, (0.2, 0.3, 0.5, 1)).add(
            sc.animate(st, motion.preset("slide from left", 0, 1, distance=60), stagger=0.3))
        ts = [0.0, 0.25, 0.5, 1.0, 2.0]
        for scale in (1.0, 0.5):
            for tt, f in zip(ts, sc.render_frames(s, ts, scale, reg=REG)):
                ref = sc.render(s, scale, reg=REG, t=tt)
                diff = np.abs(f - ref)
                # Mid-move the cached layer is resampled at a sub-pixel offset: edge pixels
                # differ a little, the picture as a whole does not.
                self.assertLess(diff.mean(), 0.002, (scale, tt))
                self.assertLess(diff.max(), 0.35, (scale, tt))
                if tt in (0.0, 2.0):  # at rest (whole-pixel positions): the same pixels
                    self.assertLess(diff.max(), 0.02, (scale, tt))


class Video(unittest.TestCase):
    def frames(self):
        f = np.zeros((4, 10, 20, 3), np.uint8)
        for i in range(4):
            f[i, :, :, 0] = 60 * i
        return f

    def test_frame_follows_time(self):
        v = sc.VideoItem(self.frames(), fps=2, w=20, h=10, mode="stretch", start=1.0)
        self.assertEqual([v.index(t) for t in (None, 0, 1.0, 1.5, 2.9, 3.0, 9.6)], [0, 0, 0, 1, 3, 0, 1])
        hold = sc.VideoItem(self.frames(), fps=2, loop=False)
        self.assertEqual(hold.index(100), 3)
        s = sc.Scene(20, 10).add(v)
        self.assertAlmostEqual(float(R(s, 2.0)[5, 5, 0]), 120 / 255, delta=1 / 255)
        self.assertEqual(sc.scene_duration(s), 3.0)

    def test_templates_refuse_video_keep_anim(self):
        with self.assertRaisesRegex(ValueError, "video"):
            tpl.to_data(sc.Scene(10, 10).add(sc.VideoItem(self.frames())))
        s = sc.Scene(100, 100, duration=2, fps=25).add(sc.animate(box(), motion.preset("pop", 0, 1)))
        back = tpl.from_data(tpl.to_data(s))
        self.assertEqual(back, s)
        np.testing.assert_allclose(R(back, 0.3), R(s, 0.3), atol=1 / 255)


@unittest.skipUnless(have_ffmpeg(), "ffmpeg not installed")
class Files(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def clip(self):
        s = sc.Scene(64, 48, fps=10, duration=1.0).add(sc.animate(box(10, 10, 30, 20), motion.preset("fade", 0, 1)))
        return s, list(sc.render_frames(s, sc.frame_times(s), reg=REG, as_uint8=True))

    def stream(self, info):
        return next(x for x in info["streams"] if x["codec_type"] == "video")

    def test_formats(self):
        s, frames = self.clip()
        want = {"mp4 (H.264)": ("h264", "yuv420p"), "mov (ProRes 4444, alpha)": ("prores", "yuva444p12le"),
                "webm (VP9, alpha)": ("vp9", "yuv420p"), "gif": ("gif", "bgra")}
        for fmt, (codec, pix) in want.items():
            p = str(Path(self.dir) / f"clip{video.FORMATS[fmt]}")
            n = video.encode(p, iter(frames), 64, 48, 10, fmt)
            self.assertEqual(n, 10)
            st = self.stream(video.probe(p))
            self.assertEqual((st["codec_name"], st["width"], st["height"]), (codec, 64, 48), fmt)
            if fmt.startswith("mov"):
                self.assertIn(st["pix_fmt"], ("yuva444p12le", "yuva444p10le"), "ProRes keeps alpha")

    def test_mp4_with_audio_and_odd_size(self):
        frames = [np.full((49, 63, 4), 200, np.uint8)] * 10
        tone = np.sin(np.linspace(0, 440 * 2 * np.pi, 48000))[None].repeat(2, 0) * 0.2
        p = str(Path(self.dir) / "a.mp4")
        video.encode(p, iter(frames), 63, 49, 10, "mp4 (H.264)", audio=(tone, 48000))
        info = video.probe(p)
        kinds = sorted(x["codec_type"] for x in info["streams"])
        self.assertEqual(kinds, ["audio", "video"])
        self.assertEqual((self.stream(info)["width"], self.stream(info)["height"]), (64, 50), "padded to even")
        self.assertAlmostEqual(float(info["format"]["duration"]), 1.0, delta=0.1)

    def test_bad_frame_size(self):
        with self.assertRaises(ValueError):
            video.encode(str(Path(self.dir) / "x.mp4"), iter([np.zeros((10, 10, 4), np.uint8)]), 20, 10, 10,
                         "mp4 (H.264)")


if __name__ == "__main__":
    unittest.main()
