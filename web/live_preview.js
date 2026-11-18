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

function attach(node, type) {
  const root = document.createElement("div");
  root.style.cssText =
    "display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;" +
    "width:100%;height:100%;box-sizing:border-box;padding:4px;overflow:hidden;";
  const img = document.createElement("img");
  img.style.cssText = "max-width:100%;max-height:" + (HEIGHT - 24) + "px;object-fit:contain;" +
    "border-radius:4px;box-shadow:0 0 0 1px rgba(255,255,255,0.08);";
  img.alt = "";
  const note = document.createElement("div");
  note.style.cssText = "font:11px sans-serif;color:#9aa3ad;text-align:center;line-height:1.2;" +
    "max-height:2.4em;overflow:hidden;";
  note.textContent = "live preview";
  root.append(img, note);

  const widget = node.addDOMWidget(WIDGET, "cn_preview", root, {
    serialize: false,
    hideOnZoom: false,
    getMinHeight: () => HEIGHT,
    getMaxHeight: () => HEIGHT,
    getHeight: () => HEIGHT,
  });
  // Keep the preview out of saved workflows (widgets_values) too, not only out of prompts.
  if (widget) widget.serialize = false;

  const state = { last: "", timer: null, inflight: 0, url: null };
  node.cnPreview = state;
  live.add(node);

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
        note.textContent = "⚠ " + (e.error || r.statusText);
        note.style.color = "#e0a050";
        return;
      }
      const blob = await r.blob();
      if (state.url) URL.revokeObjectURL(state.url);
      state.url = URL.createObjectURL(blob);
      img.src = state.url;
      note.textContent = r.headers.get("X-CN-Note") || "live preview";
      note.style.color = "#9aa3ad";
    } catch (err) {
      note.textContent = "⚠ preview unavailable";
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
