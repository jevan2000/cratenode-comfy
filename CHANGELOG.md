# Changelog

## Unreleased

- **Preview Scene** node: a quick preview of the design so far, anywhere in a chain
  (the scene passes through). Transparency over a checkerboard or a solid colour,
  optional guides (safe area, item outlines; preview only), any moment of an
  animation, and an `info` line (size, items, duration). Used in the thumbnail and
  motion examples.
- Two more examples, so every node is used by at least one: **layers_blend**
  (Palette, Safe Area, Opacity & Blend, Blur, Layers) and **keyframes** (Animate,
  Add Video, Render Animation, Save Video from a frame batch).
- `install_sandbox.ps1 -Workflows` copies the examples into ComfyUI's Workflows
  sidebar; `make_thumbnails.py` grabs video frames itself.

## 1.0.0 (2026-11-18)

The first release: 49 nodes in 13 groups. See [docs/nodes.md](docs/nodes.md).

- **Model:** designs flow as a vector scene (`CN_SCENE`) and render sharp at any
  scale; Render Scene / Add Image / Image to Scene convert to and from IMAGE + MASK.
- **Canvas, type, shapes, layout, effects:** canvas presets (social, video, print
  with bleed), safe areas, gradients, Text Box (fonts from your folders, wrapping,
  auto-fit, `*bold*`, gradient text), shapes, Stack / Place / Grid / Layers that
  measure content (a longer title pushes the rest down), drop shadow, outer glow,
  outline, blur, opacity and 17 blend modes, clip to previous.
- **Export:** PNG, JPEG, WebP with transparency or a matte, DPI, sRGB profile,
  workflow metadata and a file-size budget; vector PDF.
- **Templates and data:** save, load and fill JSON templates (slots,
  `{placeholders}`, image slots, colour names); CSV/JSON rows run the graph once per
  row; `{column}` filenames.
- **Colour:** palettes, palette from image, brand kits, picking colours by name or
  contrast, WCAG contrast check, recolouring a design.
- **Motion and video:** timeline, entrance/exit presets with stagger, keyframes with
  easing, video inside designs and designs over video, frames as IMAGE batches,
  Save Video (MP4, ProRes 4444 and WebM with alpha, GIF, with audio).
- **Smart helpers:** auto-placement in calm areas, readability check against the
  pixels behind the letters, just-enough scrims, copy variants from a local Ollama
  model; optional GPU mode behind a gate.
- **Print:** CMYK PDFs (vector text, exact CMYK values, profile conversion, bleed,
  crop marks, output intent), soft proof, CMYK values.
- **Fonts:** licence warnings (never errors) for fonts used outside their licence.
- **Examples:** twelve workflows in ComfyUI's Templates browser (`example_workflows/`)
  and as API files (`api_examples/`) with placeholder assets.
