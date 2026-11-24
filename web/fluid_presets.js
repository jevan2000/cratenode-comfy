// CrateNode-Comfy Fluid Gradient presets: picking a preset fills the node's style,
// colours and settings in (from /cratenode/fluid_presets), so the look can be tweaked
// from there; changing any of those settings sets the preset back to "custom".
//
// Random looks: a "Random look" button, and with randomize ticked a new look just before
// each queued prompt (before_run.js, shared with Palette Generator), so the queued prompt
// carries exactly what the node shows. The server picks the look (/cratenode/fluid_random)
// within ranges that keep it good. Fields fed by a link are left alone, and so are the
// colours when a palette is connected.

import { onBeforeRun } from "./before_run.js";

const { app } = window.comfyAPI.app;
const { api } = window.comfyAPI.api;

const NODE = "CNFluidGradient";
const CUSTOM = "custom";

let presets = null; // Promise<{name: {input: value}}>
function getPresets() {
  if (!presets) {
    presets = api.fetchApi("/cratenode/fluid_presets")
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}));
  }
  return presets;
}

async function apply(node, name) {
  const all = await getPresets();
  const values = all[name];
  if (!values) return;
  node.cnApplyingPreset = true;
  try {
    for (const w of node.widgets || []) {
      if (w.name in values) w.value = values[w.name];
    }
  } finally {
    node.cnApplyingPreset = false;
  }
  node.setDirtyCanvas?.(true, true);
}

const isFluid = (n) => n?.comfyClass === NODE || n?.type === NODE;
const widget = (node, name) => node.widgets?.find((w) => w.name === name);
const linkedInput = (node, name) => (node.inputs || []).some((i) => (i.widget?.name === name || i.name === name)
  && i.link != null);

async function randomLook(node) {
  const r = await api.fetchApi("/cratenode/fluid_random");
  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.values) throw new Error(data.error || r.statusText);
  const keepColours = linkedInput(node, "palette");
  node.cnApplyingPreset = true;
  try {
    for (const w of node.widgets || []) {
      if (!(w.name in data.values) || linkedInput(node, w.name)) continue;
      if (keepColours && /^color_\d$/.test(w.name)) continue;
      w.value = data.values[w.name];
    }
    const preset = widget(node, "preset");
    if (preset) preset.value = CUSTOM; // the look is no longer a preset's
  } finally {
    node.cnApplyingPreset = false;
  }
  node.setDirtyCanvas?.(true, true);
}

function addButton(node) {
  if (node.cnRandom) return;
  const b = node.addWidget("button", "🎲 Random look", null, () => {
    randomLook(node).catch((e) => console.warn("CrateNode fluid:", e));
  }, { serialize: false });
  b.serialize = false;
  node.cnRandom = b;
  placeButton(node);
}

// The button goes right under preset / randomize at the top (display only; not saved).
function placeButton(node) {
  const b = node.cnRandom;
  if (!b) return;
  const i = node.widgets.indexOf(b);
  if (i < 0) return;
  node.widgets.splice(i, 1);
  const anchor = ["randomize", "preset"].map((n) => node.widgets.findIndex((w) => w.name === n)).find((x) => x >= 0);
  node.widgets.splice(anchor === undefined ? 0 : anchor + 1, 0, b);
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

// Before a run: a new look on each Fluid Gradient with randomize ticked (not bypassed or muted).
async function beforeRun() {
  const jobs = allNodes().filter((n) => isFluid(n) && n.mode === 0 && widget(n, "randomize")?.value);
  await Promise.all(jobs.map((n) => randomLook(n).catch((e) => console.warn("CrateNode fluid:", e))));
}

const NOT_LOOK = new Set(["randomize", "cn_live_preview"]); // changing these keeps the preset

function hook(node) {
  const preset = node.widgets?.find((w) => w.name === "preset");
  if (!preset || preset.cnHooked) return;
  preset.cnHooked = true;
  const pick = preset.callback;
  preset.callback = function (value) {
    const r = pick?.apply(this, arguments);
    if (preset.value && preset.value !== CUSTOM) apply(node, preset.value);
    return r;
  };
  // a hand edit of any look setting means the node no longer matches the preset
  for (const w of node.widgets) {
    if (w === preset || NOT_LOOK.has(w.name) || w === node.cnRandom) continue;
    const cb = w.callback;
    w.callback = function () {
      const r = cb?.apply(this, arguments);
      if (!node.cnApplyingPreset && preset.value !== CUSTOM) {
        preset.value = CUSTOM;
        node.setDirtyCanvas?.(true, true);
      }
      return r;
    };
  }
}

app.registerExtension({
  name: "CrateNode.FluidPresets",
  setup() {
    // once per queued prompt, so a batch of N gets N different looks (before_run.js)
    onBeforeRun(beforeRun);
  },
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE) return;
    getPresets();
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      addButton(this);
      hook(this);
      // other extensions may reorder the fields after this; settle the button once they have
      setTimeout(() => placeButton(this), 0);
      return r;
    };
  },
});
