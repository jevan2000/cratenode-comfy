// CrateNode-Comfy layout nodes (Stack, Place, Grid): x, y, box_width and box_height
// only apply when area is "custom". Grey them out otherwise, so it's clear they do
// nothing. Display only: their values are still saved and sent as before.

const { app } = window.comfyAPI.app;

const BOX_FIELDS = ["x", "y", "box_width", "box_height"];

function sync(node) {
  const area = node.widgets?.find((w) => w.name === "area");
  if (!area) return;
  const off = area.value !== "custom";
  let changed = false;
  for (const w of node.widgets) {
    if (!BOX_FIELDS.includes(w.name) || !!w.disabled === off) continue;
    w.disabled = off;
    changed = true;
  }
  if (changed) node.setDirtyCanvas?.(true, true);
}

function watch(node) {
  const area = node.widgets?.find((w) => w.name === "area");
  if (!area || area.cnAreaWatched) return;
  area.cnAreaWatched = true;
  const callback = area.callback;
  area.callback = function () {
    const r = callback?.apply(this, arguments);
    sync(node);
    return r;
  };
  sync(node);
}

app.registerExtension({
  name: "CrateNode.AreaFields",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData?.name?.startsWith("CN")) return;
    const inputs = { ...(nodeData.input?.required || {}), ...(nodeData.input?.optional || {}) };
    if (!inputs.area || !BOX_FIELDS.every((n) => inputs[n])) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      watch(this);
      return r;
    };
    // a loaded workflow sets area after the node is created
    const configure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const r = configure?.apply(this, arguments);
      sync(this);
      return r;
    };
    // values set by code (or a widget without a callback) are caught when drawn
    const draw = nodeType.prototype.onDrawBackground;
    nodeType.prototype.onDrawBackground = function () {
      sync(this);
      return draw?.apply(this, arguments);
    };
  },
});
