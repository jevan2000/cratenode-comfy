// CrateNode-Comfy Palette: makes the optional 'colors' text box behave as a mirror of the
// color_1..color_5 swatches. It shrinks the box to a few rows so it stops dominating the
// node, and shows the live hexes as its placeholder - so the empty box literally displays the
// colours below it, making it obvious that typing 'name: #hex' there is the manual way in.
// Typing in the box still wins when it has content (the server honours that); that rule is
// unchanged, this only affects how the empty box looks.

const { app } = window.comfyAPI.app;

const TYPE = "CNPalette";
const MIRROR = "colors";
const ROWS = 3;

const widget = (node, name) => node.widgets?.find((w) => w.name === name);
const swatchWidgets = (node) => (node.widgets || []).filter((w) => /^color_\d+$/.test(w.name));

function liveHexes(node) {
  return swatchWidgets(node).map((w) => String(w.value ?? "").trim()).filter(Boolean);
}

// Multiline widgets take their height from the row count, so cap it at ROWS.
function compact(node) {
  const w = widget(node, MIRROR);
  if (!w) return;
  w.options ??= {};
  w.options.rows = ROWS;
  // The multiline field is a DOM textarea. Its visible height comes from its own style, and
  // the node gives it a flexible layout height through computeLayoutSize(), which lets it
  // grow to fill the node (and grow back to 15 rows after a resize). Pin both to ROWS.
  if (w.inputEl) {
    w.inputEl.rows = ROWS;
    w.inputEl.style.height = "auto";
    w.inputEl.style.maxHeight = `${Math.round((window.LiteGraph?.NODE_WIDGET_HEIGHT || 20) * ROWS)}px`;
  }
  if (w.cnSized) return;
  if (typeof w.computeLayoutSize === "function") {
    const height = Math.round((window.LiteGraph?.NODE_WIDGET_HEIGHT || 20) * ROWS);
    w.computeLayoutSize = function () { return { minHeight: height, maxHeight: height }; };
    w.cnSized = true;
  }
}

// The placeholder is what the field shows while empty, so it mirrors the swatches.
function syncMirror(node) {
  compact(node); // the textarea can be created after the first compact()
  const w = widget(node, MIRROR);
  if (!w) return;
  const hexes = liveHexes(node);
  w.placeholder = hexes.length
    ? `empty = use the swatches:\n${hexes.join("\n")}`
    : "optional: name: #hex";
  w.options ??= {};
  w.options.placeholder = w.placeholder;
  if (w.inputEl) w.inputEl.placeholder = w.placeholder;
}

function wire(node) {
  compact(node);
  syncMirror(node);
  // Every swatch edit updates the mirror, so the hint always matches what a run would use.
  for (const w of swatchWidgets(node)) {
    if (w.cnMirrored) continue;
    w.cnMirrored = true;
    const cb = w.callback;
    w.callback = function () {
      const r = cb?.apply(this, arguments);
      try {
        syncMirror(node);
        node.setDirtyCanvas?.(true, true);
      } catch { /* never break a swatch edit */ }
      return r;
    };
  }
}

app.registerExtension({
  name: "CrateNode.PaletteMirror",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== TYPE) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      try { wire(this); } catch (e) { console.warn("CrateNode palette mirror:", e); }
      return r;
    };
    // A loaded workflow fills widget values after creation, so refresh once it is configured.
    const configure = nodeType.prototype.configure;
    nodeType.prototype.configure = function () {
      const r = configure?.apply(this, arguments);
      try { syncMirror(this); } catch { /* not fatal */ }
      return r;
    };
  },
});
