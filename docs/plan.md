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
| Print | ~~reportlab for CMYK PDF~~ skia's vector PDF converted to CMYK with pypdf (2026-11-18: skia-python gives no glyph positions, so reportlab could not redraw text where skia lays it out); Pillow ImageCms (littleCMS) for colour conversion through a configured profile; exact CMYK values on demand |
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
- Step 4 (templates and data): done 2026-11-18. Scenes save to and load from template JSON (`template.py`; defaults left out, images embedded); `slot` names on items and `{placeholders}` in text; Load / Fill / Save as Template; Data Rows (CSV/JSON, list output so the rest runs per row) and Row Value; `{column}`, `{date}`, `{time}`, `{index}` in Export Image / Save PDF filenames. Stack, Place and Grid now store a `LayoutItem` that is arranged at draw time, so filled templates reflow. A bundled `templates/thumbnail.json` and three examples.
- Step 5 (colour): done 2026-11-18. `color.py`: named palettes, WCAG contrast, palette from image (k-means++ in Lab on a sample, near-duplicates merged by ΔE), recolouring a whole scene, brand kits (JSON: colours, fonts, logos). Nodes Palette, Palette from Image, Brand Kit, Pick Color, Contrast Check, Recolor Scene; Fill Template takes a palette for colour names. Bundled `brand/example/`; example `examples/colour.api.json`. CPU only; a GPU option is left for the smart helpers (step 7).
- Step 6 (motion and video): done 2026-11-18. `motion.py` (tracks, 8 easings, 12 in/out presets, keyframe parsing); every item carries `anim`; `VideoItem` (frames follow time); scenes carry fps and duration; `render(t=...)` and `render_frames` (layout once per animation; static items with effects drawn once and moved). `video.py` streams frames to ffmpeg: MP4 H.264, ProRes 4444 MOV (alpha), VP9 WebM (alpha), GIF, plus audio. Nodes Timeline, Animate In / Out, Animate, Add Video, Video to Scene, Render Frame, Render Animation, Save Video. Drawing surfaces are now premultiplied (much faster blending and readback). Examples `motion` and `video_overlay`. VideoHelperSuite compatibility (IMAGE batches + fps) is by design but not yet tested: VHS is not installed in the sandbox.
- Step 7 (smart helpers): done 2026-11-18. `smart.py`: busyness map (Sobel edges + local contrast, torch), quiet box search (integral image; anywhere or 9 positions), ink bounds, readability (WCAG per text against the pixels behind its glyphs, 10th percentile; large-text rule), scrims solved by bisection for the weakest opacity reaching a target. `devices.py`: CPU, or "gpu when free" behind an optional HTTP gate (`gpu_gate`); falls back to the CPU with the reason. `copywriter.py`: Ollama `/api/generate` client with task prompts and variant parsing. Nodes Auto Place, Find Quiet Area, Readability Check, Smart Scrim, Copy Writer (Ollama); Palette from Image gains a device option (k-means on torch). No models are bundled or chosen: GPU modes are tensor maths only, and the copy model is the user's pick. Examples `smart` and `copy_variants` (needs a model name).
- Step 8 (PDF and CMYK print): done 2026-11-18. `cmyk.py` (ImageCms sRGB→CMYK with intent and black point compensation; uncalibrated fallback; exact overrides and pure black for vector colours; soft proof). `printpdf.py` converts skia's PDF: `rg`/`RG`/DeviceRGB `sc` → `k`/`K`, shadings (type 2/3 functions), RGB images through the profile, transparency groups to DeviceCMYK; TrimBox/BleedBox, crop marks in registration colour, OutputIntent with the profile; vector or flatten. `to_pdf` now draws shadows/glows/outlines as their own layer so text stays vector, and rasterises effects at the print dpi (skia's default was 72). Nodes Save Print PDF (CMYK), Soft Proof (CMYK), CMYK Values; Canvas presets with bleed. Example `print`.

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
