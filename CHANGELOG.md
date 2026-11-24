# Changelog

## Unreleased

- **Fix: a batch count above 1 gave only one result** with Palette Generator
  (`new_each_run`) or Fluid Gradient (`randomize`).
  - **Cause:** the new colours or look were made once per click of Run, but ComfyUI
    builds every prompt of a batch inside that one click. All the prompts were the
    same, and ComfyUI reused the first result for the rest.
  - **Fix:** a batch of N is now queued as N single prompts, with a new set or look
    made before each. Normal seeds still step once per prompt.
  - New shared `web/before_run.js`. Checked with a batch of 3: three different
    prompts, three results.
- **Fix: Palette Generator settings moved down one place after reopening a workflow**
  (so it came back locked). ComfyUI frontend 1.51.9 saved a blank slot for the
  Generate button and skipped it when loading. The node now saves without the slot and
  repairs workflows that were saved with it.
- **Fluid Gradient: random looks.** A **🎲 Random look** button, and a `randomize`
  toggle (optional, last in the file, shown under `preset`) for a new look just
  before each run.
  - **Where the look comes from:** the server picks it (`fluid.random_look`, served at
    `/cratenode/fluid_random`) and the browser writes it into the node's own fields
    before the run. The queued prompt therefore carries what the node shows, and
    unticking keeps the look.
  - **Kept good-looking:**
    - about a third start from a preset;
    - colours come from Palette Generator harmonies, with blue, purple, pink and
      orange bases favoured, and flat, grey, brown or clashing-green sets rejected;
    - mesh and twirl only get neighbouring hues;
    - each style's settings stay in ranges tuned on contact sheets.
  - **Left alone:** linked fields, and the colours when a palette is connected.
- **Palette Generator** node: five colours as separate outputs (color_1..color_5),
  plus a palette and swatches.
  - **Making colours:** pick a harmony (random, analogous, complementary, split
    complementary, triadic, tetradic, monochromatic, warm and cool), a colour family
    and a style. A **Generate palette** button on the node makes a new set without
    running (`/cratenode/palette`).
  - **On each run:** with `new_each_run` on, a new set is made in the browser just
    before each run, so the run uses exactly the colours shown and saved.
  - **Lock:** `locked` keeps the colours. The button greys out, and runs don't change
    them.
  - New `palettegen.py`, `web/palette_generator.js` and `tests/test_palettegen.py`.
- **Live previews use linked colours** where they can be known before running: a
  primitive node's value (through reroutes too), or Random Colour's colour for its
  current seed. For example, a Fluid Gradient fed by Random Colour now previews with
  that colour and follows it as it changes. Other links keep the widget's value.
- **Fix: a live preview could be drawn outside its node** (offset to the right, seen
  on frontend 1.51.9 after runs). The preview now uses the node's real width and
  never draws past the node.
- **Random Colour** node (Colour group): a random colour on every run, from a seed
  that moves on after each run (set it to fixed to keep one). It is limited by:
  - **family:** red, orange, yellow, green, teal, blue, purple, pink, warm, cool,
    brown, earth, neutral or any;
  - **style:** vivid, pastel, muted, dark, light, neon, jewel or any;
  - **brightness:** a perceived-brightness range (CIE L*, so yellow and blue are
    judged fairly);
  - **contrast:** optionally a minimum WCAG contrast against a background colour.

  `count` makes a palette of colours kept apart. Outputs are `color` (hex), `palette`,
  `swatches` and a `report` that also says when limits couldn't all be met (the
  closest colour is used instead of failing). It has a live preview of the colours the
  current seed gives. New `cratenode_comfy/randcolor.py` and `tests/test_randcolor.py`.
- **Fluid Gradient presets:** 18 ready-made looks (Twirl, Controlled, Strange, Liquid,
  Generator, Abstract, Color, Motion Blur, Abstract Glass, Aurora, Sunset Silk, Lava,
  Neon Marble, Holographic, Ocean, Midnight, Candy, Mono Silk).
  - **In the browser:** the new `preset` input is shown at the top. Picking a preset
    fills in the style, colours and settings to tweak from; editing any of them sets
    it back to `custom`.
  - **On the server and through the API:** a preset name applies that look, and a
    connected palette still supplies the colours.
  - **Saved workflows:** the input is optional and last in the file, so they load
    unchanged.
  - New `/cratenode/fluid_presets` endpoint and `web/fluid_presets.js`. The display-only
    reordering in `live_preview.js` can now put a setting first.
- **Fluid Gradient** node (Fill): flowing abstract gradient fills for canvases,
  shapes and text.
  - **Styles:** mesh blobs, liquid marbling, twirl, strange, waves, motion blur and
    glass.
  - **Controls:** up to six colours (or a palette), a seed and more than 20 settings
    (scale, warp, detail, softness, bands, blobs, twirl with centre and radius,
    rotation, stretch, motion blur and angle, glass, grain, brightness, contrast,
    saturation, hue shift, vignette, evolve).
  - **Behaves like a gradient:** it is a `Gradient` subclass, so recolouring, fill
    opacity, templates, text fills and backgrounds work with it unchanged.
  - **Rendering:** numpy, deterministic per seed and relative to the box it fills.
  - It has a live preview. New example **fluid_gradient**. `cratenode_comfy/fluid.py`,
    `tests/test_fluid.py`.
- **Stack, Place, Grid: `x`, `y`, `box_width`, `box_height` are greyed out unless
  `area` is `custom`**, the only setting that uses them (with safe area or canvas they
  were silently ignored). Tooltips now say so. Display only: values are still saved
  and nothing renders differently. `web/area_fields.js`; checked on frontends 1.51.9
  and 1.55.
- **Grid: `placement`.** `within cell` is the grid as before. `on grid line` centres
  each part on the cell line that align/valign names: left/top on the cell's first
  line, right/bottom on its last, center/middle on its centre. Parts then sit on the
  lines and their crossings.
  - It is optional and last in the file (shown under valign), so saved workflows and
    templates keep their layout.
  - The Grid live preview now draws its guides under the parts.
- **Grid: `direction`** (vertical / horizontal). Vertical is the grid as before: rows
  filled left to right, growing down. Horizontal fills columns top to bottom and grows
  to the right, with the count meaning parts per column (the field is labelled "rows"
  then). It is optional and last in the file, so saved workflows and templates keep
  their layout; it is shown under the count, and the live preview follows.
- **Shape: stroke styles and a stroke editor.** New optional `stroke_style` input,
  last in the file and shown under `stroke_width`. Saved workflows keep their values,
  and an empty style draws as before.
  - **Styles:** alignment (centre, inside, outside), dash patterns with an offset,
    round, flat or square ends, round, sharp or bevel corners, a second (double) line
    inside or outside with its own width and gap, and drawing the stroke behind the
    fill. All lengths are in stroke widths.
  - **Editor:** clicking the field opens a pop-out with 14 presets drawn as samples,
    the width, and every setting. The node's live preview follows, and Escape undoes.
  - **Rendering:** strokes are built as vector outlines (skia path ops), so they stay
    vector in PDFs.
  - **Fix:** layers and crops now allow for how far a stroke reaches past the shape,
    so a thick stroke on a shape with a shadow or opacity is no longer cut off at
    the box.
  - New `cratenode_comfy/stroke.py`, `web/stroke_editor.js` and `tests/test_stroke.py`.
- **Grid has a live preview:** numbered stand-in tiles of different sizes (one per
  connected part, six if none), the cells and the area, on a 1920 x 1080 stand-in
  canvas, following columns, gaps, align/valign and area as they change.
- **Colour picker: Swatches tab** next to RGB and HSL: a honeycomb of 127 colours
  (white in the middle, hues around it, deeper towards the edge) and 13 greys; click
  one to use it (opacity is kept). The current colour's cell is outlined.
- **Colour picker opens from the whole field**, not just the chip; type a hex code
  in the picker's box (applied as you type, Enter keeps it, an incomplete code is
  marked red and ignored).
- **Colour picker on hex colour fields.** Each colour field shows a chip with its
  colour; clicking it opens a picker with RGB sliders (default) or HSL, opacity, a
  hex box, an eyedropper where the browser has one, recent colours and buttons for
  special values (Transparent, Auto, None). The field and live preview update while
  dragging; Escape reverts. The value stays plain hex text, so saved workflows and
  prompts are unchanged. `web/color_picker.js`; checked on frontends 1.51.9 and 1.55.
- **Shape shows `fill_opacity` right under `color`.** Only the display order changes
  (in the browser): saved workflows keep the node's own order, so files saved before
  and after `fill_opacity` existed load the same values. Checked on frontends 1.51.9
  and 1.55.
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
