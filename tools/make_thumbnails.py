"""Thumbnails for example_workflows/ (ComfyUI shows <name>.jpg next to each template).

    python tools/make_thumbnails.py

Reads the renders that tools/run_workflow.py left under out/ after running every
api_examples workflow, so run those first. Copy Writer needs a model, so its
thumbnail is drawn here instead.
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT, DST = ROOT / "out", ROOT / "example_workflows"
W, H = 640, 360

SOURCES = {
    "thumbnail": ["thumbnail.api/12_*.png"],
    "showcase": ["showcase.api/22_*.png"],
    "export": ["export.api/11_*.jpg", "export.api/13_*.png"],
    "template_save": ["template_save.api/13_*.png"],
    "batch_template": ["batch_template.api/*.jpg"],
    "batch_workflow": ["batch_workflow.api/*.jpg"],
    "colour": ["colour.api/16_*.png", "colour.api/19_*.png"],
    "motion": ["motion.api/16_*.png"],
    "video_overlay": ["video_overlay.api/11_*.mp4@1.5"],
    "smart": ["smart.api/10_*.jpg"],
    "print": ["print.api/18_*.png"],
    "layers_blend": ["layers_blend.api/20_*.png"],
    "keyframes": ["keyframes.api/14_*.mp4@2.0"],
    "scene_to_image": ["scene_to_image.api/12_*.png", "scene_to_image.api/18_*.png"],
}


def latest(pattern):
    """The newest file matching pattern; ``video.mp4@seconds`` grabs that frame with ffmpeg."""
    pattern, _, at = pattern.partition("@")
    files = sorted(glob.glob(str(OUT / pattern)), key=lambda p: Path(p).stat().st_mtime)
    if not files:
        return None
    if not at:
        return files[-1]
    import subprocess

    from cratenode_comfy.video import ffmpeg_path

    still = str(Path(files[-1]).with_suffix(f".{at}s.png"))
    subprocess.run([ffmpeg_path(), "-v", "error", "-y", "-ss", at, "-i", files[-1], "-frames:v", "1", still],
                   check=True)
    return still


def tile(paths) -> Image.Image:
    """One picture, or several side by side, fitted into W x H on a dark background."""
    ims = [Image.open(p).convert("RGBA") for p in paths]
    canvas = Image.new("RGB", (W, H), (24, 26, 32))
    n = len(ims)
    cw = (W - 8 * (n + 1)) // n
    for i, im in enumerate(ims):
        im.thumbnail((cw, H - 16), Image.LANCZOS)
        bg = Image.new("RGBA", im.size, (40, 40, 48, 255))
        for y in range(0, im.size[1], 16):  # checkerboard behind transparency
            for x in range(0, im.size[0], 16):
                if (x // 16 + y // 16) % 2:
                    bg.paste((60, 60, 70, 255), (x, y, x + 16, y + 16))
        bg.alpha_composite(im)
        x = 8 + i * (cw + 8) + (cw - im.size[0]) // 2
        canvas.paste(bg.convert("RGB"), (x, (H - im.size[1]) // 2))
    return canvas


def copy_card() -> Image.Image:
    from cratenode_comfy import config, fonts, scene as sc, text

    reg = fonts.FontRegistry(config.Config(system_fonts=False))
    s = sc.Scene(W, H, sc.Gradient("linear", ((0, (0.07, 0.11, 0.23, 1)), (1, (0.12, 0.3, 0.33, 1))), 30))
    for i, (t, y) in enumerate((("Find your *peace*", 70), ("Rest in the noise", 160), ("Quiet *Sundays*", 250))):
        s = s.add(sc.ShapeItem("rectangle", 120, y - 12, 400, 70, (1, 1, 1, 0.08 + 0.04 * i), radius=12))
        s = s.add(sc.TextItem(text.TextSpec(t, "Montserrat", 700, 900, size=34, x=120, y=y, width=400,
                                            align="center", color=(1, 1, 1, 1))))
    s = s.add(sc.TextItem(text.TextSpec("Copy Writer (Ollama): one design per variant", "Inter", 400, size=16,
                                        x=0, y=330, width=W, align="center", color=(0.8, 0.85, 0.9, 1))))
    rgba = sc.render(s, reg=reg)
    return Image.fromarray(np.round(rgba[:, :, :3] * 255).astype(np.uint8))


def main() -> None:
    DST.mkdir(exist_ok=True)
    for name, pats in SOURCES.items():
        paths = [p for pat in pats for p in ([latest(pat)] if "*" in pat else [str(OUT / pat)]) if p]
        if name.startswith("batch"):
            paths = sorted(glob.glob(str(OUT / pats[0])))[-3:]
        if not paths:
            print(f"{name}: no render under out/ (run its workflow first)")
            continue
        tile(paths).save(DST / f"{name}.jpg", quality=85)
        print(f"{name}.jpg from {len(paths)} render(s)")
    copy_card().save(DST / "copy_variants.jpg", quality=85)
    print("copy_variants.jpg drawn")


if __name__ == "__main__":
    main()
