# CrateNode-Comfy plan

A kitchen-sink custom-node pack for designers in ComfyUI: automate design work in
the same graph as AI image generation. Typography, layout, shapes, effects,
templates, data-driven batches, motion, smart design helpers and print output.

## Goals

- **AI imagery + design in one graph:** generate a background, then lay type,
  shapes and logos over it and export a finished thumbnail, poster or cover.
- **Data-driven design:** fill templates from CSV/JSON rows and render every row.
- **Motion:** animate layer properties (keyframes, easing) and overlay design on
  video frames; export MP4, ProRes 4444 / WebM with alpha, GIF.
- **Designer quality:** real typography (shaping, kerning, rich text, wrapping,
  auto-fit), vector shapes, effects, print PDF with CMYK.

## Decisions

| Topic | Decision |
|---|---|
| Engine | [skia-python](https://github.com/kyamagu/skia-python): paths, effects, blend modes, Paragraph rich text, RGB PDF |
| Print | reportlab for CMYK PDF; Pillow ImageCms (littleCMS) for colour conversion through a configured profile; exact CMYK values on demand |
| Data model | **SCENE (vector) with converters both ways** — chosen 2026-11-17 after the step 1 spike ([spike-results.md](spike-results.md)). Render turns a scene into IMAGE/MASK; image nodes turn IMAGE/MASK back into scene items. The IMAGE+MASK spike nodes are retired in step 2 |
| Fonts | A configured font folder first, then system fonts; licence data from font catalogs; a warning (never an error) when a font is used outside its licence scope |
| Templates | JSON files with named slots, plus example workflows; a "Save as Template" node writes a design back to JSON |
| Batches | CSV/JSON rows use ComfyUI list execution; filename templates like `{date}_{title}` |
| Motion | Timeline (fps, duration) + Animate nodes (keyframes, easing on any numeric property) + a render node that outputs frame batches; our own ffmpeg Save Video node, or VideoHelperSuite. To be expanded after first use |
| Smart helpers | Auto-placement in quiet areas, readability/contrast check, smart scrim, palette from image, copy helpers via Ollama. CPU by default, optional GPU mode |
| API | ComfyUI V3 node API (`comfy_api.latest`) |
| Licence | MIT |
| Never in this repo | Licensed fonts, ICC profiles, brand assets, private paths or hosts, tokens. Examples use OFL fonts and placeholder content; private templates and brand kits live in a configured data folder |

## Status

- Step 1 (spike): done 2026-11-17, SCENE chosen.
- Step 2 (core families): done 2026-11-18. Canvas presets and safe areas, gradients, Text Box, Shape, Add Image / Image to Scene, Stack / Place / Grid / Layers, Drop Shadow / Outer Glow / Outline / Blur / Opacity & Blend / Clip to Previous, Render / Save PDF.
- Step 3 (export): done 2026-11-18. Export Image: PNG / JPEG / WebP (lossy or lossless) from a scene or an IMAGE batch; transparency or a matte; scale; DPI; sRGB ICC; workflow metadata like Save Image; `max_kb` size budget (highest quality that fits). Example `examples/export.api.json`.

## Build order

1. **Spike:** a thumbnail (background, title + subtitle, logo, shadow, PNG) built in both data models; compare quality, speed, wiring, reflow, resolution independence and PDF ability; pick the model.
2. **Core families:** canvas presets, type (text box, rich text, auto-fit), shapes (rect, ellipse, line, polygon, gradients), layout (Stack, Place, Layers, Frame, grids, safe areas), effects (shadow, glow, stroke, blur, blend modes, masks).
3. **Export:** PNG, JPEG, WebP.
4. **Templates and data batches.**
5. **Colour:** palettes, brand kits, palette from image.
6. **Motion and video.**
7. **Smart helpers.**
8. **PDF and CMYK print.**
9. **Polish:** docs, example gallery, v1 release.

## Testing

- Pure-Python unit tests for layout maths, fonts, templates and data.
- Every family ships example workflows (in `examples/`) that are run headless
  against a test ComfyUI instance and can be opened by hand.
- Key renders are reviewed by eye before a step is closed.

## Process

- Commit to `main` per ticket; review at the end of each step, then push.
- Develop and test in a sandbox ComfyUI install; production instances only at milestones.
