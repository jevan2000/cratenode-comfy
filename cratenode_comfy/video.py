"""Video files through ffmpeg: frames are piped in as raw RGBA, nothing is held in memory.

Formats:
    mp4      H.264, yuv420p (no alpha: flattened onto a matte), plays everywhere
    mov      ProRes 4444 with alpha, for editors (Premiere, Resolve, Final Cut)
    webm     VP9 with alpha, for the web and OBS
    gif      palette-optimised GIF (1-bit transparency)

ffmpeg comes from CRATENODE_FFMPEG, then PATH, then the imageio-ffmpeg package if installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

from .render import parse_color

FORMATS = {
    "mp4 (H.264)": ".mp4",
    "mov (ProRes 4444, alpha)": ".mov",
    "webm (VP9, alpha)": ".webm",
    "gif": ".gif",
}
ALPHA_FORMATS = {"mov (ProRes 4444, alpha)", "webm (VP9, alpha)", "gif"}


def ffmpeg_path() -> str:
    env = os.environ.get("CRATENODE_FFMPEG")
    if env and Path(env).is_file():
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    raise RuntimeError("ffmpeg not found: install it on PATH or set CRATENODE_FFMPEG to ffmpeg.exe")


def crf(quality: int, lo: int, hi: int) -> int:
    """Map quality 1..100 (100 best) onto a CRF range (lo best .. hi worst)."""
    q = max(1, min(100, int(quality)))
    return round(hi - (hi - lo) * (q - 1) / 99)


def write_wav(path: str, waveform: np.ndarray, sample_rate: int) -> None:
    """waveform: channels x samples float (-1..1)."""
    w = np.clip(np.asarray(waveform, np.float32), -1, 1)
    if w.ndim == 1:
        w = w[None]
    pcm = (w.T * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(w.shape[0])
        f.setsampwidth(2)
        f.setframerate(int(sample_rate))
        f.writeframes(pcm.tobytes())


def command(path: str, width: int, height: int, fps: float, fmt: str, quality: int = 80,
            audio: str | None = None, loop: bool = True) -> list[str]:
    if fmt not in FORMATS:
        raise ValueError(f"unknown video format {fmt!r}; use one of {', '.join(FORMATS)}")
    cmd = [ffmpeg_path(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{width}x{height}", "-r", f"{fps:g}", "-i", "-"]
    if audio and fmt != "gif":
        cmd += ["-i", audio]
    if fmt == "mp4 (H.264)":
        cmd += ["-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", "-c:v", "libx264", "-preset", "medium",
                "-crf", str(crf(quality, 14, 34)), "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    elif fmt == "mov (ProRes 4444, alpha)":
        cmd += ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le", "-vendor", "apl0",
                "-qscale:v", str(max(2, min(31, round(2 + (100 - quality) / 4))))]
    elif fmt == "webm (VP9, alpha)":
        cmd += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-crf", str(crf(quality, 18, 45)), "-b:v", "0",
                "-auto-alt-ref", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4"]
    else:  # gif
        cmd += ["-filter_complex",
                "[0:v]split[a][b];[a]palettegen=reserve_transparent=1:stats_mode=diff[p];"
                "[b][p]paletteuse=dither=sierra2_4a:alpha_threshold=128",
                "-loop", "0" if loop else "-1"]
    if audio and fmt != "gif":
        cmd += ["-c:a", "libopus" if fmt.startswith("webm") else "aac", "-b:a", "192k", "-shortest"]
    return cmd + [path]


def flatten(frame: np.ndarray, matte) -> np.ndarray:
    """uint8 RGBA over an opaque matte colour (for formats without alpha)."""
    a = frame[:, :, 3:4].astype(np.float32) / 255.0
    m = np.array(matte[:3], np.float32) * 255.0
    rgb = frame[:, :, :3].astype(np.float32) * a + m * (1 - a)
    out = np.empty_like(frame)
    out[:, :, :3] = np.round(rgb).astype(np.uint8)
    out[:, :, 3] = 255
    return out


def encode(path: str, frames, width: int, height: int, fps: float, fmt: str, quality: int = 80,
           matte: str = "#000000", audio: tuple | None = None) -> int:
    """Write uint8 RGBA frames (an iterable of H x W x 4) to ``path``. ``audio`` is
    (waveform channels x samples, sample_rate) or None. Returns the frame count."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    if audio is not None and fmt != "gif":
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        write_wav(tmp.name, audio[0], audio[1])
    keep_alpha = fmt in ALPHA_FORMATS
    m = parse_color(matte)
    proc = subprocess.Popen(command(path, width, height, fps, fmt, quality, tmp.name if tmp else None),
                            stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n = 0
    try:
        for f in frames:
            if f.shape[:2] != (height, width):
                raise ValueError(f"frame {n} is {f.shape[1]}x{f.shape[0]}, expected {width}x{height}")
            if f.shape[2] == 3:
                f = np.concatenate([f, np.full(f.shape[:2] + (1,), 255, np.uint8)], axis=2)
            proc.stdin.write(np.ascontiguousarray(f if keep_alpha else flatten(f, m)).tobytes())
            n += 1
        proc.stdin.close()
        err = proc.stderr.read().decode("utf-8", "replace")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {err.strip()[-2000:]}")
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    finally:
        for pipe in (proc.stdin, proc.stderr):
            try:
                pipe.close()
            except OSError:
                pass
        if tmp:
            os.unlink(tmp.name)
    if n == 0:
        raise ValueError("no frames to write")
    return n


def probe(path: str) -> dict:
    """Basic stream facts via ffprobe (for tests and reports)."""
    ff = ffmpeg_path()
    fp = str(Path(ff).with_name("ffprobe" + Path(ff).suffix))
    out = subprocess.run([fp, "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,width,height,pix_fmt,nb_frames,r_frame_rate:format=duration",
                          "-of", "json", path], capture_output=True, text=True, check=True).stdout
    import json

    return json.loads(out)
