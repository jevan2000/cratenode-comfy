"""Turn API-format workflows (api_examples/*.api.json) into UI-format workflows that ComfyUI
opens with nodes laid out and wired, and lists under Templates for this pack.

    python tools/api_to_ui.py api_examples/*.api.json [--server http://127.0.0.1:8195] [--out example_workflows]

Node definitions (widget order, types, outputs) come from the server's /object_info,
so run it against a ComfyUI with the pack installed. Standard library only.
"""

from __future__ import annotations

import argparse
import glob
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WIDGETS = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}
COL_W, GAP_Y, NODE_W = 400, 40, 340


def object_info(server: str) -> dict:
    with urllib.request.urlopen(f"{server}/object_info", timeout=60) as r:
        return json.loads(r.read())


def _is_link(v) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], str) and isinstance(v[1], int)


def _kind(spec):
    t = spec[0]
    return "COMBO" if isinstance(t, list) else t


def _default(spec):
    t, opts = spec[0], (spec[1] if len(spec) > 1 else {})
    if "default" in opts:
        return opts["default"]
    if isinstance(t, list):
        return t[0] if t else ""
    if t == "COMBO":
        return (opts.get("options") or [""])[0]
    return {"INT": 0, "FLOAT": 0.0, "STRING": "", "BOOLEAN": False}.get(t)


def convert(api: dict, info: dict) -> dict:
    ids = sorted(api, key=int)
    nodes, links, link_id = {}, [], 0
    # depth = longest path from a source, for the column layout
    depth: dict[str, int] = {}

    def d(nid, seen=()):
        if nid in depth:
            return depth[nid]
        srcs = [v[0] for v in api[nid]["inputs"].values() if _is_link(v) and v[0] in api and v[0] not in seen]
        depth[nid] = 0 if not srcs else 1 + max(d(s, seen + (nid,)) for s in srcs)
        return depth[nid]

    for nid in ids:
        d(nid)
    out_links: dict[tuple, list] = {}
    for nid in ids:
        node = api[nid]
        ct = node["class_type"]
        if ct not in info:
            raise SystemExit(f"node {nid}: {ct} is not installed on the server")
        oi = info[ct]
        req, opt = oi["input"].get("required", {}), oi["input"].get("optional", {})
        order = oi.get("input_order") or {"required": list(req), "optional": list(opt)}
        inputs, widgets = [], []
        for name in order.get("required", []) + order.get("optional", []):
            spec = req.get(name) or opt.get(name)
            if spec is None:
                continue
            kind, opts = _kind(spec), (spec[1] if len(spec) > 1 else {})
            val = node["inputs"].get(name)
            if kind in WIDGETS:
                linked = _is_link(val)
                widgets.append(_default(spec) if linked or val is None else val)
                if opts.get("control_after_generate"):
                    widgets.append("fixed")
                if opts.get("image_upload") or opts.get("video_upload") or opts.get("audio_upload"):
                    widgets.append("image")
                if linked:
                    inputs.append({"name": name, "type": kind, "widget": {"name": name}, "link": None, "_src": val})
            else:
                inputs.append({"name": name, "type": kind, "link": None, "_src": val if _is_link(val) else None})
        outs = [{"name": n, "type": t, "links": None, **({"shape": 6} if lst else {})}
                for n, t, lst in zip(oi.get("output_name") or oi["output"], oi["output"],
                                     oi.get("output_is_list") or [False] * len(oi["output"]))]
        nodes[nid] = {"id": int(nid), "type": ct, "pos": [0, 0], "size": [NODE_W, 0], "flags": {}, "order": 0,
                      "mode": 0, "inputs": inputs, "outputs": outs,
                      "properties": {"Node name for S&R": ct}, "widgets_values": widgets}
        if node.get("_meta", {}).get("title"):
            nodes[nid]["title"] = node["_meta"]["title"]
    # links
    for nid in ids:
        for slot, inp in enumerate(nodes[nid]["inputs"]):
            src = inp.pop("_src")
            if not src:
                continue
            sid, sslot = src
            link_id += 1
            ltype = nodes[sid]["outputs"][sslot]["type"]
            links.append([link_id, int(sid), sslot, int(nid), slot, ltype])
            inp["link"] = link_id
            out_links.setdefault((sid, sslot), []).append(link_id)
    for (sid, sslot), ls in out_links.items():
        nodes[sid]["outputs"][sslot]["links"] = ls
        nodes[sid]["outputs"][sslot]["slot_index"] = sslot
    # layout: columns by depth, stacked
    col_y: dict[int, float] = {}
    for order, nid in enumerate(sorted(ids, key=lambda n: (depth[n], int(n)))):
        n = nodes[nid]
        h = 46 + 24 * len(n["widgets_values"]) + 22 * max(len([i for i in n["inputs"] if "widget" not in i]),
                                                          len(n["outputs"]))
        if n["type"] in ("PreviewImage", "SaveImage", "LoadImage") or n["type"].startswith("CNExport"):
            h += 260
        y = col_y.get(depth[nid], 0.0)
        n["pos"] = [depth[nid] * COL_W, y]
        n["size"] = [NODE_W, h]
        n["order"] = order
        col_y[depth[nid]] = y + h + GAP_Y
    return {"last_node_id": max(int(i) for i in ids), "last_link_id": link_id,
            "nodes": [nodes[i] for i in ids], "links": links, "groups": [], "config": {},
            "extra": {"ds": {"scale": 0.75, "offset": [40, 40]}}, "version": 0.4}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("workflows", nargs="+")
    ap.add_argument("--server", default="http://127.0.0.1:8195")
    ap.add_argument("--out", default=str(ROOT / "example_workflows"))
    a = ap.parse_args()
    info = object_info(a.server)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = [f for pat in a.workflows for f in (glob.glob(pat) or [pat])]
    for f in files:
        api = json.loads(Path(f).read_text(encoding="utf-8"))
        ui = convert(api, info)
        name = Path(f).name.replace(".api.json", ".json")
        (out / name).write_text(json.dumps(ui, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{name}: {len(ui['nodes'])} nodes, {len(ui['links'])} links")


if __name__ == "__main__":
    main()
