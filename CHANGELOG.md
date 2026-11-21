# Changelog

## Unreleased

- **Canvas: `transparent`** toggle (last, optional) for designs with no background
  (overlays, logos, PNG/WebP/MOV with alpha); `background` also accepts the word
  `transparent`. It overrides the colour and fill.
- **Live previews are drawn on the node itself** (like ComfyUI's own widgets) instead
  of an HTML element over the canvas. On frontend 1.51.9 that element drifted away
  from the node after it was moved or resized (seen on Canvas). The preview is still
  left out of saved workflows and prompts.
- README troubleshooting: refresh the browser tab if the nodes don't show after
  installing.
- **Clear install errors:** when skia-python, pypdf or numpy is missing, the pack
  now says which and prints the pip command for the Python running ComfyUI, instead
  of a bare "IMPORT FAILED". README has a **Troubleshooting** section (missing
  packages per install type, ICU data on Windows, Linux libraries, fonts, ffmpeg,
  live previews, black renders). Checked on ComfyUI 0.34.0 as well as 0.42.5.
- **Shape: `fill_opacity`** (0–1, default 1) fades the fill (colour or gradient)
  without touching the outline; 0 with a stroke makes an outline-only shape. It is
  the last input, so saved workflows keep their values.
- **Security hardening** (from a review of the whole repository and its history):
  Data Rows, Load Template and Brand Kit read files only from the data folder,
  ComfyUI's input folder, the package and `data_roots`; Copy Writer calls only this
  machine unless `allowed_hosts` lists another; the live-preview endpoint limits
  request size and text length; the CI job gets a read-only token. A client name in
  a test is replaced with a made-up one. New `SECURITY.md`.
- **Image to Scene** brings generations back into designs: with a scene connected,
  the image goes under the design, on top of it, or replaces it while keeping the
  canvas (size, safe area, frame rate), fitted by fill / fit / stretch; a batch can
  give one design per image (a list output). New inputs are optional, so earlier
  workflows load unchanged. New example **image_round_trip**.
- **Scene to Image** node: converts a design into IMAGE + MASK for other pipelines,
  sized by scale, fit width / height / inside, or an exact (stretched) size, rounded
  to a multiple of 8–64 for diffusion latents, with transparency kept or flattened
  onto a colour, at any moment of an animation. Rendered sharp at the output size;
  faint edge pixels keep a clean colour when the IMAGE is used without its mask.
  Render Scene and Scene to Image are found by searching "scene to image". New
  example **scene_to_image**.
- **Live previews on the nodes** before running: Canvas, Text Box, Shape, Linear and
  Radial Gradient, Palette, Safe Area, Contrast Check and the effect nodes show a
  picture under their settings that updates as they change. `web/live_preview.js`
  posts the node's widget values to `/cratenode/preview`, which runs the node's own
  code and returns a small PNG (effects on a sample "Aa"; text cropped to its
  letters; a dark checkerboard behind light content). Not saved into workflows.
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
