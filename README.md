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
| Data | **Load Template** | A saved design (JSON) as a scene, from your templates folder or the bundled ones |
| | **Fill Template** | Replace slot text, `name.color` colours, `{placeholders}` and image slots from a data row or a values box; layouts reflow |
| | **Save as Template** | Write a design to a template JSON (images embedded) |
| | **Data Rows** | Rows from a CSV/JSON file or pasted text; everything after it runs once per row |
| | **Row Value** | One column of a row as text, for any text input |
| Colour | **Palette** | Named colours (`primary: #1f6feb` lines) with a swatch preview |
| | **Palette from Image** | An image's main colours and their shares (k-means in Lab, similar colours merged) |
| | **Brand Kit** | A brand JSON: palette, heading/body fonts and weights, logo |
| | **Pick Color** | One colour as `#hex` for any colour input: by name, the most readable against a background, lightest, darkest |
| | **Contrast Check** | WCAG contrast ratio and grade (AA / AAA) |
| | **Recolor Scene** | Swap colours throughout a design (`primary -> accent`) |
| Motion | **Timeline** | A design's length and frame rate |
| | **Animate In**, **Animate Out** | Presets: fade, fade up/down, slides, pop, zoom, wipe, blur in; stagger plays the parts of a Stack / Grid in turn |
| | **Animate** | Keyframes (`0: 0, 2: 360`) with easing for x, y, scale, rotation, opacity, blur or wipe |
| | **Add Video**, **Video to Scene** | Video frames (an IMAGE batch) inside a design, or a design on top of a video |
| | **Render Frame** | One moment as IMAGE + alpha |
| | **Render Animation** | All frames as an IMAGE + MASK batch (for VideoHelperSuite or any image node) |
| | **Save Video** | MP4 (H.264), MOV (ProRes 4444 with alpha), WebM (VP9 with alpha) or GIF, with audio; streamed through ffmpeg |
| Smart | **Auto Place** | Put a part where the design (or a given image) is calmest, inside the safe area; optionally switch its text to white or near-black |
| | **Find Quiet Area** | The calmest box of a size in any image: x, y, size, a readable text colour and a heat map |
| | **Readability Check** | WCAG contrast of each text against the pixels behind its letters; report and a pass/fail overlay |
| | **Smart Scrim** | A gradient band, box or soft glow under the last item, only as strong as needed to reach a contrast |
| | **Copy Writer (Ollama)** | Headlines, shorter text, subtitles, taglines or calls to action from a local Ollama model; variants come out as a list (one design each) |

Masks: our `MASK` outputs are coverage (1 = opaque). ComfyUI's **Load Image** mask
is the opposite (1 = transparent), so image inputs have a `mask_meaning` switch.

## Templates and data batches

Give an item a **slot** name (Text Box, Shape and Add Image have a `slot` input)
or type `{placeholders}` in any text, then **Save as Template**. **Fill Template**
changes a template by name:

```
title: When the waiting is the work      <- a text slot
title.color: #ffcc00                     <- a text or shape slot's colour
series: Still                            <- fills {series} in any text
```

Image slots take an IMAGE (`image_1` + `slot_1`). Stack, Place and Grid lay
out when the design is drawn, so a longer title still pushes the rest down.

**Data Rows** reads a CSV (header line) or JSON list and outputs one row at a
time: ComfyUI runs the nodes after it once per row. Wire the row into Fill
Template (or Row Value → any text input) and into Export Image / Save PDF,
whose `filename_prefix` takes `{column}` names plus `{date}`, `{time}` and
`{index}`, e.g. `batch/{index}_{title}`.

Templates are read from `templates/` in your data folder (`data_dir` in the
config) and from this package's `templates/`.

## Colour and brand kits

A brand kit is a folder with a `brand.json` (see `brand/example/`):

```json
{"cratenode_brand": 1, "name": "Example Co.",
 "colors": {"primary": "#1f6feb", "accent": "#f2b134"},
 "fonts": {"heading": {"family": "Montserrat", "weight": 800}, "body": {"family": "Inter", "weight": 400}},
 "logos": {"primary": "logo.png"}}
```

Kits are read from `brand/` in your data folder and from this package's
`brand/`. Wire **Brand Kit**'s fonts into a Text Box's `font_override` and
`weight`, its logo into Add Image (with `mask_meaning` set to alpha), and
**Pick Color** outputs into any colour input. With a palette connected, Fill
Template and Recolor Scene accept colour names (`title.color: accent`).

## Motion and video

Animation is added to items like effects: **Animate In** after a Text Box
animates that box; after a Stack (with `stagger`) it animates the parts one
after another. Animation only moves, scales, fades, blurs or wipes what the
layout already placed, so layouts never jump. **Timeline** sets the length (or
leave it at 0: the last animation + 1 s).

**Save Video** renders frame by frame straight into ffmpeg, so long or 4K videos
don't fill memory. It needs `ffmpeg` on PATH (or `CRATENODE_FFMPEG` pointing at
it). For overlays, load a clip with ComfyUI's **Load Video** → **Get Video
Components**, start the design with **Video to Scene**, and pass the audio to
Save Video.

Speed tip: an item with effects (shadow, glow, outline) is drawn once and then
moved per frame, unless something inside it is animated. For a shadowed title
that animates in parts, put the shadow on each part, not on the Stack.

## Smart helpers

The helpers use image statistics, not models: busyness is edges plus local
contrast; readability is the WCAG contrast of each text against the pixels behind
its letters (the worst 10 %). They run on the CPU. Nodes with a `device` input can
run on the GPU instead (`gpu when free`): set `gpu_gate` in the config (or the
`CRATENODE_GPU_GATE` environment variable) to a URL answering `{"ok": true|false}`
and the GPU is used only when it says yes, otherwise the CPU (the report says why).

**Copy Writer** talks to a local [Ollama](https://ollama.com) server with the
model you name; nothing is downloaded for you. Its `variants` output is a list, so
a Text Box fed by it makes one design per variant.

If a render comes out black, check that the chain starts from a **Canvas**: a part
on its own has a transparent background, and Save Image drops transparency.

## Examples

`examples/*.api.json` can be dragged into ComfyUI, or run headless:

```
python tools/run_workflow.py examples/thumbnail.api.json --server http://127.0.0.1:8188
```

- **thumbnail**: background image, headline with shadow and subtitle in a Stack, logo placed bottom-right.
- **export**: the thumbnail saved four ways: a YouTube JPEG under 2 MB, a half-size WebP for the web, the title alone as a transparent PNG overlay, and a 2x JPEG tagged 300 dpi made from a rendered IMAGE.
- **template_save**: the thumbnail with slots (`background`, `title`, `subtitle`, `logo`) saved as a template; it is bundled as `templates/thumbnail.json`.
- **batch_template**: three CSV rows → Load Template → Fill Template → one JPEG per row, named from the row.
- **batch_workflow**: the same batch with the graph as the template (Row Value feeds the Text Box).
- **colour**: a square card built from the example brand kit (colours, fonts, logo; title colour picked for contrast), a recoloured variant (`primary -> accent`), a contrast check, and a palette taken from the background photo.
- **motion**: an animated title card (staggered rise-and-blur, logo pop, fade out) saved as MP4 and GIF, plus a transparent WebM overlay version.
- **video_overlay**: a lower third sliding in over a clip (core Load Video), saved as MP4 with the clip's audio.
- **smart**: a title auto-placed in the calm side of a busy picture, readability checked before and after a smart scrim, and Find Quiet Area's heat map.
- **copy_variants**: three headline variants from Copy Writer, one design each (set `model` to an installed Ollama model first).
- **showcase**: gradient canvas, a photo clipped inside outlined text, a glowing star, gradient text, a grid of shapes, a 2x render.

## Configuration

Fonts, private templates and brand kits are read from folders you configure, so
licensed material never has to live inside this package. See
`cratenode_comfy/config.py`.

## Licence

MIT. See [LICENSE](LICENSE). Bundled example fonts are under the SIL Open Font
License (see `fonts/`).
