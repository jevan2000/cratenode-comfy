# CrateNode-Comfy

A design suite for ComfyUI: typography, layout, shapes, effects, templates,
data-driven batches, motion and print output, as custom nodes that sit next to
your image-generation nodes.

**Status: early development.** See [docs/plan.md](docs/plan.md).

## Install (development)

Copy this folder into `ComfyUI/custom_nodes/cratenode-comfy` and install the
requirements into ComfyUI's Python:

```
python -m pip install -r requirements.txt
```

Restart ComfyUI. The nodes appear under **CrateNode-Comfy** in the node menu.

## How it works

Designs flow between nodes as a **scene** (`CN_SCENE`): a canvas plus text, shapes,
images and groups that stay vector until you render. That means sharp output at
any size, layouts that reflow when text changes, and PDF export. **Render Scene**
turns a scene into an `IMAGE` + alpha `MASK` for any other ComfyUI node; **Add
Image** brings any `IMAGE` (an AI background, a logo) into a scene.

Item nodes (Text Box, Shape, Add Image) take an optional `scene`: connected, they
add to it; left empty, they make a *part* for Stack, Place or Grid, which position
parts by their size so you never compute coordinates.

## Nodes

| Group | Node | What it does |
|---|---|---|
| Canvas | **Canvas** | Size from a preset (YouTube, Instagram, Story, Letter @300dpi, ...) or custom; background colour or gradient; safe-area margin |
| | **Safe Area** | Set the safe-area margins in pixels |
| Fill | **Linear Gradient**, **Radial Gradient** | Up to 4 colour stops, for canvases, shapes and text |
| Type | **Text Box** | Fonts from your folders, wrapping, align, vertical anchor (bottom grows upward), auto-fit, `*bold*` words, case, letter spacing, gradient text |
| Shapes | **Shape** | Rectangle (rounded), ellipse, line, polygon, star; fill or gradient, stroke, rotation |
| Image | **Add Image** | Fit, fill (crop) or stretch an image into a box |
| | **Image to Scene** | Start a design from an image |
| Layout | **Stack** | Up to 6 parts in a column or row with a gap, placed in the safe area / canvas / a custom box |
| | **Place** | One part at an alignment (e.g. a logo bottom-right of the safe area) |
| | **Grid** | Up to 9 parts in equal cells |
| | **Layers** | Scenes on top of each other |
| Effects | **Drop Shadow**, **Outer Glow**, **Outline**, **Blur** | On the last item or the whole scene so far |
| | **Opacity & Blend** | Opacity and 17 blend modes (multiply, screen, overlay, ...) |
| | **Clip to Previous** | Show the last item only inside the one before it (a photo inside text) |
| Output | **Render Scene** | IMAGE + alpha MASK at any scale |
| | **Export Image** | PNG, JPEG or WebP from a scene or any IMAGE batch: transparency kept (PNG/WebP) or flattened onto a matte, scale, DPI tag, sRGB profile, workflow embedded, and a `max_kb` budget that lowers quality until the file fits |
| | **Save PDF** | Vector PDF, fonts embedded |

Masks: our `MASK` outputs are coverage (1 = opaque). ComfyUI's **Load Image** mask
is the opposite (1 = transparent), so image inputs have a `mask_meaning` switch.

If a render comes out black, check that the chain starts from a **Canvas**: a part
on its own has a transparent background, and Save Image drops transparency.

## Examples

`examples/*.api.json` can be dragged into ComfyUI, or run headless:

```
python tools/run_workflow.py examples/thumbnail.api.json --server http://127.0.0.1:8188
```

- **thumbnail**: background image, headline with shadow and subtitle in a Stack, logo placed bottom-right.
- **export**: the thumbnail saved four ways: a YouTube JPEG under 2 MB, a half-size WebP for the web, the title alone as a transparent PNG overlay, and a 2x JPEG tagged 300 dpi made from a rendered IMAGE.
- **showcase**: gradient canvas, a photo clipped inside outlined text, a glowing star, gradient text, a grid of shapes, a 2x render.

## Configuration

Fonts, private templates and brand kits are read from folders you configure, so
licensed material never has to live inside this package. See
`cratenode_comfy/config.py`.

## Licence

MIT. See [LICENSE](LICENSE). Bundled example fonts are under the SIL Open Font
License (see `fonts/`).
