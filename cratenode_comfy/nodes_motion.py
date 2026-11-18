"""Motion and video: a timeline, entrance / exit presets and keyframe animation on
any item, video frames inside a design, and rendering to frames or a video file."""

from __future__ import annotations

import logging
import os
from dataclasses import replace

import numpy as np
from comfy_api.latest import IO, UI

from . import motion, render, video
from . import scene as sc
from . import template as tpl
from .nodes_common import (MASK_MEANINGS, ROOT, RowT, SceneT, apply_to_target, flow, flow_inputs, mask_to_alpha,
                           new_part, slot, target_input, with_warnings)

CAT = f"{ROOT}/Motion"
EASINGS = list(motion.EASINGS)
MAX_BATCH_GB = 8.0


# ---- helpers ----

animate_item = sc.animate


def frames_uint8(images, alpha=None, chunk: int = 16) -> np.ndarray:
    """ComfyUI IMAGE batch (+ optional coverage MASK) as N x H x W x 3|4 uint8, converted in chunks."""
    n, h, w = images.shape[0], images.shape[1], images.shape[2]
    c = 4 if alpha is not None else 3
    out = np.empty((n, h, w, c), np.uint8)
    if alpha is not None and tuple(alpha.shape[1:]) != (h, w):
        raise ValueError(f"mask {tuple(alpha.shape[1:])} does not match the frames {(h, w)}")
    for i in range(0, n, chunk):
        j = min(n, i + chunk)
        out[i:j, :, :, :3] = (images[i:j, :, :, :3].clamp(0, 1) * 255).round().byte().cpu().numpy()
        if alpha is not None:
            m = alpha[i:j] if alpha.shape[0] >= j else alpha[-1:].expand(j - i, -1, -1)  # short mask: repeat last
            out[i:j, :, :, 3] = (m.clamp(0, 1) * 255).round().byte().cpu().numpy()
    return out


def _fps(scene, fps):
    return fps if fps > 0 else (scene.fps if scene is not None and scene.fps > 0 else 30.0)


# ---- timeline and animation ----

class CNTimeline(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNTimeline", display_name="Timeline", category=CAT,
            description="Set a design's length and frame rate. Duration 0 = until the last animation ends + 1 s "
                        "(or the length of its video).",
            inputs=[SceneT.Input("scene"), IO.Float.Input("duration", default=0.0, min=0.0, max=3600.0, step=0.1),
                    IO.Float.Input("fps", default=30.0, min=1.0, max=120.0, step=1.0)],
            outputs=[SceneT.Output(display_name="scene"), IO.Float.Output(display_name="seconds")],
        )

    @classmethod
    def execute(cls, scene, duration, fps):
        out = replace(scene, duration=duration, fps=fps)
        return IO.NodeOutput(out, sc.scene_duration(out))


def _preset_schema(node_id, name, out):
    return IO.Schema(
        node_id=node_id, display_name=name, category=CAT,
        description=("Make the last item (or everything so far) leave: " if out else
                     "Make the last item (or everything so far) arrive: ")
                    + "fade, slide, pop, zoom, wipe or blur. On a Stack or Grid, stagger plays the parts one after "
                      "another.",
        inputs=[SceneT.Input("scene"), target_input(),
                IO.Combo.Input("preset", options=motion.PRESETS, default="fade up"),
                IO.Float.Input("start", default=0.0 if not out else 3.0, min=0.0, max=3600.0, step=0.05,
                               tooltip="Seconds"),
                IO.Float.Input("duration", default=0.6, min=0.01, max=60.0, step=0.05),
                IO.Combo.Input("easing", options=EASINGS, default="ease out" if not out else "ease in"),
                IO.Float.Input("distance", default=80.0, min=0.0, max=10000.0, tooltip="Pixels, for slides"),
                IO.Float.Input("stagger", default=0.0, min=0.0, max=10.0, step=0.05,
                               tooltip="Seconds between parts of a Stack / Grid / group")],
        outputs=[SceneT.Output(display_name="scene")],
    )


class CNAnimateIn(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return _preset_schema("CNAnimateIn", "Animate In", False)

    @classmethod
    def execute(cls, scene, target, preset, start, duration, easing, distance, stagger):
        tracks = motion.preset(preset, start, duration, distance, easing)
        return IO.NodeOutput(apply_to_target(scene, target, lambda it: animate_item(it, tracks, stagger)))


class CNAnimateOut(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return _preset_schema("CNAnimateOut", "Animate Out", True)

    @classmethod
    def execute(cls, scene, target, preset, start, duration, easing, distance, stagger):
        tracks = motion.preset(preset, start, duration, distance, easing, out=True)
        return IO.NodeOutput(apply_to_target(scene, target, lambda it: animate_item(it, tracks, stagger)))


class CNAnimate(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNAnimate", display_name="Animate", category=CAT,
            description="Keyframes for one property of the last item (or everything so far): 'seconds: value' "
                        "pairs. x / y are pixel offsets, scale 1 = normal, rotation in degrees, opacity 0..1, "
                        "blur in pixels, wipe 0..1 (reveals left to right).",
            inputs=[SceneT.Input("scene"), target_input(),
                    IO.Combo.Input("property", options=list(motion.PROPS), default="rotation"),
                    IO.String.Input("keyframes", multiline=True, default="0: 0\n2: 360"),
                    IO.Combo.Input("easing", options=EASINGS, default="ease in out"),
                    IO.Float.Input("stagger", default=0.0, min=0.0, max=10.0, step=0.05)],
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, scene, target, property, keyframes, easing, stagger):
        tr = (motion.track(property, motion.parse_keys(keyframes), easing),)
        return IO.NodeOutput(apply_to_target(scene, target, lambda it: animate_item(it, tr, stagger)))


# ---- video in designs ----

class CNAddVideo(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNAddVideo", display_name="Add Video", category=CAT,
            description="Put video frames (an IMAGE batch, e.g. from VideoHelperSuite's Load Video) into a box; "
                        "the frame follows the design's time. Box size 0 = to the canvas edge.",
            inputs=[SceneT.Input("scene", optional=True), IO.Image.Input("frames"),
                    IO.Mask.Input("mask", optional=True),
                    IO.Combo.Input("mask_meaning", options=MASK_MEANINGS, default=MASK_MEANINGS[0]),
                    IO.Float.Input("fps", default=30.0, min=1.0, max=240.0, tooltip="The frames' own frame rate"),
                    IO.Combo.Input("mode", options=render.FIT_MODES, default="fill"),
                    IO.Float.Input("x", default=0.0, min=-20000, max=20000),
                    IO.Float.Input("y", default=0.0, min=-20000, max=20000),
                    IO.Float.Input("box_width", default=0.0, min=0.0, max=40000),
                    IO.Float.Input("box_height", default=0.0, min=0.0, max=40000),
                    IO.Float.Input("start", default=0.0, min=0.0, max=3600.0, tooltip="Seconds before it starts"),
                    IO.Boolean.Input("loop", default=False, tooltip="Repeat; otherwise hold the last frame")]
                   + flow_inputs(),
            outputs=[SceneT.Output(display_name="scene")],
        )

    @classmethod
    def execute(cls, frames, fps, mode, x, y, box_width, box_height, start, loop, scene=None, mask=None,
                mask_meaning=MASK_MEANINGS[0], **kw):
        scene = new_part(scene)
        f = frames_uint8(frames, mask_to_alpha(mask, mask_meaning))
        w = box_width or (scene.width - x)
        h = box_height or (scene.height - y)
        item = sc.VideoItem(f, fps, x, y, w, h, mode, start, loop, flow=flow(kw), name=slot(kw))
        return IO.NodeOutput(scene.add(item))


class CNVideoToScene(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNVideoToScene", display_name="Video to Scene", category=CAT,
            description="Start a design from video frames: the canvas takes their size, frame rate and length, "
                        "so anything added on top becomes an overlay.",
            inputs=[IO.Image.Input("frames"), IO.Float.Input("fps", default=30.0, min=1.0, max=240.0),
                    IO.Float.Input("safe_margin", default=5.0, min=0.0, max=45.0, step=0.5)],
            outputs=[SceneT.Output(display_name="scene"), IO.Float.Output(display_name="seconds")],
        )

    @classmethod
    def execute(cls, frames, fps, safe_margin):
        f = frames_uint8(frames)
        n, h, w = f.shape[:3]
        m = min(w, h) * safe_margin / 100.0
        s = sc.Scene(w, h, margin=(m, m, m, m), fps=fps, duration=n / fps)
        return IO.NodeOutput(s.add(sc.VideoItem(f, fps, 0, 0, w, h, "stretch", loop=False)), n / fps)


# ---- rendering ----

class CNRenderFrame(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNRenderFrame", display_name="Render Frame", category=CAT,
            description="One moment of an animated design, as IMAGE + alpha MASK.",
            inputs=[SceneT.Input("scene"), IO.Float.Input("time", default=1.0, min=0.0, max=3600.0, step=0.05),
                    IO.Float.Input("scale", default=1.0, min=0.05, max=8.0, step=0.05)],
            outputs=[IO.Image.Output(display_name="image"), IO.Mask.Output(display_name="alpha")],
        )

    @classmethod
    def execute(cls, scene, time, scale):
        img, a = render.rgba_to_comfy(sc.render(scene, scale, t=time))
        return IO.NodeOutput(img, a)


class CNRenderAnimation(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNRenderAnimation", display_name="Render Animation", category=CAT,
            description="All frames as an IMAGE batch + alpha MASK batch (for VideoHelperSuite or any image node). "
                        "Frames are held in memory: for long or large videos use Save Video, which streams.",
            inputs=[SceneT.Input("scene"), IO.Float.Input("scale", default=0.5, min=0.05, max=8.0, step=0.05),
                    IO.Float.Input("fps", default=0.0, min=0.0, max=120.0, tooltip="0 = the design's frame rate"),
                    IO.Int.Input("start_frame", default=0, min=0, max=1_000_000),
                    IO.Int.Input("max_frames", default=0, min=0, max=1_000_000, tooltip="0 = all"),
                    IO.Int.Input("every_nth", default=1, min=1, max=1000, tooltip="2 = every other frame")],
            outputs=[IO.Image.Output(display_name="frames"), IO.Mask.Output(display_name="alpha"),
                     IO.Float.Output(display_name="fps")],
        )

    @classmethod
    def execute(cls, scene, scale, fps, start_frame, max_frames, every_nth):
        import torch

        fps = _fps(scene, fps)
        times = sc.frame_times(scene, fps, start_frame, max_frames, every_nth)
        w, h = max(1, round(scene.width * scale)), max(1, round(scene.height * scale))
        gb = len(times) * w * h * 4 * 4 / 1e9
        if gb > MAX_BATCH_GB:
            raise ValueError(f"{len(times)} frames at {w}x{h} need about {gb:.0f} GB as a batch; lower scale or "
                             f"max_frames, or use Save Video (it streams)")
        imgs = torch.empty((len(times), h, w, 3), dtype=torch.float32)
        alphas = torch.empty((len(times), h, w), dtype=torch.float32)
        for i, f in enumerate(sc.render_frames(scene, times, scale)):
            t = torch.from_numpy(f)
            imgs[i], alphas[i] = t[:, :, :3], t[:, :, 3]
        return IO.NodeOutput(imgs, alphas, fps / every_nth)


class CNSaveVideo(IO.ComfyNode):
    @classmethod
    def define_schema(cls):
        return IO.Schema(
            node_id="CNSaveVideo", display_name="Save Video", category=CAT,
            description="Write an animated design (streamed frame by frame) or an IMAGE batch to MP4, ProRes 4444 "
                        "MOV (alpha), VP9 WebM (alpha) or GIF, with optional audio. Uses ffmpeg.",
            is_output_node=True,
            inputs=[SceneT.Input("scene", optional=True),
                    IO.Image.Input("images", optional=True, tooltip="Or frames; used when no scene is connected"),
                    IO.Mask.Input("alpha", optional=True, tooltip="Transparency for images (1 = opaque)"),
                    IO.Audio.Input("audio", optional=True),
                    IO.Combo.Input("format", options=list(video.FORMATS), default="mp4 (H.264)"),
                    IO.Float.Input("fps", default=0.0, min=0.0, max=120.0, tooltip="0 = the design's (or 30)"),
                    IO.Int.Input("quality", default=80, min=1, max=100),
                    IO.Float.Input("scale", default=1.0, min=0.05, max=8.0, step=0.05, tooltip="Designs only"),
                    IO.String.Input("matte", default="#000000", tooltip="Behind transparency in MP4"),
                    IO.String.Input("filename_prefix", default="cratenode/video",
                                    tooltip="{column} from a data row, {date}, {time}, {index}"),
                    RowT.Input("row", optional=True)],
            outputs=[IO.String.Output(display_name="path"), IO.String.Output(display_name="report")],
        )

    @classmethod
    def execute(cls, format, fps, quality, scale, matte, filename_prefix, scene=None, images=None, alpha=None,
                audio=None, row=None):
        import folder_paths

        fps = _fps(scene, fps)
        if scene is not None:
            times = sc.frame_times(scene, fps)
            w, h = max(1, round(scene.width * scale)), max(1, round(scene.height * scale))
            frames = sc.render_frames(scene, times, scale, as_uint8=True)
        elif images is not None:
            arr = frames_uint8(images, alpha)
            h, w = arr.shape[1:3]
            frames = iter(arr)
        else:
            raise ValueError("connect a scene or images")
        aud = None
        if audio is not None:
            wf = audio["waveform"]
            aud = (wf[0].cpu().numpy(), int(audio["sample_rate"]))
        prefix = tpl.format_name(filename_prefix, row)
        out_dir, base, counter, subfolder, _ = folder_paths.get_save_image_path(
            prefix, folder_paths.get_output_directory(), w, h)
        name = f"{base}_{counter:05}_{video.FORMATS[format]}"
        path = os.path.join(out_dir, name)
        n = video.encode(path, frames, w, h, fps, format, quality, matte, aud)
        size = os.path.getsize(path) / 1e6
        report = f"{name}: {n} frames, {w}x{h} @ {fps:g} fps, {n / fps:.2f} s, {size:.1f} MB"
        if scene is not None:
            report = with_warnings(report, scene.items)
        logging.info("CrateNode-Comfy Save Video: %s", report)
        res = UI.SavedResult(name, subfolder, IO.FolderType.output)
        if format == "gif":
            ui = UI.SavedImages([res], is_animated=True)
        elif format.startswith("mov"):
            ui = UI.PreviewText(report)
        else:
            ui = UI.PreviewVideo([res])
        return IO.NodeOutput(path, report, ui=ui)


NODES = [CNTimeline, CNAnimateIn, CNAnimateOut, CNAnimate, CNAddVideo, CNVideoToScene, CNRenderFrame,
         CNRenderAnimation, CNSaveVideo]
