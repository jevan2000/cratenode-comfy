// CrateNode-Comfy colour fields: a chip inside every hex colour field shows the colour,
// and clicking the chip opens a picker (RGB sliders, or HSL; opacity; eyedropper;
// recent colours). The field keeps plain text (#rrggbb or #rrggbbaa), so saved
// workflows, links and the API are unchanged; typing a value still works as before.

const { app } = window.comfyAPI.app;

const COLOR_NAME = /^(colou?r(_\d+)?|stroke_color|background|matte|against|text_color)$/;
const MARGIN = 15; // litegraph widget margin
const CHIP_W = 24;
const RECENT_KEY = "cratenode.recentColors";

// ---- colour maths ----

function parseHex(s) {
  const m = /^#?([0-9a-f]{3}|[0-9a-f]{6}|[0-9a-f]{8})$/i.exec(String(s || "").trim());
  if (!m) return null;
  let h = m[1];
  if (h.length === 3) h = h.split("").map((c) => c + c).join("");
  const n = (i) => parseInt(h.slice(i, i + 2), 16);
  return { r: n(0), g: n(2), b: n(4), a: h.length === 8 ? n(6) : 255 };
}

function toHex({ r, g, b, a }) {
  const x = (v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0");
  return "#" + x(r) + x(g) + x(b) + (a >= 255 ? "" : x(a));
}

function rgbToHsl({ r, g, b }) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l: l * 100 };
  const d = max - min, s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return { h: h * 60, s: s * 100, l: l * 100 };
}

function hslToRgb({ h, s, l }) {
  s /= 100; l /= 100;
  const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return { r: f(0) * 255, g: f(8) * 255, b: f(4) * 255 };
}

// ---- recent colours (this browser only) ----

function recent() {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]").filter((c) => parseHex(c)); }
  catch { return []; }
}

function remember(hex) {
  try {
    const list = [hex, ...recent().filter((c) => c.toLowerCase() !== hex.toLowerCase())].slice(0, 14);
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch { /* private window: no memory, still works */ }
}

// ---- the chip inside the field ----

function checker(ctx, x, y, w, h, size = 4) {
  ctx.fillStyle = "#cfcfcf";
  ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#9a9a9a";
  for (let i = 0; i < w / size; i++)
    for (let j = 0; j < h / size; j++)
      if ((i + j) % 2) ctx.fillRect(x + i * size, y + j * size, Math.min(size, w - i * size), Math.min(size, h - j * size));
}

function linked(node, w) {
  return (node.inputs || []).some((i) => i.widget?.name === w.name && i.link != null);
}

// Draw the chip right after the field draws itself (a node's foreground hook runs before
// widgets on newer frontends, so the field would cover it). Frontends call widget.draw
// as draw(ctx, node, width, y, height) (plain widgets) or, for built-in widget classes,
// drawWidget(ctx, {width, ...}) with the row's top in this.y.
function hookField(node, w) {
  const key = typeof w.drawWidget === "function" ? "drawWidget" : "draw";
  const orig = w[key];
  if (typeof orig !== "function" || w.cnHooked) return;
  w.cnHooked = true;
  w[key] = function (ctx, ...args) {
    const r = orig.call(this, ctx, ...args);
    try {
      const legacy = args[0] === node;
      const width = legacy ? args[1] : (args[0]?.width ?? node.size[0]);
      const y = legacy ? args[2] : (this.y ?? this.last_y);
      drawChip(node, this, ctx, width, y);
    } catch { /* never break the node's drawing */ }
    return r;
  };
  // A click on the chip opens the picker; anywhere else in the field keeps the usual
  // text prompt. Built-in widget classes handle clicks in onClick({e, node}), plain
  // widgets in mouse(event, pos, node).
  const onChip = (e) => {
    const x = e?.canvasX - node.pos[0], y = e?.canvasY - node.pos[1];
    const chip = (node.cnChips || []).find((c) => c.w === w);
    if (!chip || !(x >= chip.x && x <= chip.x + chip.cw && y >= chip.y && y <= chip.y + chip.ch)) return false;
    openPicker(node, w, e.clientX ?? 200, e.clientY ?? 200);
    return true;
  };
  if (typeof w.onClick === "function") {
    const click = w.onClick;
    w.onClick = function (opts) {
      if (onChip(opts?.e)) return;
      return click.apply(this, arguments);
    };
  }
  if (typeof w.mouse === "function") {
    const mouse = w.mouse;
    w.mouse = function (e) {
      if (e?.type?.endsWith("down") && onChip(e)) return true;
      return mouse.apply(this, arguments);
    };
  }
}

function drawChip(node, w, ctx, width, y) {
  node.cnChips = (node.cnChips || []).filter((c) => c.w !== w);
  const H = window.LiteGraph?.NODE_WIDGET_HEIGHT || 20;
  if (w.hidden || w.disabled || linked(node, w) || typeof y !== "number") return;
  {
    ctx.save();
    ctx.font = "12px Arial";
    const labelW = ctx.measureText(w.label || w.name).width;
    const valueW = ctx.measureText(String(w.value ?? "")).width;
    const x = MARGIN * 2 + labelW + 8;
    const room = width - MARGIN * 2 - valueW - 8 - x;
    const cw = Math.min(CHIP_W, room);
    if (cw >= 10) {
      const top = y + 4, ch = H - 8;
      const c = parseHex(w.value);
      ctx.beginPath();
      ctx.roundRect ? ctx.roundRect(x, top, cw, ch, 3) : ctx.rect(x, top, cw, ch);
      ctx.save();
      ctx.clip();
      checker(ctx, x, top, cw, ch);
      if (c) {
        ctx.fillStyle = `rgba(${c.r},${c.g},${c.b},${c.a / 255})`;
        ctx.fillRect(x, top, cw, ch);
      } else { // empty, "transparent", "auto", a palette name: a diagonal line
        ctx.strokeStyle = "#d04040";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(x, top + ch);
        ctx.lineTo(x + cw, top);
        ctx.stroke();
      }
      ctx.restore();
      ctx.strokeStyle = "rgba(255,255,255,0.35)";
      ctx.lineWidth = 1;
      ctx.stroke();
      node.cnChips.push({ w, x: x - 3, y: top - 3, cw: cw + 6, ch: ch + 6 });
    }
    ctx.restore();
  }
}

// ---- the picker ----

let open = null; // { root, close }

function specials(node, w) {
  const out = [];
  const spec = node.cnColorSpecs?.[w.name] || {};
  if (spec.transparent) out.push(["Transparent", "transparent"]);
  if (spec.auto) out.push(["Auto", "auto"]);
  if (spec.empty) out.push(["None", ""]);
  return out;
}

function el(tag, css, attrs = {}) {
  const e = document.createElement(tag);
  if (css) e.style.cssText = css;
  Object.assign(e, attrs);
  return e;
}

function openPicker(node, w, clientX, clientY) {
  open?.close(false);
  const start = String(w.value ?? "");
  let c = parseHex(start) || { r: 0, g: 0, b: 0, a: 255 };
  let mode = (() => { try { return localStorage.getItem("cratenode.pickerMode") || "rgb"; } catch { return "rgb"; } })();
  let hsl = rgbToHsl(c);

  const root = el("div",
    "position:fixed;z-index:10000;width:264px;padding:10px;border-radius:10px;background:#1f2126;" +
    "color:#d7dbe0;font:12px sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.55);border:1px solid #3a3d44;user-select:none;");
  root.addEventListener("pointerdown", (e) => e.stopPropagation());

  // header: swatch, hex, mode toggle
  const head = el("div", "display:flex;gap:8px;align-items:center;margin-bottom:8px;");
  const sw = el("div", "width:44px;height:44px;border-radius:6px;border:1px solid #555;flex:none;" +
    "background-image:linear-gradient(45deg,#999 25%,transparent 25%,transparent 75%,#999 75%)," +
    "linear-gradient(45deg,#999 25%,#ccc 25%,#ccc 75%,#999 75%);background-size:10px 10px;background-position:0 0,5px 5px;");
  const swFill = el("div", "width:100%;height:100%;border-radius:5px;");
  sw.append(swFill);
  const right = el("div", "flex:1;display:flex;flex-direction:column;gap:6px;");
  const hex = el("input", "width:100%;box-sizing:border-box;background:#14161a;color:#e8eaed;border:1px solid #444;" +
    "border-radius:5px;padding:4px 6px;font:12px monospace;", { type: "text", spellcheck: false });
  const toggle = el("div", "display:flex;gap:4px;");
  const modeBtn = (m) => el("button", "", { textContent: m.toUpperCase() });
  const rgbBtn = modeBtn("rgb"), hslBtn = modeBtn("hsl");
  toggle.append(rgbBtn, hslBtn);
  right.append(hex, toggle);
  head.append(sw, right);

  const sliders = el("div", "display:flex;flex-direction:column;gap:5px;");
  const extras = el("div", "display:flex;gap:6px;margin-top:8px;flex-wrap:wrap;");
  const recentRow = el("div", "display:flex;gap:4px;flex-wrap:wrap;margin-top:8px;");
  root.append(head, sliders, extras, recentRow);

  const btnCss = "background:#2c2f36;color:#d7dbe0;border:1px solid #474b53;border-radius:5px;padding:3px 8px;" +
    "font:12px sans-serif;cursor:pointer;";
  for (const b of [rgbBtn, hslBtn]) b.style.cssText = btnCss + "flex:1;";

  function row(label, max, get, set, gradient) {
    const r = el("div", "display:flex;align-items:center;gap:6px;");
    const name = el("span", "width:12px;color:#9aa3ad;", { textContent: label });
    const range = el("input", "flex:1;height:14px;-webkit-appearance:none;appearance:none;border-radius:7px;" +
      "border:1px solid #444;margin:0;cursor:pointer;", { type: "range", min: 0, max, step: 1 });
    const num = el("input", "width:44px;background:#14161a;color:#e8eaed;border:1px solid #444;border-radius:4px;" +
      "padding:2px 3px;font:11px monospace;", { type: "number", min: 0, max, step: 1 });
    const apply = (v) => { set(Math.max(0, Math.min(max, Number(v) || 0))); update(true); };
    range.addEventListener("input", () => apply(range.value));
    num.addEventListener("input", () => apply(num.value));
    r.append(name, range, num);
    sliders.append(r);
    return () => { const v = Math.round(get()); range.value = v; num.value = v; range.style.background = gradient(); };
  }

  let refreshers = [];
  function build() {
    sliders.textContent = "";
    rgbBtn.style.background = mode === "rgb" ? "#3b6fd4" : "#2c2f36";
    hslBtn.style.background = mode === "hsl" ? "#3b6fd4" : "#2c2f36";
    const rgb = (o) => `rgb(${o.r},${o.g},${o.b})`;
    if (mode === "rgb") {
      refreshers = ["r", "g", "b"].map((k) => row(k.toUpperCase(), 255, () => c[k],
        (v) => { c[k] = v; hsl = rgbToHsl(c); },
        () => `linear-gradient(90deg,${rgb({ ...c, [k]: 0 })},${rgb({ ...c, [k]: 255 })})`));
    } else {
      refreshers = [
        row("H", 360, () => hsl.h, (v) => { hsl.h = v; Object.assign(c, hslToRgb(hsl)); },
          () => `linear-gradient(90deg,${[0, 60, 120, 180, 240, 300, 360].map((h) => rgb(hslToRgb({ h, s: hsl.s, l: hsl.l }))).join(",")})`),
        row("S", 100, () => hsl.s, (v) => { hsl.s = v; Object.assign(c, hslToRgb(hsl)); },
          () => `linear-gradient(90deg,${rgb(hslToRgb({ ...hsl, s: 0 }))},${rgb(hslToRgb({ ...hsl, s: 100 }))})`),
        row("L", 100, () => hsl.l, (v) => { hsl.l = v; Object.assign(c, hslToRgb(hsl)); },
          () => `linear-gradient(90deg,#000,${rgb(hslToRgb({ ...hsl, l: 50 }))},#fff)`),
      ];
    }
    refreshers.push(row("A", 100, () => (c.a / 255) * 100, (v) => { c.a = (v / 100) * 255; },
      () => `linear-gradient(90deg,rgba(${c.r},${c.g},${c.b},0),rgb(${c.r},${c.g},${c.b})),` +
        "repeating-conic-gradient(#999 0 25%,#ccc 0 50%) 0 0/8px 8px"));
    refreshers.forEach((f) => f());
  }

  let current = start;
  function setValue(v) {
    current = v;
    w.value = v;
    try { w.callback?.(v, app.canvas, node); } catch { /* a widget without a callback */ }
    node.setDirtyCanvas?.(true, true);
  }

  function update(apply) {
    const h = toHex(c);
    swFill.style.background = `rgba(${Math.round(c.r)},${Math.round(c.g)},${Math.round(c.b)},${c.a / 255})`;
    if (document.activeElement !== hex) hex.value = h;
    refreshers.forEach((f) => f());
    if (apply) setValue(h);
  }

  hex.addEventListener("input", () => {
    const p = parseHex(hex.value);
    if (p) { c = p; hsl = rgbToHsl(c); update(true); }
  });
  hex.addEventListener("keydown", (e) => { if (e.key === "Enter") close(true); });
  rgbBtn.onclick = () => { mode = "rgb"; try { localStorage.setItem("cratenode.pickerMode", mode); } catch {} build(); update(false); };
  hslBtn.onclick = () => { mode = "hsl"; try { localStorage.setItem("cratenode.pickerMode", mode); } catch {} build(); update(false); };

  if ("EyeDropper" in window) {
    const eye = el("button", btnCss, { textContent: "Eyedropper", title: "Pick a colour from anywhere on screen" });
    eye.onclick = async () => {
      try {
        const r = await new window.EyeDropper().open();
        const p = parseHex(r.sRGBHex);
        if (p) { p.a = c.a; c = p; hsl = rgbToHsl(c); update(true); }
      } catch { /* cancelled */ }
    };
    extras.append(eye);
  }
  for (const [label, value] of specials(node, w)) {
    const b = el("button", btnCss, { textContent: label });
    b.onclick = () => { setValue(value); close(true); };
    extras.append(b);
  }
  const done = el("button", btnCss + "margin-left:auto;", { textContent: "Done" });
  done.onclick = () => close(true);
  extras.append(done);

  for (const r of recent()) {
    const p = parseHex(r);
    const b = el("div", `width:16px;height:16px;border-radius:3px;cursor:pointer;border:1px solid #555;` +
      `background:rgba(${p.r},${p.g},${p.b},${p.a / 255});`, { title: r });
    b.onclick = () => { c = { ...p }; hsl = rgbToHsl(c); update(true); };
    recentRow.append(b);
  }
  if (!recentRow.childElementCount) recentRow.style.display = "none";

  function close(keep) {
    if (!keep) setValue(start);
    else if (parseHex(current) && current !== start) remember(current);
    document.removeEventListener("pointerdown", outside, true);
    document.removeEventListener("keydown", onKey, true);
    root.remove();
    open = null;
  }
  const outside = (e) => { if (!root.contains(e.target)) close(true); };
  const onKey = (e) => { if (e.key === "Escape") { e.stopPropagation(); close(false); } };
  setTimeout(() => document.addEventListener("pointerdown", outside, true), 0);
  document.addEventListener("keydown", onKey, true);

  build();
  update(false);
  document.body.append(root);
  const bw = root.offsetWidth, bh = root.offsetHeight;
  root.style.left = Math.max(8, Math.min(window.innerWidth - bw - 8, clientX + 12)) + "px";
  root.style.top = Math.max(8, Math.min(window.innerHeight - bh - 8, clientY - 20)) + "px";
  open = { root, close };
  hex.focus();
  hex.select();
}

// ---- wiring ----

app.registerExtension({
  name: "CrateNode.ColorPicker",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData?.name?.startsWith("CN")) return;
    const fields = new Set(), specs = {};
    for (const sect of ["required", "optional"]) {
      for (const [name, spec] of Object.entries(nodeData.input?.[sect] || {})) {
        const [type, opts = {}] = spec;
        if (type !== "STRING" || opts.multiline || !COLOR_NAME.test(name)) continue;
        fields.add(name);
        const d = String(opts.default ?? ""), tip = String(opts.tooltip ?? "");
        specs[name] = {
          empty: d === "" || /empty/i.test(tip),
          transparent: /transparent/i.test(tip) && name === "background",
          auto: d === "auto",
        };
      }
    }
    if (!fields.size) return;
    nodeType.prototype.cnColorFields = fields;
    nodeType.prototype.cnColorSpecs = specs;

    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      for (const w of this.widgets || []) if (fields.has(w.name)) hookField(this, w);
      return r;
    };
    const down = nodeType.prototype.onMouseDown;
    nodeType.prototype.onMouseDown = function (e, pos) {
      for (const chip of this.cnChips || []) {
        if (pos[0] >= chip.x && pos[0] <= chip.x + chip.cw && pos[1] >= chip.y && pos[1] <= chip.y + chip.ch) {
          openPicker(this, chip.w, e.clientX ?? 200, e.clientY ?? 200);
          return true;
        }
      }
      return down?.apply(this, arguments);
    };
  },
});
