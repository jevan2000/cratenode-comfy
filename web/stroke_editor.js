// CrateNode-Comfy stroke editor: clicking Shape's stroke_style field opens a pop-out with
// presets, alignment (centre / inside / outside), dash patterns, ends and corners, a second
// (double) line and "behind the fill", plus the stroke width. The field keeps plain text
// (e.g. "align=inside; dash=3,2"), so workflows and the API are unchanged.

const { app } = window.comfyAPI.app;

const FIELD = "stroke_style";
const MARGIN = 15;

// Same presets as cratenode_comfy/stroke.py (the server is the reference).
const PRESETS = [
  ["Solid", ""],
  ["Dashed", "dash=3,2; cap=butt"],
  ["Long dash", "dash=6,3; cap=butt"],
  ["Short dash", "dash=1.5,1.5; cap=butt"],
  ["Dotted", "dash=0,2; cap=round"],
  ["Dash dot", "dash=4,2,0,2; cap=round"],
  ["Double", "double=0.75,1,inside"],
  ["Thick + thin", "double=0.5,0.3,inside"],
  ["Thin + thick", "double=0.6,2,inside"],
  ["Outer ring", "double=1,0.4,outside"],
  ["Inside border", "align=inside; join=miter"],
  ["Outside border", "align=outside; join=miter"],
  ["Sharp corners", "join=miter; cap=square"],
  ["Behind the fill", "behind=1"],
];
const DASHES = [
  ["Solid", ""], ["Dashed", "3,2"], ["Long", "6,3"], ["Short", "1.5,1.5"], ["Dotted", "0,2"], ["Dash dot", "4,2,0,2"],
];
const DEFAULT = { align: "center", dash: "", offset: 0, cap: "round", join: "round",
  double: false, gap: 0.75, width2: 1, side: "inside", behind: false };

// ---- text <-> settings ----

function parse(text) {
  const s = { ...DEFAULT };
  for (const part of String(text || "").split(/[;\n]/)) {
    const [k, ...rest] = part.split("=");
    const key = k.trim().toLowerCase(), v = rest.join("=").trim().toLowerCase();
    if (!key) continue;
    if (key === "align") s.align = v;
    else if (key === "dash") s.dash = v.replace(/\s+/g, "");
    else if (key === "offset") s.offset = Number(v) || 0;
    else if (key === "cap") s.cap = v;
    else if (key === "join") s.join = v;
    else if (key === "behind") s.behind = ["1", "true", "yes", "on"].includes(v);
    else if (key === "double") {
      const [g, w, side] = v.split(",").map((x) => x.trim());
      s.double = true;
      s.gap = Number(g) || 0;
      s.width2 = Number(w) || 0;
      if (side) s.side = side;
    }
  }
  return s;
}

function toText(s) {
  const out = [];
  const n = (x) => String(Math.round(Number(x) * 1000) / 1000);
  if (s.align !== "center") out.push(`align=${s.align}`);
  if (s.dash) out.push(`dash=${s.dash}`);
  if (s.dash && Number(s.offset)) out.push(`offset=${n(s.offset)}`);
  if (s.cap !== "round") out.push(`cap=${s.cap}`);
  if (s.join !== "round") out.push(`join=${s.join}`);
  if (s.double && Number(s.width2) > 0) out.push(`double=${n(s.gap)},${n(s.width2)},${s.side}`);
  if (s.behind) out.push("behind=1");
  return out.join("; ");
}

// ---- a small drawing of a style (approximate; the node's live preview is exact) ----

function sketch(ctx, s, x, y, w, h, lw, color = "#ff6b5b") {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineCap = s.cap === "square" ? "square" : s.cap === "butt" ? "butt" : "round";
  ctx.lineJoin = s.join === "miter" ? "miter" : s.join === "bevel" ? "bevel" : "round";
  const dash = (s.dash || "").split(",").map(Number).filter((v) => !isNaN(v));
  const line = (inset, width, dashed) => {
    ctx.lineWidth = width;
    ctx.setLineDash(dashed && dash.length ? dash.map((v) => Math.max(0.01, v * lw)) : []);
    ctx.lineDashOffset = -(Number(s.offset) || 0) * lw;
    ctx.strokeRect(x + inset, y + inset, w - 2 * inset, h - 2 * inset);
  };
  const shift = { center: 0, inside: lw / 2, outside: -lw / 2 }[s.align] ?? 0;
  if (s.behind) { ctx.fillStyle = "#19a7a1"; }
  line(shift, lw, true);
  if (s.double && Number(s.width2) > 0) {
    const g = Number(s.gap) * lw, w2 = Number(s.width2) * lw, sign = s.side === "outside" ? -1 : 1;
    line(shift + sign * (lw / 2 + g + w2 / 2), w2, true);
  }
  if (s.behind) ctx.fillRect(x + lw / 2, y + lw / 2, w - lw, h - lw);
  ctx.restore();
}

// ---- the field: a little sample of the style after the label; a click opens the editor ----

function linked(node, w) {
  return (node.inputs || []).some((i) => i.widget?.name === w.name && i.link != null);
}

function hookField(node, w) {
  const key = typeof w.drawWidget === "function" ? "drawWidget" : "draw";
  const orig = w[key];
  if (typeof orig !== "function" || w.cnStrokeHooked) return;
  w.cnStrokeHooked = true;
  w[key] = function (ctx, ...args) {
    const r = orig.call(this, ctx, ...args);
    try {
      const legacy = args[0] === node;
      const y = legacy ? args[2] : (this.y ?? this.last_y);
      if (!this.hidden && !linked(node, this) && typeof y === "number") {
        const H = window.LiteGraph?.NODE_WIDGET_HEIGHT || 20;
        ctx.save();
        ctx.font = "12px Arial";
        const x = MARGIN * 2 + ctx.measureText(this.label || this.name).width + 10;
        ctx.beginPath();
        ctx.rect(x - 2, y + 2, 34, H - 4);
        ctx.clip();
        sketch(ctx, parse(this.value), x + 2, y + 6, 26, H - 12, 2);
        ctx.restore();
      }
    } catch { /* never break the node's drawing */ }
    return r;
  };
  const open = (e) => { if (e) openEditor(node, w, e.clientX ?? 200, e.clientY ?? 200); return !!e; };
  if (typeof w.onClick === "function") {
    const click = w.onClick;
    w.onClick = function (opts) { if (open(opts?.e)) return; return click.apply(this, arguments); };
  }
  if (typeof w.mouse === "function") {
    const mouse = w.mouse;
    w.mouse = function (e) {
      if (e?.type?.endsWith("down") && open(e)) return true;
      return mouse.apply(this, arguments);
    };
  }
}

// ---- the editor ----

let current = null;

function el(tag, css, attrs = {}) {
  const e = document.createElement(tag);
  if (css) e.style.cssText = css;
  Object.assign(e, attrs);
  return e;
}

const BTN = "background:#2c2f36;color:#d7dbe0;border:1px solid #474b53;border-radius:5px;padding:3px 6px;" +
  "font:12px sans-serif;cursor:pointer;";
const ON = "#3b6fd4";
const NUM = "width:52px;background:#14161a;color:#e8eaed;border:1px solid #444;border-radius:4px;padding:2px 4px;" +
  "font:11px monospace;";

function openEditor(node, w, clientX, clientY) {
  current?.close(false);
  const widthW = node.widgets?.find((x) => x.name === "stroke_width");
  const colorW = node.widgets?.find((x) => x.name === "stroke_color");
  const start = { style: String(w.value ?? ""), width: widthW?.value, color: colorW?.value };
  let s = parse(start.style);
  const ink = () => (/^#?[0-9a-f]{3,8}$/i.test(String(colorW?.value || "")) ? colorW.value : "#ff6b5b");

  const root = el("div",
    "position:fixed;z-index:10000;width:320px;box-sizing:border-box;overflow-x:hidden;padding:10px;border-radius:10px;background:#1f2126;color:#d7dbe0;" +
    "font:12px sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.55);border:1px solid #3a3d44;user-select:none;" +
    "display:flex;flex-direction:column;gap:8px;max-height:calc(100vh - 16px);overflow:auto;");
  root.addEventListener("pointerdown", (e) => e.stopPropagation());

  const title = el("div", "font-weight:600;color:#e8eaed;", { textContent: "Stroke" });
  const label = (t) => el("div", "color:#9aa3ad;font-size:11px;margin-bottom:3px;", { textContent: t });

  // presets: small drawings
  const presetBox = el("div", "display:grid;grid-template-columns:repeat(4,1fr);gap:5px;");
  for (const [name, text] of PRESETS) {
    const b = el("button", BTN + "padding:3px;display:flex;flex-direction:column;align-items:center;gap:2px;" +
      "min-width:0;overflow:hidden;",
      { title: text || "plain stroke" });
    const cv = el("canvas", "width:56px;height:30px;", { width: 112, height: 60 });
    const c = cv.getContext("2d");
    c.scale(2, 2);
    c.fillStyle = "#19a7a1";
    c.fillRect(10, 7, 36, 16);
    sketch(c, parse(text), 10, 7, 36, 16, 3, ink());
    b.append(cv, el("span", "font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%;",
      { textContent: name }));
    b.title = `${name}: ${text || "plain stroke"}`;
    b.onclick = () => { s = parse(text); refresh(true); };
    presetBox.append(b);
  }

  // a row of toggle buttons for one setting
  function seg(key, options) {
    const row = el("div", "display:flex;gap:4px;");
    const btns = options.map(([value, text]) => {
      const b = el("button", BTN + "flex:1;", { textContent: text });
      b.onclick = () => { s[key] = value; refresh(true); };
      row.append(b);
      return [value, b];
    });
    row.update = () => btns.forEach(([v, b]) => { b.style.background = s[key] === v ? ON : "#2c2f36"; });
    return row;
  }
  const num = (key, step, min, max) => {
    const i = el("input", NUM, { type: "number", step, min, max });
    i.addEventListener("input", () => { s[key] = Number(i.value) || 0; refresh(true, i); });
    i.update = () => { if (document.activeElement !== i) i.value = s[key]; };
    return i;
  };
  const check = (key, text) => {
    const lab = el("label", "display:flex;align-items:center;gap:6px;cursor:pointer;");
    const c = el("input", "", { type: "checkbox" });
    c.onchange = () => { s[key] = c.checked; refresh(true); };
    lab.append(c, el("span", "", { textContent: text }));
    lab.update = () => { c.checked = !!s[key]; };
    return lab;
  };

  // width (the node's stroke_width) with a slider
  const widthRow = el("div", "display:flex;align-items:center;gap:6px;");
  const wRange = el("input", "flex:1;", { type: "range", min: 0, max: 60, step: 0.5 });
  const wNum = el("input", NUM, { type: "number", min: 0, max: 1000, step: 0.5 });
  const setWidth = (v) => {
    if (!widthW) return;
    widthW.value = Math.max(0, Number(v) || 0);
    try { widthW.callback?.(widthW.value, app.canvas, node); } catch {}
    node.setDirtyCanvas?.(true, true);
  };
  wRange.oninput = () => { setWidth(wRange.value); wNum.value = wRange.value; };
  wNum.oninput = () => { setWidth(wNum.value); wRange.value = wNum.value; };
  widthRow.append(el("span", "width:42px;color:#9aa3ad;", { textContent: "Width" }), wRange, wNum);
  if (!widthW) widthRow.style.display = "none";

  const align = seg("align", [["center", "Centre"], ["inside", "Inside"], ["outside", "Outside"]]);
  const dashSel = el("select", "flex:1;background:#14161a;color:#e8eaed;border:1px solid #444;border-radius:4px;" +
    "padding:2px;font:12px sans-serif;");
  for (const [name, v] of DASHES) dashSel.append(el("option", "", { value: v, textContent: name }));
  dashSel.append(el("option", "", { value: "custom", textContent: "Custom…" }));
  const dashText = el("input", NUM + "width:80px;", { type: "text", placeholder: "on,off", title:
    "Dash pattern: on,off lengths in stroke widths (e.g. 3,2 or 4,2,0,2); 0 with round ends = dots" });
  const offset = num("offset", 0.25, -100, 100);
  offset.title = "Dash offset, in stroke widths (shifts where the dashes start)";
  dashSel.onchange = () => {
    if (dashSel.value !== "custom") s.dash = dashSel.value;
    else if (!s.dash) s.dash = "2,1";
    if (s.dash === "0,2" || s.dash === "4,2,0,2") s.cap = "round";
    refresh(true);
  };
  dashText.addEventListener("input", () => {
    const v = dashText.value.replace(/\s+/g, "");
    const nums = v.split(",").filter(Boolean).map(Number);
    const ok = !v || (nums.length % 2 === 0 && nums.every((n) => n >= 0) && nums.some((n) => n > 0));
    dashText.style.borderColor = ok ? "#444" : "#d04040";
    if (ok) { s.dash = v; refresh(true, dashText); }
  });
  const dashRow = el("div", "display:flex;gap:5px;align-items:center;");
  dashRow.append(dashSel, dashText, el("span", "color:#9aa3ad;", { textContent: "offset" }), offset);

  const cap = seg("cap", [["round", "Round"], ["butt", "Flat"], ["square", "Square"]]);
  const join = seg("join", [["round", "Round"], ["miter", "Sharp"], ["bevel", "Bevel"]]);

  const dbl = check("double", "Second line");
  const dblRow = el("div", "display:flex;gap:5px;align-items:center;flex-wrap:wrap;");
  const gap = num("gap", 0.1, 0, 50), w2 = num("width2", 0.1, 0, 50);
  gap.title = "Space between the lines, in stroke widths";
  w2.title = "Second line's width, in stroke widths (0.3 = thin, 2 = thick)";
  const side = seg("side", [["inside", "Inside"], ["outside", "Outside"]]);
  side.style.flex = "1";
  dblRow.append(el("span", "color:#9aa3ad;", { textContent: "gap" }), gap,
    el("span", "color:#9aa3ad;", { textContent: "width" }), w2, side);
  const behind = check("behind", "Behind the fill (the fill covers the inner half)");

  const textBox = el("input", NUM + "width:100%;box-sizing:border-box;font-size:11px;", { type: "text",
    spellcheck: false, placeholder: "plain stroke", title: "The style as text (what is saved); you can type here" });
  textBox.addEventListener("input", () => { s = parse(textBox.value); refresh(true, textBox, textBox.value); });

  const foot = el("div", "display:flex;gap:6px;");
  const reset = el("button", BTN, { textContent: "Plain" });
  reset.onclick = () => { s = { ...DEFAULT }; refresh(true); };
  const done = el("button", BTN + "margin-left:auto;", { textContent: "Done" });
  done.onclick = () => close(true);
  foot.append(reset, done);

  const section = (name, ...kids) => { const d = el("div"); d.append(label(name), ...kids); return d; };
  root.append(title, presetBox, widthRow, section("Alignment", align), section("Dashes", dashRow),
    section("Ends", cap), section("Corners", join), dbl, dblRow, behind, section("Style text", textBox), foot);

  function refresh(apply, source, raw) {
    for (const r of [align, cap, join, side, dbl, behind]) r.update();
    for (const i of [offset, gap, w2]) if (i !== source) i.update();
    const known = DASHES.find(([, v]) => v === s.dash);
    dashSel.value = known ? s.dash : "custom";
    if (source !== dashText) dashText.value = s.dash;
    dashText.style.display = known ? "none" : "";
    offset.disabled = !s.dash;
    dblRow.style.opacity = s.double ? "1" : "0.4";
    dblRow.style.pointerEvents = s.double ? "" : "none";
    if (widthW) { wNum.value = widthW.value; wRange.value = widthW.value; }
    const text = raw ?? toText(s);
    if (source !== textBox) textBox.value = text;
    if (apply) {
      w.value = text;
      try { w.callback?.(text, app.canvas, node); } catch {}
      node.setDirtyCanvas?.(true, true);
    }
  }

  function close(keep) {
    if (!keep) {
      w.value = start.style;
      try { w.callback?.(start.style, app.canvas, node); } catch {}
      if (widthW && start.width !== undefined) setWidth(start.width);
      if (colorW && colorW.value !== start.color) {
        colorW.value = start.color;
        try { colorW.callback?.(start.color, app.canvas, node); } catch {}
      }
      node.setDirtyCanvas?.(true, true);
    }
    document.removeEventListener("pointerdown", outside, true);
    document.removeEventListener("keydown", onKey, true);
    root.remove();
    current = null;
  }
  const outside = (e) => { if (!root.contains(e.target)) close(true); };
  const onKey = (e) => {
    if (e.key === "Escape") { e.stopPropagation(); close(false); }
    else if (e.key === "Enter" && e.target?.tagName === "INPUT") close(true);
  };
  setTimeout(() => document.addEventListener("pointerdown", outside, true), 0);
  document.addEventListener("keydown", onKey, true);

  // a stroke needs a width and a colour to show: give it some when it has none
  if (widthW && !(Number(widthW.value) > 0)) setWidth(8);
  if (colorW && !String(colorW.value || "").trim()) {
    colorW.value = "#ff6b5b";
    try { colorW.callback?.(colorW.value, app.canvas, node); } catch {}
  }

  refresh(false);
  document.body.append(root);
  const bw = root.offsetWidth, bh = root.offsetHeight;
  root.style.left = Math.max(8, Math.min(window.innerWidth - bw - 8, clientX + 12)) + "px";
  root.style.top = Math.max(8, Math.min(window.innerHeight - bh - 8, clientY - 40)) + "px";
  current = { close };
}

app.registerExtension({
  name: "CrateNode.StrokeEditor",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!nodeData?.name?.startsWith("CN")) return;
    const inputs = { ...(nodeData.input?.required || {}), ...(nodeData.input?.optional || {}) };
    if (!inputs[FIELD]) return;
    const created = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const r = created?.apply(this, arguments);
      const w = this.widgets?.find((x) => x.name === FIELD);
      if (w) hookField(this, w);
      return r;
    };
  },
});
