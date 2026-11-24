// CrateNode-Comfy Palette Generator: a Generate button on the node (a new set of five
// colours without running), a new set just before each run when new_each_run is on, and
// a lock that stops both. The colours are the node's own color_1..color_5 fields, so the
// workflow saves them and a run uses exactly what the node shows. The server makes the
// colours (/cratenode/palette), with the same rules as the node's documentation.

import { onBeforeRun } from "./before_run.js";

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const TYPE = "CNPaletteGenerator";
const COUNT = 5;

const isGen = (n) => n?.comfyClass === TYPE || n?.type === TYPE;
const widget = (node, name) => node.widgets?.find((w) => w.name === name);

function setValue(node, name, value) {
  const w = widget(node, name);
  if (!w) return;
  w.value = value;
  try { w.callback?.(value, app.canvas, node); } catch { /* a widget without a callback */ }
}

async function generate(node) {
  if (widget(node, "locked")?.value) return false;
  const body = {
    harmony: widget(node, "harmony")?.value ?? "random",
    family: widget(node, "family")?.value ?? "any",
    style: widget(node, "style")?.value ?? "any",
  };
  const r = await api.fetchApi("/cratenode/palette", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || !Array.isArray(data.colors)) throw new Error(data.error || r.statusText);
  data.colors.slice(0, COUNT).forEach((hex, i) => setValue(node, `color_${i + 1}`, hex));
  node.setDirtyCanvas?.(true, true);
  return true;
}

// The Generate button greys out while the node is locked.
function syncButton(node) {
  const b = node.cnGenerate;
  if (!b) return;
  const off = !!widget(node, "locked")?.value;
  if (!!b.disabled !== off) {
    b.disabled = off;
    b.label = off ? "🔒 locked (unlock to generate)" : "🎲 Generate palette";
    b.name = b.label;
    node.setDirtyCanvas?.(true, true);
  }
}

function addButton(node) {
  if (node.cnGenerate) return;
  const b = node.addWidget("button", "🎲 Generate palette", null, () => {
    if (b.disabled) return;
    generate(node).catch((e) => console.warn("CrateNode palette:", e));
  }, { serialize: false });
  b.serialize = false;
  node.cnGenerate = b;
  // show it right under the colours (display only; it isn't saved with the workflow)
  const i = node.widgets.indexOf(b), after = node.widgets.findIndex((w) => w.name === `color_${COUNT}`);
  if (i >= 0 && after >= 0) {
    node.widgets.splice(i, 1);
    node.widgets.splice(after + 1, 0, b);
  }
  syncButton(node);
  keepValuesInPlace(node);
}

// Saved widget values are positional. Some frontends (1.51.9) save a blank slot for the
// button even though it isn't saved, then skip it when loading, so every setting after it
// moved down one place (new_each_run's value landed in locked). Save without the slot, and
// repair files that were saved with it.
const saved = (w) => w.serialize !== false && w.options?.serialize !== false;
function keepValuesInPlace(node) {
  const names = () => node.widgets.filter(saved).map((w) => w.name);
  const onSerialize = node.onSerialize;
  node.onSerialize = function (o) {
    const r = onSerialize?.apply(this, arguments);
    const v = o?.widgets_values;
    if (Array.isArray(v) && v.length > names().length) {
      o.widgets_values = node.widgets.map((w, i) => [w, v[i]]).filter(([w]) => saved(w)).map(([, x]) => x);
    }
    return r;
  };
  const configure = node.configure;
  node.configure = function (info) {
    const v = info?.widgets_values;
    // An old file with the button's slot: one value too many, a blank right after color_5.
    if (Array.isArray(v) && v.length === names().length + 1 && v[COUNT] == null) {
      info = { ...info, widgets_values: [...v.slice(0, COUNT), ...v.slice(COUNT + 1)] };
    }
    return configure.call(this, info);
  };
}

// Every graph (including subgraphs) the run will include.
function allNodes() {
  const out = [];
  const walk = (g) => {
    for (const n of g?._nodes || g?.nodes || []) {
      out.push(n);
      if (n.subgraph) walk(n.subgraph);
    }
  };
  walk(app.graph);
  return out;
}

// Before a run: a new set on each unlocked generator with new_each_run on (and not
// bypassed or muted), so the queued prompt carries the new colours.
async function beforeRun() {
  const jobs = allNodes().filter((n) => isGen(n) && n.mode === 0 && widget(n, "new_each_run")?.value
    && !widget(n, "locked")?.value);
  await Promise.all(jobs.map((n) => generate(n).catch((e) => console.warn("CrateNode palette:", e))));
}

app.registerExtension({
  name: "CrateNode.PaletteGenerator",
  setup() {
    // once per queued prompt, so a batch of N gets N different sets (before_run.js)
    onBeforeRun(beforeRun);
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== TYPE) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      addButton(this);
      return r;
    };
    const draw = nodeType.prototype.onDrawBackground;
    nodeType.prototype.onDrawBackground = function () {
      syncButton(this);
      return draw?.apply(this, arguments);
    };
  },
});
