// CrateNode-Comfy Fluid Gradient presets: picking a preset fills the node's style,
// colours and settings in (from /cratenode/fluid_presets), so the look can be tweaked
// from there; changing any of those settings sets the preset back to "custom".

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
    if (w === preset || w.name === "cn_live_preview") continue;
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
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData?.name !== NODE) return;
    getPresets();
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      hook(this);
      return r;
    };
  },
});
