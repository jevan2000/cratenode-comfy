# Step 1 spike: SCENE vs IMAGE+MASK

Both pipelines build the same 1920x1080 thumbnail: a background image (fill), a
two-weight headline (`*PEACE*` in the bold weight) with a drop shadow, a subtitle
that sits under the headline (so a longer title pushes it down), and a logo
bottom-right. Both use the same font registry, text layout and skia drawing, so
only the data model differs.

- Workflows: `examples/spike/scene_thumbnail.api.json`, `examples/spike/image_thumbnail.api.json`
- Run headless: `python tools/run_workflow.py examples/spike/scene_thumbnail.api.json`
- Measured on 2026-11-17 in the sandbox ComfyUI (v0.42.5), CPU only.

## Results

| | SCENE (vector until rendered) | IMAGE + MASK (pixels at every step) |
|---|---|---|
| Output | identical: largest difference 2/255, no pixel off by more than 8, for a short and a long (3-line) title | |
| Nodes / wires for the 1x thumbnail | **10 / 9**: one `scene` wire runs through the chain | 11 / 16: every layer needs a composite node, image + mask wires, and the subtitle needs the title's `bottom` wired into `below_y` |
| Repeated settings | canvas size set once | canvas size repeated on every layer node (6 places) |
| Long title pushes the subtitle down | yes (`below_previous` on the subtitle) | yes, by wiring `bottom` → `below_y` |
| Render at 2x | one Render node with `scale` 2: 3840x2160 with sharp text | not possible without changing every size and position |
| PDF | yes: vector, fonts embedded, text copyable | no (pixels only) |
| Re-run after editing the title | about 2.2 s (the whole scene is redrawn at the end) | about 1.8 s (ComfyUI caches the unchanged layers) |
| Mixing with other ComfyUI nodes mid-design | needs Render (scene → IMAGE/MASK) and Add Image (IMAGE → scene) | native: every step is an IMAGE/MASK |

## Notes

- MASK convention: our nodes output coverage (1 = opaque). ComfyUI's LoadImage
  mask is the opposite (1 = transparent), so image inputs take a
  `mask_meaning` switch. Whichever model wins should keep that switch.
- skia's Paragraph needs `icudtl.dat` next to the base `python.exe` (venvs share
  it); `tools/install_sandbox.ps1` copies it.
- Speed: the scene model redraws everything on each run. Caching decoded images
  and laid-out text inside scene items would close most of the 0.4 s gap.

## Recommendation

**SCENE as the backbone**, with converters both ways (Render → IMAGE/MASK, and
IMAGE/MASK → scene item), so any ComfyUI node can still be used between design
steps. It gives fewer wires, one place for the canvas size, sharp output at any
scale, PDF/print, and a single object for motion to animate (re-render per frame).
The IMAGE+MASK model's advantages (per-layer caching, native pixels) are
recovered by the converters and by caching inside the scene renderer.
