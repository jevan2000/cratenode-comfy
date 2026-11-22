# Node reference

All 52 nodes, generated from the node definitions by `tools/gen_node_docs.py`.
Types: *scene* is a design (`CN_SCENE`), *fill* a gradient, *data row* one CSV/JSON row, *palette* a named colour palette.

- [Canvas](#canvas)
- [Colour](#colour)
- [Data](#data)
- [Effects](#effects)
- [Fill](#fill)
- [Image](#image)
- [Layout](#layout)
- [Motion](#motion)
- [Output](#output)
- [Print](#print)
- [Shapes](#shapes)
- [Smart](#smart)
- [Type](#type)

## Canvas

### Canvas

`CNCanvas`. Start a design: size (preset or custom), background colour, fill or transparent, and safe-area margins.

| Input | Type | Default | Notes |
|---|---|---|---|
| `preset` | choice | `YouTube thumbnail / HD 1920x1080` |  |
| `landscape_flip` | boolean | `false` | Swap width and height |
| `width` | int | `1920` | Used when preset is custom |
| `height` | int | `1080` | Used when preset is custom |
| `background` | string | `#000000` | #rrggbb or #rrggbbaa, or 'transparent' |
| `safe_margin` | float | `5.0` | Safe area inset, % of the shorter side (layout nodes can use it) |
| `background_fill` | fill (optional) |  | A gradient; replaces the background colour |
| `transparent` | boolean (optional) | `false` | No background: overlays, logos, PNG/WebP/MOV with alpha. Overrides the background colour and fill |

Outputs: `scene` (scene)

### Safe Area

`CNSafeArea`. Set the safe-area margins in pixels (layout nodes with area = safe area use them).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `left` | float | `96.0` |  |
| `top` | float | `96.0` |  |
| `right` | float | `96.0` |  |
| `bottom` | float | `96.0` |  |

Outputs: `scene` (scene)

## Colour

### Brand Kit

`CNBrandKit`. A brand kit (JSON in your data folder's brand/): its palette, heading and body fonts, and a logo. Wire the fonts into a Text Box's font_override and the logo into Add Image (set its mask_meaning to alpha).

| Input | Type | Default | Notes |
|---|---|---|---|
| `kit` | choice | `example` |  |
| `path` | string | `""` | Any brand kit file; used instead of the list when set |
| `logo` | string | `primary` | Which logo of the kit |

Outputs: `palette` (palette), `heading_font` (string), `heading_weight` (int), `body_font` (string), `body_weight` (int), `logo` (image), `logo_alpha` (mask), `swatches` (image), `notes` (string)

### Contrast Check

`CNContrast`. WCAG contrast ratio of text on a background. Body text needs 4.5:1 (AA), large text 3:1.

| Input | Type | Default | Notes |
|---|---|---|---|
| `text_color` | string | `#ffffff` |  |
| `background` | string | `#1f6feb` |  |
| `large_text` | boolean | `false` | 24px+, or 18.7px+ bold |
| `palette` | palette (optional) |  | Lets the colours be palette names |

Outputs: `ratio` (float), `grade` (string)

### Palette

`CNPalette`. A named colour palette: 'name: #hex' lines, or plain #hex values (named color_1, ...).

| Input | Type | Default | Notes |
|---|---|---|---|
| `colors` | string | `primary: #1f6feb / secondary: #0b1d3a / …` |  |
| `name` | string | `""` |  |

Outputs: `palette` (palette), `swatches` (image)

### Palette from Image

`CNPaletteFromImage`. The main colours of an image (k-means in Lab colour space, CPU). Similar colours merge; transparent pixels (by the mask) are ignored.

| Input | Type | Default | Notes |
|---|---|---|---|
| `image` | image |  |  |
| `mask_meaning` | choice | `LoadImage (1 = transparent)` |  |
| `count` | int | `5` |  |
| `sort` | choice | `by share` |  |
| `min_distance` | float | `8.0` | Merge colours closer than this (ΔE; ~2 is barely visible) |
| `seed` | int | `0` |  |
| `mask` | mask (optional) |  |  |
| `device` | choice (optional) | `cpu` | gpu when free: asks the GPU gate first, else runs on the CPU |

Outputs: `palette` (palette), `swatches` (image), `report` (string)

### Pick Color

`CNPickColor`. One palette colour as #hex text, to wire into any colour input: by name or number, the most readable against another colour, or the lightest / darkest.

| Input | Type | Default | Notes |
|---|---|---|---|
| `palette` | palette |  |  |
| `mode` | choice | `by name or number` |  |
| `name` | string | `primary` | A colour name, or its number (1 = first) |
| `against` | string | `#000000` | For best contrast: the background (#hex or a palette name) |

Outputs: `color` (string), `report` (string)

### Recolor Scene

`CNRecolor`. Swap colours throughout a design (text, shapes, strokes, gradients, effects, background): '#from -> #to' lines; with a palette, either side can be a colour name.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `mapping` | string | `#ffffff -> accent` |  |
| `tolerance` | float | `0.02` | How close a colour must be (per channel, 0..1) to be swapped |
| `palette` | palette (optional) |  |  |

Outputs: `scene` (scene), `report` (string)

## Data

### Data Rows

`CNDataRows`. Rows from a CSV (with a header line) or JSON file, or pasted text. The row output is a list, so everything after it runs once per row (one design per row).

| Input | Type | Default | Notes |
|---|---|---|---|
| `file` | string | `""` | CSV/JSON path; relative paths look in the data folder |
| `text` | string | `""` | Pasted CSV or JSON, used when file is empty |
| `format` | choice | `auto` |  |
| `start` | int | `0` | First row (0 = the first) |
| `limit` | int | `0` | How many rows; 0 = all |

Outputs: `row` (data row, list), `count` (int), `columns` (string)

### Fill Template

`CNFillTemplate`. Replace slot text (by slot name), colours (name.color) and {placeholders} from a data row and/or the values box, and image slots from images. Layouts reflow to the new text.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `values` | string | `""` | key: value lines or a JSON object; these win over the row |
| `mask_meaning` | choice | `LoadImage (1 = transparent)` |  |
| `slot_1` | string | `""` | The image slot image_1 replaces |
| `slot_2` | string | `""` | The image slot image_2 replaces |
| `slot_3` | string | `""` | The image slot image_3 replaces |
| `row` | data row (optional) |  |  |
| `palette` | palette (optional) |  | Lets colour values be palette names (title.color: accent) |
| `image_1` | image (optional) |  |  |
| `mask_1` | mask (optional) |  |  |
| `image_2` | image (optional) |  |  |
| `mask_2` | mask (optional) |  |  |
| `image_3` | image (optional) |  |  |
| `mask_3` | mask (optional) |  |  |

Outputs: `scene` (scene), `report` (string)

### Load Template

`CNLoadTemplate`. A saved design (JSON) as a scene. Templates come from your data folder's templates/ and the bundled examples. Fill it with Fill Template.

| Input | Type | Default | Notes |
|---|---|---|---|
| `template` | choice | `thumbnail` |  |
| `path` | string | `""` | Any template file; used instead of the list when set |

Outputs: `scene` (scene), `slots` (string)

### Row Value

`CNRowValue`. One column of a data row as text, to wire into any text input (e.g. a Text Box).

| Input | Type | Default | Notes |
|---|---|---|---|
| `row` | data row |  |  |
| `column` | string | `title` |  |
| `default` | string | `""` | Used when the column is missing or empty |

Outputs: `text` (string)

### Save as Template

`CNSaveTemplate`. Write a design to a template JSON (images embedded). Give items a 'slot' name so Fill Template can change them, or put {placeholders} in text.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `name` | string | `my-template` | File name; a/b makes a subfolder |
| `description` | string | `""` |  |
| `folder` | choice |  | The data folder is set in config (data_dir); without one, output is used |
| `overwrite` | boolean | `false` |  |

Outputs: `path` (string)

## Effects

### Blur

`CNBlur`. Blur the item (or the whole scene so far, e.g. a background).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `target` | choice | `last item` | last item: the item added just before; whole scene: everything so far, as one |
| `radius` | float | `12.0` |  |

Outputs: `scene` (scene)

### Clip to Previous

`CNClipToPrevious`. Show the last item only where the item before it is (a clipping mask): e.g. a photo inside text, or a texture inside a shape.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `clip` | boolean | `true` |  |

Outputs: `scene` (scene)

### Drop Shadow

`CNDropShadow`. A soft shadow under the item (or the whole scene).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `target` | choice | `last item` | last item: the item added just before; whole scene: everything so far, as one |
| `dx` | float | `0.0` |  |
| `dy` | float | `8.0` |  |
| `blur` | float | `24.0` |  |
| `color` | string | `#000000` |  |
| `opacity` | float | `0.6` |  |

Outputs: `scene` (scene)

### Opacity & Blend

`CNOpacityBlend`. Opacity and blend mode (multiply, screen, overlay, ...) of the item or the whole scene.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `target` | choice | `last item` | last item: the item added just before; whole scene: everything so far, as one |
| `opacity` | float | `1.0` |  |
| `blend` | choice | `normal` |  |

Outputs: `scene` (scene)

### Outer Glow

`CNOuterGlow`. A soft glow around the item; spread grows it before blurring.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `target` | choice | `last item` | last item: the item added just before; whole scene: everything so far, as one |
| `blur` | float | `24.0` |  |
| `spread` | float | `0.0` |  |
| `color` | string | `#ffffff` |  |
| `opacity` | float | `0.8` |  |

Outputs: `scene` (scene)

### Outline

`CNOutline`. A solid outline around the item's shape (text, cut-out images, shapes).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `target` | choice | `last item` | last item: the item added just before; whole scene: everything so far, as one |
| `width` | float | `6.0` |  |
| `color` | string | `#000000` |  |
| `opacity` | float | `1.0` |  |

Outputs: `scene` (scene)

## Fill

### Fluid Gradient

`CNFluidGradient`. A flowing, abstract gradient fill (mesh blobs, liquid, twirl, strange marbling, waves, motion blur, glass) for canvases, shapes and text. Same settings + seed = same picture; change the seed for a new one.

| Input | Type | Default | Notes |
|---|---|---|---|
| `style` | choice | `liquid` | mesh: soft colour blobs. liquid: silky flowing marble. twirl: a swirl. strange: tight psychedelic marbling. waves: flowing stripes. motion blur: streaked flow. glass: liquid glass with highlights |
| `color_1` | string | `#ff5a1f` | #rrggbb[aa] or a palette name; empty = unused |
| `color_2` | string | `#ff2fa0` | #rrggbb[aa] or a palette name; empty = unused |
| `color_3` | string | `#7a2cff` | #rrggbb[aa] or a palette name; empty = unused |
| `color_4` | string | `#1b3cff` | #rrggbb[aa] or a palette name; empty = unused |
| `color_5` | string | `#13d3ff` | #rrggbb[aa] or a palette name; empty = unused |
| `color_6` | string | `""` | #rrggbb[aa] or a palette name; empty = unused |
| `seed` | int | `0` | A different seed gives a different arrangement |
| `scale` | float | `1.0` | Feature size: larger = bigger, calmer shapes |
| `warp` | float | `1.0` | How much the shapes flow and bend (times the style's own amount) |
| `detail` | int | `3` | Noise layers: more = finer ripples |
| `softness` | float | `1.0` | How softly colours blend; lower = crisper edges |
| `bands` | float | `0.0` | Extra repeats of the colours: ripples and stripes |
| `blobs` | int | `2` | mesh / twirl: points per colour |
| `twirl` | float | `0.0` | Degrees of swirl, added to the style's own |
| `twirl_x` | float | `0.5` | Swirl centre across the fill (0 = left, 1 = right) |
| `twirl_y` | float | `0.5` | Swirl centre down the fill (0 = top, 1 = bottom) |
| `twirl_radius` | float | `0.6` | How far the swirl reaches, in fill heights |
| `rotation` | float | `0.0` | Turns the whole pattern |
| `stretch` | float | `1.0` | Above 1 stretches the shapes sideways, below 1 upright |
| `blur` | float | `0.0` | Motion blur length in fill heights, added to the style's own |
| `blur_angle` | float | `0.0` | Motion blur direction; 0 = left to right |
| `glass` | float | `0.0` | Glassy highlights and refraction, added to the style's own |
| `grain` | float | `0.02` | Film grain (also hides banding) |
| `brightness` | float | `0.0` | Lighter or darker |
| `contrast` | float | `1.0` | 1 = as the colours are |
| `saturation` | float | `1.0` | 0 = grey, 1 = as the colours are |
| `hue_shift` | float | `0.0` | Turns every colour around the colour wheel |
| `vignette` | float | `0.0` | Darker edges |
| `evolve` | float | `0.0` | Moves through the pattern; animate or step it for a flowing gradient |
| `palette` | palette (optional) |  | Use these colours (in order) instead of color_1..6, or resolve colour names |
| `preset` | choice (optional) | `custom` | A ready-made look. Picking one fills in the style, colours and settings above; change any of them and this goes back to 'custom'. A connected palette still supplies the colours. |

Outputs: `fill` (fill)

### Linear Gradient

`CNLinearGradient`. A gradient fill for canvases, shapes and text. Angle 90 = top to bottom.

| Input | Type | Default | Notes |
|---|---|---|---|
| `angle` | float | `90.0` |  |
| `color_1` | string | `#0b1020` | #rrggbb[aa]; empty = unused |
| `position_1` | float | `0.0` |  |
| `color_2` | string | `#0f3b40` | #rrggbb[aa]; empty = unused |
| `position_2` | float | `1.0` |  |
| `color_3` | string | `""` | #rrggbb[aa]; empty = unused |
| `position_3` | float | `0.5` |  |
| `color_4` | string | `""` | #rrggbb[aa]; empty = unused |
| `position_4` | float | `0.75` |  |

Outputs: `fill` (fill)

### Radial Gradient

`CNRadialGradient`. A gradient from the centre of whatever it fills outward.

| Input | Type | Default | Notes |
|---|---|---|---|
| `color_1` | string | `#ffffff` | #rrggbb[aa]; empty = unused |
| `position_1` | float | `0.0` |  |
| `color_2` | string | `#000000` | #rrggbb[aa]; empty = unused |
| `position_2` | float | `1.0` |  |
| `color_3` | string | `""` | #rrggbb[aa]; empty = unused |
| `position_3` | float | `0.5` |  |
| `color_4` | string | `""` | #rrggbb[aa]; empty = unused |
| `position_4` | float | `0.75` |  |

Outputs: `fill` (fill)

## Image

### Add Image

`CNAddImage`. Put an image (e.g. an AI background or a logo) into a box: fit, fill (crop) or stretch. Box size 0 = to the canvas edge.

| Input | Type | Default | Notes |
|---|---|---|---|
| `image` | image |  |  |
| `mask_meaning` | choice | `LoadImage (1 = transparent)` |  |
| `mode` | choice | `fill` |  |
| `x` | float | `0.0` |  |
| `y` | float | `0.0` |  |
| `box_width` | float | `0.0` |  |
| `box_height` | float | `0.0` |  |
| `batch_index` | int | `0` | Which image of a batch to use |
| `below_previous` | boolean | `false` | Sit under the previous item (its bottom + gap) instead of at y |
| `gap` | float | `24.0` |  |
| `scene` | scene (optional) |  |  |
| `mask` | mask (optional) |  |  |
| `slot` | string (optional) | `""` | A name for this item in a template (Fill Template replaces its text, image or colour by this name) |

Outputs: `scene` (scene)

### Image to Scene

`CNImageToScene`. Bring an image (an AI generation, a photo, any IMAGE) into a design. Without a scene: a new canvas the image's size. With a scene: the image goes under the design (an AI background behind sharp type), on top of it, or replaces it while keeping the canvas, fitted to the canvas (fill crops, fit letterboxes). A batch can give one design per image (a list: the rest of the graph runs once per image).

| Input | Type | Default | Notes |
|---|---|---|---|
| `image` | image |  |  |
| `mask_meaning` | choice | `LoadImage (1 = transparent)` |  |
| `safe_margin` | float | `5.0` | For a new canvas |
| `mask` | mask (optional) |  |  |
| `scene` | scene (optional) |  | Put the image into this design |
| `place` | choice (optional) | `new canvas (image size)` | Where the image goes when a scene is connected |
| `fit` | choice (optional) | `fill` | How the image covers the canvas: fill crops, fit letterboxes |
| `batch` | choice (optional) | `one image (batch_index)` |  |
| `batch_index` | int (optional) | `0` | Which image of a batch, for 'one image' |
| `slot` | string (optional) | `""` | A name for the image item (an image slot in a template) |

Outputs: `scene` (scene, list)

## Layout

### Grid

`CNGrid`. Parts in equal cells, left to right then top to bottom.

| Input | Type | Default | Notes |
|---|---|---|---|
| `columns` | int | `3` |  |
| `gap_x` | float | `24.0` |  |
| `gap_y` | float | `24.0` |  |
| `align` | choice | `center` |  |
| `valign` | choice | `middle` |  |
| `area` | choice | `safe area` | Where to place: the safe area, the whole canvas, or the custom box below |
| `x` | float | `0.0` | Custom area only: the box's left edge, in canvas pixels |
| `y` | float | `0.0` | Custom area only: the box's top edge, in canvas pixels |
| `box_width` | float | `0.0` | Custom area only: the box's width; 0 = to the canvas edge |
| `box_height` | float | `0.0` | Custom area only: the box's height; 0 = to the canvas edge |
| `scene` | scene (optional) |  |  |
| `part_1` | scene (optional) |  |  |
| `part_2` | scene (optional) |  |  |
| `part_3` | scene (optional) |  |  |
| `part_4` | scene (optional) |  |  |
| `part_5` | scene (optional) |  |  |
| `part_6` | scene (optional) |  |  |
| `part_7` | scene (optional) |  |  |
| `part_8` | scene (optional) |  |  |
| `part_9` | scene (optional) |  |  |
| `direction` | choice (optional) | `vertical` | vertical: parts fill each row left to right and the grid grows down (columns = parts per row). horizontal: parts fill each column top to bottom and the grid grows to the right (the count is parts per column, shown as 'rows'). |
| `placement` | choice (optional) | `within cell` | within cell: each part sits inside its cell at align/valign. on grid line: each part is centred on the cell line that align/valign names (left/top = the cell's first line, right/bottom = its last, center/middle = its centre), so parts sit on the grid lines and their crossings. |

Outputs: `scene` (scene)

### Layers

`CNLayers`. Put scenes on top of each other where they are (layer_1 at the bottom).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene (optional) |  | The bottom layer and the canvas |
| `layer_1` | scene (optional) |  |  |
| `layer_2` | scene (optional) |  |  |
| `layer_3` | scene (optional) |  |  |
| `layer_4` | scene (optional) |  |  |
| `layer_5` | scene (optional) |  |  |
| `layer_6` | scene (optional) |  |  |

Outputs: `scene` (scene)

### Place

`CNPlace`. Move a part into an area at an alignment (e.g. a logo bottom-right of the safe area).

| Input | Type | Default | Notes |
|---|---|---|---|
| `part` | scene |  |  |
| `align` | choice | `right` |  |
| `valign` | choice | `bottom` |  |
| `area` | choice | `safe area` | Where to place: the safe area, the whole canvas, or the custom box below |
| `x` | float | `0.0` | Custom area only: the box's left edge, in canvas pixels |
| `y` | float | `0.0` | Custom area only: the box's top edge, in canvas pixels |
| `box_width` | float | `0.0` | Custom area only: the box's width; 0 = to the canvas edge |
| `box_height` | float | `0.0` | Custom area only: the box's height; 0 = to the canvas edge |
| `scene` | scene (optional) |  |  |

Outputs: `scene` (scene)

### Stack

`CNStack`. Lay parts out in a column or row with a gap, then place the group in an area. A part that grows (a wrapped title) pushes the ones after it.

| Input | Type | Default | Notes |
|---|---|---|---|
| `direction` | choice | `vertical` |  |
| `gap` | float | `24.0` |  |
| `align` | choice | `center` |  |
| `valign` | choice | `middle` |  |
| `area` | choice | `safe area` | Where to place: the safe area, the whole canvas, or the custom box below |
| `x` | float | `0.0` | Custom area only: the box's left edge, in canvas pixels |
| `y` | float | `0.0` | Custom area only: the box's top edge, in canvas pixels |
| `box_width` | float | `0.0` | Custom area only: the box's width; 0 = to the canvas edge |
| `box_height` | float | `0.0` | Custom area only: the box's height; 0 = to the canvas edge |
| `scene` | scene (optional) |  | Add the stack to this scene |
| `part_1` | scene (optional) |  |  |
| `part_2` | scene (optional) |  |  |
| `part_3` | scene (optional) |  |  |
| `part_4` | scene (optional) |  |  |
| `part_5` | scene (optional) |  |  |
| `part_6` | scene (optional) |  |  |

Outputs: `scene` (scene)

## Motion

### Add Video

`CNAddVideo`. Put video frames (an IMAGE batch, e.g. from VideoHelperSuite's Load Video) into a box; the frame follows the design's time. Box size 0 = to the canvas edge.

| Input | Type | Default | Notes |
|---|---|---|---|
| `frames` | image |  |  |
| `mask_meaning` | choice | `LoadImage (1 = transparent)` |  |
| `fps` | float | `30.0` | The frames' own frame rate |
| `mode` | choice | `fill` |  |
| `x` | float | `0.0` |  |
| `y` | float | `0.0` |  |
| `box_width` | float | `0.0` |  |
| `box_height` | float | `0.0` |  |
| `start` | float | `0.0` | Seconds before it starts |
| `loop` | boolean | `false` | Repeat; otherwise hold the last frame |
| `below_previous` | boolean | `false` | Sit under the previous item (its bottom + gap) instead of at y |
| `gap` | float | `24.0` |  |
| `scene` | scene (optional) |  |  |
| `mask` | mask (optional) |  |  |
| `slot` | string (optional) | `""` | A name for this item in a template (Fill Template replaces its text, image or colour by this name) |

Outputs: `scene` (scene)

### Animate

`CNAnimate`. Keyframes for one property of the last item (or everything so far): 'seconds: value' pairs. x / y are pixel offsets, scale 1 = normal, rotation in degrees, opacity 0..1, blur in pixels, wipe 0..1 (reveals left to right).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `target` | choice | `last item` | last item: the item added just before; whole scene: everything so far, as one |
| `property` | choice | `rotation` |  |
| `keyframes` | string | `0: 0 / 2: 360` |  |
| `easing` | choice | `ease in out` |  |
| `stagger` | float | `0.0` |  |

Outputs: `scene` (scene)

### Animate In

`CNAnimateIn`. Make the last item (or everything so far) arrive: fade, slide, pop, zoom, wipe or blur. On a Stack or Grid, stagger plays the parts one after another.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `target` | choice | `last item` | last item: the item added just before; whole scene: everything so far, as one |
| `preset` | choice | `fade up` |  |
| `start` | float | `0.0` | Seconds |
| `duration` | float | `0.6` |  |
| `easing` | choice | `ease out` |  |
| `distance` | float | `80.0` | Pixels, for slides |
| `stagger` | float | `0.0` | Seconds between parts of a Stack / Grid / group |

Outputs: `scene` (scene)

### Animate Out

`CNAnimateOut`. Make the last item (or everything so far) leave: fade, slide, pop, zoom, wipe or blur. On a Stack or Grid, stagger plays the parts one after another.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `target` | choice | `last item` | last item: the item added just before; whole scene: everything so far, as one |
| `preset` | choice | `fade up` |  |
| `start` | float | `3.0` | Seconds |
| `duration` | float | `0.6` |  |
| `easing` | choice | `ease in` |  |
| `distance` | float | `80.0` | Pixels, for slides |
| `stagger` | float | `0.0` | Seconds between parts of a Stack / Grid / group |

Outputs: `scene` (scene)

### Render Animation

`CNRenderAnimation`. All frames as an IMAGE batch + alpha MASK batch (for VideoHelperSuite or any image node). Frames are held in memory: for long or large videos use Save Video, which streams.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `scale` | float | `0.5` |  |
| `fps` | float | `0.0` | 0 = the design's frame rate |
| `start_frame` | int | `0` |  |
| `max_frames` | int | `0` | 0 = all |
| `every_nth` | int | `1` | 2 = every other frame |

Outputs: `frames` (image), `alpha` (mask), `fps` (float)

### Render Frame

`CNRenderFrame`. One moment of an animated design, as IMAGE + alpha MASK.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `time` | float | `1.0` |  |
| `scale` | float | `1.0` |  |

Outputs: `image` (image), `alpha` (mask)

### Save Video

`CNSaveVideo`. Write an animated design (streamed frame by frame) or an IMAGE batch to MP4, ProRes 4444 MOV (alpha), VP9 WebM (alpha) or GIF, with optional audio. Uses ffmpeg.

| Input | Type | Default | Notes |
|---|---|---|---|
| `format` | choice | `mp4 (H.264)` |  |
| `fps` | float | `0.0` | 0 = the design's (or 30) |
| `quality` | int | `80` |  |
| `scale` | float | `1.0` | Designs only |
| `matte` | string | `#000000` | Behind transparency in MP4 |
| `filename_prefix` | string | `cratenode/video` | {column} from a data row, {date}, {time}, {index} |
| `scene` | scene (optional) |  |  |
| `images` | image (optional) |  | Or frames; used when no scene is connected |
| `alpha` | mask (optional) |  | Transparency for images (1 = opaque) |
| `audio` | audio (optional) |  |  |
| `row` | data row (optional) |  |  |

Outputs: `path` (string), `report` (string)

### Timeline

`CNTimeline`. Set a design's length and frame rate. Duration 0 = until the last animation ends + 1 s (or the length of its video).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `duration` | float | `0.0` |  |
| `fps` | float | `30.0` |  |

Outputs: `scene` (scene), `seconds` (float)

### Video to Scene

`CNVideoToScene`. Start a design from video frames: the canvas takes their size, frame rate and length, so anything added on top becomes an overlay.

| Input | Type | Default | Notes |
|---|---|---|---|
| `frames` | image |  |  |
| `fps` | float | `30.0` |  |
| `safe_margin` | float | `5.0` |  |

Outputs: `scene` (scene), `seconds` (float)

## Output

### Export Image

`CNExport`. Save a design (or any IMAGE batch) as PNG, JPEG or WebP. Transparency is kept in PNG/WebP; JPEG is flattened onto the matte colour. max_kb lowers JPEG/WebP quality until the file fits (e.g. 2000 for a YouTube thumbnail). Filename prefix accepts %date:yyyy-MM-dd%-style ComfyUI variables and %width%/%height%.

| Input | Type | Default | Notes |
|---|---|---|---|
| `mask_meaning` | choice | `alpha (1 = opaque)` | Render Scene's alpha is coverage (1 = opaque); Load Image's mask is the reverse |
| `format` | choice | `png` |  |
| `quality` | int | `92` | JPEG and lossy WebP |
| `webp_lossless` | boolean | `false` |  |
| `transparent` | boolean | `true` | Keep transparency (PNG / WebP) |
| `matte` | string | `#ffffff` | Colour behind transparent areas when flattening |
| `scale` | float | `1.0` | Scenes re-render sharp; images are resampled |
| `dpi` | float | `0.0` | Written to PNG/JPEG; 0 = none |
| `max_kb` | int | `0` | File size limit; 0 = none |
| `embed_workflow` | boolean | `true` | PNG / WebP carry the workflow, like Save Image |
| `filename_prefix` | string | `design` | {column} takes a value from the data row; also {date}, {time}, {index} (row number), and ComfyUI's %date:yyyy-MM-dd%, %width%, %height%. a/b makes a subfolder |
| `scene` | scene (optional) |  | A design; rendered at scale |
| `image` | image (optional) |  | Or any IMAGE (batch); used when no scene is connected |
| `alpha` | mask (optional) |  | Transparency for image |
| `row` | data row (optional) |  | A data row for {column} names |

Outputs: `paths` (string), `report` (string)

### Preview Scene

`CNPreviewScene`. See the design so far, anywhere in a chain: the scene passes straight through, and the node shows a quick preview (transparency over a checkerboard). Guides show the safe area and each item's outline; they are only in the preview. For animations, pick a time.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `scale` | float | `0.5` | Preview size; smaller is faster |
| `guides` | choice | `none` |  |
| `background` | choice | `checkerboard` | What shows through transparent areas (preview only) |
| `time` | float | `-1.0` | Seconds into an animation; -1 = at rest (no animation) |

Outputs: `scene` (scene), `info` (string)

### Render Scene

`CNRender`. Turn a design into an IMAGE and its alpha MASK (1 = opaque) for any ComfyUI node. scale 2 renders at twice the canvas size, still sharp.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `scale` | float | `1.0` |  |

Outputs: `image` (image), `alpha` (mask)

### Save PDF

`CNSavePDF`. Vector RGB PDF (text stays text, fonts embedded) in the output folder.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `filename_prefix` | string | `design` | {column} takes a value from the data row; also {date}, {time}, {index} (row number), and ComfyUI's %date:yyyy-MM-dd%, %width%, %height%. a/b makes a subfolder |
| `dpi` | float | `300.0` | Canvas pixels per inch |
| `row` | data row (optional) |  | A data row for {column} names |

Outputs: `path` (string)

### Scene to Image

`CNSceneToImage`. Convert a design into a ComfyUI IMAGE + MASK for any other node: an image-generation pipeline (img2img, ControlNet, inpainting), Save Image, upscalers. Choose the size (scale, fit, exact), round it to a multiple of 8 or 64 for diffusion models, and flatten transparency onto a colour (otherwise it is black in RGB-only nodes). Text and shapes are drawn sharp at the output size.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `size` | choice | `scale` |  |
| `scale` | float | `1.0` | size = scale |
| `width` | int | `1024` | fit width / fit inside / exact size |
| `height` | int | `1024` | fit height / fit inside / exact size |
| `round_to` | choice | `1` | Round width and height to a multiple (8 or 64 for diffusion latents) |
| `transparency` | choice | `keep (IMAGE + alpha MASK)` |  |
| `matte` | string | `#ffffff` | Colour for flatten |
| `time` | float | `-1.0` | Seconds into an animation; -1 = at rest |

Outputs: `image` (image), `mask` (mask), `width` (int), `height` (int)

## Print

### CMYK Values

`CNCMYKValues`. The CMYK a colour will print with (through the profile, or your exact value).

| Input | Type | Default | Notes |
|---|---|---|---|
| `color` | string | `#1f6feb` | #hex, or a palette colour name |
| `profile` | choice | `(config)` | The CMYK ICC profile: the one in the config (cmyk_profile), one found in the data folder's color/ or the system colour folder, or none (uncalibrated) |
| `intent` | choice | `relative colorimetric` |  |
| `black_point` | boolean | `true` | Black point compensation |
| `pure_black` | boolean | `true` | #000000 prints as 0/0/0/100 (K only) |
| `cmyk_values` | string | `""` | Exact values for vector colours (text, shapes, gradients): '#1f6feb = 90 55 0 0' or 'primary = 90 55 0 0' (percent), one per line. Images use the profile. |
| `palette` | palette (optional) |  | Lets cmyk_values use colour names |

Outputs: `cmyk` (string), `c` (float), `m` (float), `y` (float), `k` (float)

### Save Print PDF (CMYK)

`CNSavePrintPDF`. A CMYK PDF for print. vector: text stays text, flat colours get exact CMYK, images go through the profile. flatten: one CMYK image through the profile (blend modes look as on screen; exact values don't apply). Bleed: make the canvas trim + 2 x bleed ('canvas includes bleed', see the Canvas presets), or extend a solid background colour.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `filename_prefix` | string | `print/design` | {column} from a data row, {date}, {time}, {index} |
| `dpi` | float | `300.0` | Canvas pixels per inch |
| `mode` | choice | `vector` |  |
| `bleed_mode` | choice | `canvas includes bleed` |  |
| `bleed` | float | `0.125` | Inches |
| `crop_marks` | boolean | `true` |  |
| `output_intent` | boolean | `true` | Embed the CMYK profile as the PDF's output intent |
| `raster_dpi` | float | `300.0` | flatten mode |
| `profile` | choice | `(config)` | The CMYK ICC profile: the one in the config (cmyk_profile), one found in the data folder's color/ or the system colour folder, or none (uncalibrated) |
| `intent` | choice | `relative colorimetric` |  |
| `black_point` | boolean | `true` | Black point compensation |
| `pure_black` | boolean | `true` | #000000 prints as 0/0/0/100 (K only) |
| `cmyk_values` | string | `""` | Exact values for vector colours (text, shapes, gradients): '#1f6feb = 90 55 0 0' or 'primary = 90 55 0 0' (percent), one per line. Images use the profile. |
| `row` | data row (optional) |  |  |
| `palette` | palette (optional) |  | Lets cmyk_values use colour names |

Outputs: `path` (string), `report` (string)

### Soft Proof (CMYK)

`CNSoftProof`. How a design or image will look printed through the CMYK profile, and a mask of the colours that shift more than the threshold (out of gamut).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scale` | float | `0.5` | For a scene |
| `threshold` | float | `6.0` | Colour difference (ΔE) counted as out of gamut |
| `profile` | choice | `(config)` | The CMYK ICC profile: the one in the config (cmyk_profile), one found in the data folder's color/ or the system colour folder, or none (uncalibrated) |
| `intent` | choice | `relative colorimetric` |  |
| `black_point` | boolean | `true` | Black point compensation |
| `pure_black` | boolean | `true` | #000000 prints as 0/0/0/100 (K only) |
| `cmyk_values` | string | `""` | Exact values for vector colours (text, shapes, gradients): '#1f6feb = 90 55 0 0' or 'primary = 90 55 0 0' (percent), one per line. Images use the profile. |
| `scene` | scene (optional) |  |  |
| `image` | image (optional) |  |  |
| `palette` | palette (optional) |  | Lets cmyk_values use colour names |

Outputs: `proof` (image), `out_of_gamut` (mask), `report` (string)

## Shapes

### Shape

`CNShape`. A rectangle, ellipse, line, polygon or star in a box. A line runs from the box's top-left to its bottom-right corner (height 0 = horizontal). For an outline-only shape, set a stroke and fill_opacity 0.

| Input | Type | Default | Notes |
|---|---|---|---|
| `shape` | choice | `rectangle` |  |
| `x` | float | `96.0` |  |
| `y` | float | `96.0` |  |
| `width` | float | `400.0` |  |
| `height` | float | `200.0` |  |
| `color` | string | `#ffffff` | Fill colour; empty = no fill |
| `stroke_color` | string | `""` | Outline colour; empty = none |
| `stroke_width` | float | `0.0` |  |
| `corner_radius` | float | `0.0` | Rectangles |
| `sides` | int | `5` | Polygon sides / star points |
| `inner_ratio` | float | `0.5` | Stars |
| `rotation` | float | `0.0` |  |
| `below_previous` | boolean | `false` | Sit under the previous item (its bottom + gap) instead of at y |
| `gap` | float | `24.0` |  |
| `scene` | scene (optional) |  |  |
| `fill` | fill (optional) |  | Gradient fill; replaces the colour |
| `slot` | string (optional) | `""` | A name for this item in a template (Fill Template replaces its text, image or colour by this name) |
| `fill_opacity` | float (optional) | `1.0` | Opacity of the fill (colour or gradient), not the outline. 0 = no fill: with a stroke, an outline-only shape |
| `stroke_style` | string (optional) | `""` | How the stroke is drawn; click the field for the stroke editor. Text form: align=center\|inside\|outside; dash=3,2 (on,off in stroke widths); offset=0; cap=round\|butt\|square; join=round\|miter\|bevel; double=gap,width[,inside\|outside] (pixels); behind=1 (under the fill). Empty = a plain centred stroke. |

Outputs: `scene` (scene)

## Smart

### Auto Place

`CNAutoPlace`. Place a part (e.g. a title from Text Box) where the design so far is calmest, inside the safe area. Optionally switch its text to white or near-black, whichever reads best there.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `part` | scene |  |  |
| `area` | choice | `safe area` |  |
| `candidates` | choice | `anywhere` |  |
| `padding` | float | `24.0` | Calm space wanted around the part |
| `text_color` | choice | `keep` |  |
| `device` | choice | `cpu` |  |
| `background` | image (optional) |  | Judge this image instead of the design so far (same proportions) |

Outputs: `scene` (scene), `heatmap` (image), `report` (string)

### Copy Writer (Ollama)

`CNCopyWriter`. Headlines, shorter text, subtitles, taglines or calls to action from a local Ollama model. 'variants' is a list: wired into a Text Box, it makes one design per variant.

| Input | Type | Default | Notes |
|---|---|---|---|
| `task` | choice | `headlines` |  |
| `text` | string | `""` | What the copy is about |
| `instructions` | string | `""` | Tone, audience, words to use or avoid |
| `model` | string | `""` | An installed Ollama model, as 'ollama list' shows |
| `host` | string | `http://127.0.0.1:11434` |  |
| `count` | int | `3` |  |
| `max_chars` | int | `60` | 0 = no limit |
| `temperature` | float | `0.7` |  |
| `seed` | int | `0` |  |

Outputs: `text` (string), `variants` (string, list), `report` (string)

### Find Quiet Area

`CNQuietArea`. Where in an image a box of this size sits on the calmest pixels (fewest edges and texture), e.g. for a title over an AI background. Outputs the box, a readable text colour for that spot, and a heat map (calm = blue, busy = yellow).

| Input | Type | Default | Notes |
|---|---|---|---|
| `image` | image |  |  |
| `box_width` | float | `900.0` |  |
| `box_height` | float | `300.0` |  |
| `candidates` | choice | `anywhere` | 9 positions: only corners, edge centres and the middle |
| `margin` | float | `5.0` | Keep this % of the short side clear at the edges |
| `device` | choice | `cpu` |  |

Outputs: `x` (float), `y` (float), `width` (float), `height` (float), `text_color` (string), `heatmap` (image), `report` (string)

### Readability Check

`CNReadability`. WCAG contrast of every text against what is actually behind its letters (the worst 10% of those pixels). Large text needs 3:1, body text 4.5:1 (AA). The overlay frames each text green (pass) or red (fail).

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `level` | choice | `AA` |  |

Outputs: `report` (string), `worst` (float), `all_pass` (boolean), `overlay` (image)

### Smart Scrim

`CNSmartScrim`. Put a darkening (or lightening) layer under the last item, only as strong as needed for its text to reach the target contrast: a gradient band from the nearer edge, a box, or a soft glow. Nothing is added when the text already reads.

| Input | Type | Default | Notes |
|---|---|---|---|
| `scene` | scene |  |  |
| `style` | choice | `gradient band` |  |
| `color` | string | `auto` | auto: black under light text, white under dark |
| `target_contrast` | float | `4.5` |  |
| `max_opacity` | float | `0.85` |  |
| `padding` | float | `40.0` |  |
| `corner_radius` | float | `16.0` | Box style |

Outputs: `scene` (scene), `report` (string)

## Type

### Text Box

`CNTextBox`. Text in a box: wrapping, alignment, vertical anchoring, auto-fit, *bold* words. Leave 'scene' empty to make a part for Stack, Place or Grid.

| Input | Type | Default | Notes |
|---|---|---|---|
| `text` | string | `Your *headline* here` | *words* use the bold weight; \* is a literal star; new lines break |
| `font` | choice | `Montserrat` | Fonts from your font folders and the bundled fonts |
| `font_override` | string | `""` | Any installed system font family; used instead of 'font' when set |
| `weight` | int | `700` |  |
| `bold_weight` | int | `900` | Weight for *marked* words |
| `italic` | boolean | `false` |  |
| `size` | float | `96.0` | Font size in pixels |
| `color` | string | `#ffffff` | #rrggbb or #rrggbbaa |
| `align` | choice | `center` |  |
| `valign` | choice | `top` | With a box height: bottom keeps the last line in place, extra lines grow upward |
| `case` | choice | `as typed` |  |
| `x` | float | `96.0` |  |
| `y` | float | `96.0` |  |
| `box_width` | float | `1728.0` | Wrap width; 0 = no wrapping |
| `box_height` | float | `0.0` | 0 = as tall as the text |
| `auto_fit` | boolean | `false` | Shrink the font until the text fits the box |
| `min_size` | float | `12.0` |  |
| `line_height` | float | `1.15` |  |
| `letter_spacing` | float | `0.0` |  |
| `below_previous` | boolean | `false` | Sit under the previous item (its bottom + gap) instead of at y |
| `gap` | float | `24.0` |  |
| `scene` | scene (optional) |  |  |
| `fill` | fill (optional) |  | Gradient text; replaces the colour |
| `slot` | string (optional) | `""` | A name for this item in a template (Fill Template replaces its text, image or colour by this name) |

Outputs: `scene` (scene)
