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

function widgetValues(node) {
  const out = {};
  for (const w of node.widgets || []) {
    if (w.name === WIDGET || w.name === "control_after_generate") continue;
    const v = w.value;
    if (["string", "number", "boolean"].includes(typeof v)) out[w.name] = v;
  }
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
      const boxW = width - PAD * 2;
      const boxH = HEIGHT - NOTE_H - PAD * 1.5;
      const img = state.img;
      ctx.save();
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
    if (!set.has(nodeData.name)) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      attach(this, nodeData.name);
      return r;
    };
  },
});
