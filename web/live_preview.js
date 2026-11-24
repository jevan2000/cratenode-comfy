// CrateNode-Comfy live previews: a picture at the bottom of design nodes (Canvas,
// Text Box, Shape, gradients, Palette, effects, ...) that follows their settings
// before anything runs. The server draws it with the node's own code
// (POST /cratenode/preview), so it matches the real output.

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const WIDGET = "cn_live_preview";
const HEIGHT = 170; // preview area, px
const DEBOUNCE_MS = 250;
const POLL_MS = 350;

let previewable = null; // Promise<Set<string>>
function getPreviewable() {
  if (!previewable) {
    previewable = api
      .fetchApi("/cratenode/previewable")
      .then((r) => (r.ok ? r.json() : []))
      .then((list) => new Set(list))
      .catch(() => new Set());
  }
  return previewable;
}

const live = new Set(); // nodes with a preview

// Widgets shown somewhere other than their place in the node definition. Saved workflows
// store widget values by position, so new inputs are always added last on the server;
// here they are only *shown* next to the setting they belong with. Files keep the
// server's order (see keepFileOrder), so old and new workflows load the same values.
const SHOW_AFTER = {
  CNShape: { fill_opacity: "color", stroke_style: "stroke_width" },
  CNGrid: { direction: "columns", placement: "valign" },
  CNFluidGradient: { preset: null, randomize: "preset" }, // null = at the top
};

// Labels that follow another setting: Grid's count is per row (columns) when it fills
// across, per column (rows) when it fills down. Only the label changes, not the name.
function relabel(node) {
  if (node.comfyClass !== "CNGrid" && node.type !== "CNGrid") return;
  const dir = node.widgets?.find((w) => w.name === "direction");
  const count = node.widgets?.find((w) => w.name === "columns");
  if (!dir || !count) return;
  const label = dir.value === "horizontal" ? "rows" : "columns";
  if ((count.label || count.name) !== label) {
    count.label = label;
    node.setDirtyCanvas?.(true, true);
  }
}

const saved = (w) => w.serialize !== false && w.options?.serialize !== false;

function moveForDisplay(node, type) {
  const moves = SHOW_AFTER[type];
  if (!moves || !node.widgets) return;
  node.cnFileOrder = node.widgets.filter(saved).map((w) => w.name);
  for (const [name, after] of Object.entries(moves)) {
    const from = node.widgets.findIndex((w) => w.name === name);
    if (from < 0 || (after !== null && !node.widgets.some((w) => w.name === after))) continue;
    const [w] = node.widgets.splice(from, 1);
    const at = after === null ? 0 : node.widgets.findIndex((x) => x.name === after) + 1;
    node.widgets.splice(at, 0, w);
  }
  keepFileOrder(node);
}

// Translate widgets_values between file order (the server's) and display order.
function keepFileOrder(node) {
  const fileOrder = node.cnFileOrder;
  const shown = () => node.widgets.filter(saved).map((w) => w.name);
  const configure = node.configure;
  node.configure = function (info) {
    if (Array.isArray(info?.widgets_values)) {
      const byName = {};
      fileOrder.forEach((name, i) => { if (i < info.widgets_values.length) byName[name] = info.widgets_values[i]; });
      const values = shown().map((name) => name in byName ? byName[name] : node.widgets.find((w) => w.name === name)?.value);
      info = { ...info, widgets_values: values };
    }
    return configure.call(this, info);
  };
  const onSerialize = node.onSerialize;
  node.onSerialize = function (o) {
    const r = onSerialize?.apply(this, arguments);
    if (Array.isArray(o?.widgets_values)) {
      const byName = {};
      shown().forEach((name, i) => { byName[name] = o.widgets_values[i]; });
      o.widgets_values = fileOrder.map((name) => byName[name]);
    }
    return r;
  };
}

// The node a link starts from, following reroutes.
function linkSource(node, input) {
  const graph = node.graph || app.graph;
  let link = input?.link != null ? graph?.links?.[input.link] ?? graph?.links?.get?.(input.link) : null;
  for (let hops = 0; link && hops < 20; hops++) {
    const from = graph.getNodeById(link.origin_id);
    if (!from) return null;
    if ((from.type || from.comfyClass) !== "Reroute") return { node: from, slot: link.origin_slot };
    const next = from.inputs?.[0]?.link;
    link = next != null ? graph.links?.[next] ?? graph.links?.get?.(next) : null;
  }
  return null;
}

const simple = (v) => ["string", "number", "boolean"].includes(typeof v);

// A value arriving through a link isn't known until the workflow runs, but often it can
// be: a primitive node's value, or a CrateNode node the server can work out (Random
// Colour). Those are used in the preview; anything else keeps the widget's own value.
function linkedValues(node, out, depth = 0) {
  for (const input of node.inputs || []) {
    const name = input.widget?.name ?? input.name;
    if (input.link == null || !(name in out)) continue;
    const src = linkSource(node, input);
    if (!src) continue;
    const t = src.node.comfyClass || src.node.type || "";
    if (/^Primitive/.test(t)) {
      const v = src.node.widgets?.[0]?.value;
      if (simple(v)) out[name] = v;
    } else if (t.startsWith("CN") && depth < 2) {
      out.__links = out.__links || {};
      out.__links[name] = { type: t, slot: src.slot, widgets: widgetValues(src.node, depth + 1) };
    }
  }
}

function widgetValues(node, depth = 0) {
  const out = {};
  for (const w of node.widgets || []) {
    if (w.name === WIDGET || w.name === "control_after_generate") continue;
    const v = w.value;
    if (simple(v)) out[w.name] = v;
  }
  linkedValues(node, out, depth);
  // Layout nodes: how many part inputs are connected, so the preview shows that many
  // stand-ins (what's connected isn't known until the workflow runs).
  const parts = (node.inputs || []).filter((i) => /^part_\d+$/.test(i.name));
  if (parts.length) out.__parts = parts.filter((i) => i.link != null).length;
  return out;
}

const NOTE_H = 16; // caption line under the picture
const PAD = 8;

// The preview is drawn on the node's own canvas, like ComfyUI's built-in widgets, not as
// an HTML element laid over it: floating elements drift away from the node on some
// frontend versions (seen on 1.51.9 after moving or resizing a node), a canvas drawing
// can't.
function previewWidget(state) {
  return {
    name: WIDGET,
    type: "cn_preview",
    value: "",
    serialize: false, // not part of saved workflows or prompts
    options: { serialize: false },
    computeSize(width) {
      return [width, HEIGHT];
    },
    draw(ctx, node, width, y) {
      // The node's real width: some frontends pass a stale, larger width here (seen on
      // 1.51.9 after a run), which drew the picture off to the right, outside the node.
      width = Math.min(Number(width) || Infinity, node.size[0]);
      const boxW = width - PAD * 2;
      const boxH = HEIGHT - NOTE_H - PAD * 1.5;
      const img = state.img;
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, y, width, HEIGHT); // never draw outside the node
      ctx.clip();
      if (img && img.complete && img.naturalWidth) {
        const k = Math.min(boxW / img.naturalWidth, boxH / img.naturalHeight, 1.5);
        const w = img.naturalWidth * k, h = img.naturalHeight * k;
        const x = PAD + (boxW - w) / 2, top = y + PAD / 2 + (boxH - h) / 2;
        ctx.drawImage(img, x, top, w, h);
        ctx.strokeStyle = "rgba(255,255,255,0.10)";
        ctx.lineWidth = 1;
        ctx.strokeRect(x - 0.5, top - 0.5, w + 1, h + 1);
      }
      ctx.fillStyle = state.noteColor;
      ctx.font = "11px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      let text = state.note;
      while (text.length > 4 && ctx.measureText(text).width > boxW) text = text.slice(0, -2);
      if (text !== state.note) text = text.slice(0, -1) + "…";
      ctx.fillText(text, width / 2, y + HEIGHT - NOTE_H / 2 - 2);
      ctx.restore();
    },
  };
}

function attach(node, type) {
  const state = {
    last: "", timer: null, inflight: 0, url: null, img: null,
    note: "live preview", noteColor: "#9aa3ad",
  };
  node.cnPreview = state;
  const widget = node.addCustomWidget(previewWidget(state));
  if (widget) widget.serialize = false;
  live.add(node);

  const redraw = () => node.setDirtyCanvas?.(true, true);
  const setNote = (text, color) => {
    state.note = text;
    state.noteColor = color;
    redraw();
  };

  async function refresh(values) {
    const seq = ++state.inflight;
    try {
      const r = await api.fetchApi("/cratenode/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ type, widgets: values }),
      });
      if (seq !== state.inflight) return; // a newer request is on its way
      if (!r.ok) {
        const e = await r.json().catch(() => ({}));
        setNote("⚠ " + (e.error || r.statusText), "#e0a050");
        return;
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => {
        if (state.url) URL.revokeObjectURL(state.url);
        state.url = url;
        state.img = img;
        setNote(r.headers.get("X-CN-Note") || "live preview", "#9aa3ad");
      };
      img.src = url;
    } catch (err) {
      setNote("⚠ preview unavailable", "#e0a050");
    }
  }

  state.check = () => {
    const values = widgetValues(node);
    const key = JSON.stringify(values);
    if (key === state.last) return;
    state.last = key;
    relabel(node);
    clearTimeout(state.timer);
    state.timer = setTimeout(() => refresh(values), DEBOUNCE_MS);
  };

  const onRemoved = node.onRemoved;
  node.onRemoved = function () {
    live.delete(node);
    clearTimeout(state.timer);
    if (state.url) URL.revokeObjectURL(state.url);
    return onRemoved?.apply(this, arguments);
  };

  // make room for the preview under the widgets
  const size = node.computeSize?.();
  if (size) node.setSize([Math.max(node.size[0], size[0]), Math.max(node.size[1], size[1])]);
  state.check();
}

// One timer for all previews: cheap value comparison, so typing, sliders, combos and
// pasted workflows are all picked up without hooking every widget.
setInterval(() => {
  for (const node of live) node.cnPreview?.check();
}, POLL_MS);

app.registerExtension({
  name: "CrateNode.LivePreview",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData?.name?.startsWith("CN")) return;
    const set = await getPreviewable();
    const preview = set.has(nodeData.name), move = nodeData.name in SHOW_AFTER;
    if (!preview && !move) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      if (move) moveForDisplay(this, nodeData.name); // before the preview, which is never saved
      if (preview) attach(this, nodeData.name);
      return r;
    };
  },
});
